from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .execution_event import ExecutionEvent


L2_REGISTERS = 31
L2_DISTANCES = 2
L2_BIN_COUNT = L2_REGISTERS * L2_DISTANCES

D1 = 1
D2 = 2


def l2_bin_index(distance: int, register: int) -> int:
    """
    Frozen deterministic mapping:

        (d1, x1)  -> 0
        (d1, x31) -> 30
        (d2, x1)  -> 31
        (d2, x31) -> 61
    """
    if distance not in (D1, D2):
        raise ValueError(f"L2 distance must be d1 or d2, got {distance}")

    if not 1 <= register <= 31:
        raise ValueError(
            f"L2 dependent register must be x1..x31, got x{register}"
        )

    return (distance - 1) * 31 + (register - 1)


@dataclass(frozen=True, slots=True)
class WriterRecord:
    instruction_index: int
    register: int
    producer_type: str


@dataclass(frozen=True, slots=True)
class L2Hit:
    """
    One positive architectural RAW dependency classified into frozen L2.
    """

    bin_index: int
    distance: int
    register: int

    producer_instruction_index: int
    consumer_instruction_index: int

    producer_type: str
    consumer_type: str


class L2CoverageCollector:
    """
    Frozen 62-bin L2 dependency collector.

    Intent classification is independent of DUT correctness.

    The collector operates on contiguous ExecutionEvent objects, where one
    event corresponds to one instruction in executed-program order.
    """

    def __init__(self) -> None:
        self.intent_seen: List[bool] = [False] * L2_BIN_COUNT
        self.validated_seen: List[bool] = [False] * L2_BIN_COUNT

        self.intent_hit_count: List[int] = [0] * L2_BIN_COUNT
        self.validated_hit_count: List[int] = [0] * L2_BIN_COUNT

        # Index zero is intentionally unused for positive RAW attribution.
        self._last_writer: List[Optional[WriterRecord]] = [None] * 32

        self._last_instruction_index = 0

    def reset(self) -> None:
        self.intent_seen[:] = [False] * L2_BIN_COUNT
        self.validated_seen[:] = [False] * L2_BIN_COUNT

        self.intent_hit_count[:] = [0] * L2_BIN_COUNT
        self.validated_hit_count[:] = [0] * L2_BIN_COUNT

        self._last_writer[:] = [None] * 32
        self._last_instruction_index = 0

    @property
    def intent_bins(self) -> int:
        return sum(self.intent_seen)

    @property
    def validated_bins(self) -> int:
        return sum(self.validated_seen)

    @property
    def intent_coverage(self) -> float:
        return self.intent_bins / L2_BIN_COUNT

    @property
    def validated_coverage(self) -> float:
        return self.validated_bins / L2_BIN_COUNT

    def _check_instruction_order(self, event: ExecutionEvent) -> None:
        expected = self._last_instruction_index + 1

        if event.instruction_index != expected:
            raise ValueError(
                "ExecutionEvent stream must be contiguous in executed "
                f"program order: expected instruction_index={expected}, "
                f"got {event.instruction_index}"
            )

    def observe(self, event: ExecutionEvent) -> Tuple[L2Hit, ...]:
        """
        Process one architecturally executed instruction.

        Processing order is deliberately:

            read dependencies
            -> classify hits
            -> update destination writer

        This preserves read-before-write semantics for instructions that read
        and write the same architectural register.
        """
        self._check_instruction_order(event)

        event_hits: List[L2Hit] = []
        event_bin_indices = set()

        for source_register in event.architectural_sources():
            # Frozen x0 rule: x0 cannot represent a positive RAW dependency.
            if source_register == 0:
                continue

            writer = self._last_writer[source_register]

            if writer is None:
                continue

            distance = (
                event.instruction_index - writer.instruction_index
            )

            # L2 contains exactly d1 and d2.
            if distance not in (D1, D2):
                continue

            index = l2_bin_index(distance, source_register)

            # If rs1 == rs2 and both are architecturally used, the dependency
            # is still one (distance, register) L2 bin for this event.
            if index in event_bin_indices:
                continue

            event_bin_indices.add(index)

            hit = L2Hit(
                bin_index=index,
                distance=distance,
                register=source_register,
                producer_instruction_index=writer.instruction_index,
                consumer_instruction_index=event.instruction_index,
                producer_type=writer.producer_type,
                consumer_type=event.consumer_type,
            )

            event_hits.append(hit)

            self.intent_hit_count[index] += 1
            self.intent_seen[index] = True

        # Latest-writer attribution:
        # update only after processing the consumer's reads.
        if event.writes_rd and event.rd != 0:
            self._last_writer[event.rd] = WriterRecord(
                instruction_index=event.instruction_index,
                register=event.rd,
                producer_type=event.producer_type,
            )

        self._last_instruction_index = event.instruction_index

        return tuple(event_hits)

    def promote_validated(
        self,
        hits: Sequence[L2Hit],
    ) -> None:
        """
        Promote already-classified Intent hits after independent realization
        checking succeeds.

        Scoreboard/checker logic is deliberately outside this collector.
        """
        seen_in_call = set()

        for hit in hits:
            index = hit.bin_index

            if not 0 <= index < L2_BIN_COUNT:
                raise ValueError(f"Invalid L2 bin index: {index}")

            if not self.intent_seen[index]:
                raise ValueError(
                    "Cannot promote an L2 bin that has not been observed "
                    f"as Intent first: bin={index}"
                )

            if index in seen_in_call:
                continue

            seen_in_call.add(index)

            self.validated_hit_count[index] += 1
            self.validated_seen[index] = True
