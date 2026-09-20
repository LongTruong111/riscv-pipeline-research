from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

from .execution_event import ExecutionEvent
from .isa_decode import OP_STORE


L1_BIN_IDS = tuple(f"H{i:02d}" for i in range(1, 21))
L1_BIN_COUNT = 20


@dataclass(frozen=True, slots=True)
class L1Hit:
    """
    One L1 Intent classification.

    This object records scenario occurrence only.

    DUT correctness, forwarding correctness, stall correctness, writeback
    correctness, and architectural scoreboard results are intentionally
    outside this classifier.
    """

    bin_id: str
    consumer_instruction_index: int
    producer_instruction_indices: Tuple[int, ...]
    matched_sources: Tuple[str, ...]


class L1CoverageCollector:
    """
    Frozen H01-H20 L1 Intent coverage classifier.

    Dependency distance is computed in executed-program order using
    ExecutionEvent.instruction_index, never raw cycle difference.

    Only the previous three executed instructions are required because the
    frozen L1 dependency space extends through d3.
    """

    def __init__(self) -> None:
        self.intent_seen: Dict[str, bool] = {
            bin_id: False for bin_id in L1_BIN_IDS
        }

        self.intent_hit_count: Dict[str, int] = {
            bin_id: 0 for bin_id in L1_BIN_IDS
        }

        self._history: Deque[ExecutionEvent] = deque(maxlen=3)
        self._last_instruction_index = 0

    def reset(self) -> None:
        for bin_id in L1_BIN_IDS:
            self.intent_seen[bin_id] = False
            self.intent_hit_count[bin_id] = 0

        self._history.clear()
        self._last_instruction_index = 0

    @property
    def instructions_observed(self) -> int:
        return self._last_instruction_index

    @property
    def intent_bins(self) -> int:
        return sum(self.intent_seen.values())

    @property
    def intent_coverage(self) -> float:
        return self.intent_bins / L1_BIN_COUNT

    def _check_instruction_order(self, event: ExecutionEvent) -> None:
        expected = self._last_instruction_index + 1

        if event.instruction_index != expected:
            raise ValueError(
                "ExecutionEvent stream must be contiguous in executed "
                f"program order: expected instruction_index={expected}, "
                f"got {event.instruction_index}"
            )

    @staticmethod
    def _is_positive_producer(event: Optional[ExecutionEvent]) -> bool:
        return (
            event is not None
            and event.writes_rd
            and event.rd != 0
            and event.producer_type != "NONE"
        )

    def _producer_at_distance(
        self,
        distance: int,
    ) -> Optional[ExecutionEvent]:
        if distance <= 0:
            raise ValueError("distance must be positive")

        if len(self._history) < distance:
            return None

        return list(self._history)[-distance]

    def _nearest_writer(
        self,
        register: int,
    ) -> Optional[ExecutionEvent]:
        """
        Return the nearest valid architectural writer to register.

        x0 deliberately has no positive architectural writer.
        """
        if register == 0:
            return None

        for previous in reversed(self._history):
            if (
                self._is_positive_producer(previous)
                and previous.rd == register
            ):
                return previous

        return None

    def _is_nearest_writer(
        self,
        producer: Optional[ExecutionEvent],
        register: int,
    ) -> bool:
        if producer is None:
            return False

        return self._nearest_writer(register) is producer

    @staticmethod
    def _uses_rs1(event: ExecutionEvent, register: int) -> bool:
        return event.uses_rs1 and event.rs1 == register

    @staticmethod
    def _uses_rs2(event: ExecutionEvent, register: int) -> bool:
        return event.uses_rs2 and event.rs2 == register

    @staticmethod
    def _used_source_roles(
        event: ExecutionEvent,
        register: int,
    ) -> Tuple[str, ...]:
        roles: List[str] = []

        if event.uses_rs1 and event.rs1 == register:
            roles.append("RS1")

        if event.uses_rs2 and event.rs2 == register:
            roles.append("RS2")

        return tuple(roles)

    @staticmethod
    def _opcode(event: ExecutionEvent) -> int:
        return event.instruction & 0x7F

    @staticmethod
    def _raw_rs2(event: ExecutionEvent) -> int:
        return (event.instruction >> 20) & 0x1F

    def observe(self, event: ExecutionEvent) -> Tuple[L1Hit, ...]:
        """
        Classify all L1 Intent bins satisfied by one executed instruction.

        Multiple bins may be hit by one event when their frozen semantic
        predicates genuinely overlap. This is permitted by the vPlan.
        """
        self._check_instruction_order(event)

        p1 = self._producer_at_distance(1)
        p2 = self._producer_at_distance(2)
        p3 = self._producer_at_distance(3)

        hits: List[L1Hit] = []
        emitted = set()

        def add_hit(
            bin_id: str,
            producers: Tuple[ExecutionEvent, ...],
            matched_sources: Tuple[str, ...],
        ) -> None:
            if bin_id in emitted:
                return

            emitted.add(bin_id)

            hit = L1Hit(
                bin_id=bin_id,
                consumer_instruction_index=event.instruction_index,
                producer_instruction_indices=tuple(
                    producer.instruction_index
                    for producer in producers
                ),
                matched_sources=matched_sources,
            )

            hits.append(hit)

            self.intent_hit_count[bin_id] += 1
            self.intent_seen[bin_id] = True

        # --------------------------------------------------------------
        # H01 — ALU d1 / RS1_ONLY / RS1
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p1)
            and p1.producer_type == "ALU_RESULT"
            and event.consumer_type == "RS1_ONLY"
            and self._uses_rs1(event, p1.rd)
            and self._is_nearest_writer(p1, p1.rd)
        ):
            add_hit("H01", (p1,), ("RS1",))

        # --------------------------------------------------------------
        # H02 — ALU d1 / RS1_RS2 / RS2
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p1)
            and p1.producer_type == "ALU_RESULT"
            and event.consumer_type == "RS1_RS2"
            and self._uses_rs2(event, p1.rd)
            and self._is_nearest_writer(p1, p1.rd)
        ):
            add_hit("H02", (p1,), ("RS2",))

        # --------------------------------------------------------------
        # H03 — ALU d2 / RS1_ONLY / RS1
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p2)
            and p2.producer_type == "ALU_RESULT"
            and event.consumer_type == "RS1_ONLY"
            and self._uses_rs1(event, p2.rd)
            and self._is_nearest_writer(p2, p2.rd)
        ):
            add_hit("H03", (p2,), ("RS1",))

        # --------------------------------------------------------------
        # H04 — ALU d2 / RS1_RS2 / RS2
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p2)
            and p2.producer_type == "ALU_RESULT"
            and event.consumer_type == "RS1_RS2"
            and self._uses_rs2(event, p2.rd)
            and self._is_nearest_writer(p2, p2.rd)
        ):
            add_hit("H04", (p2,), ("RS2",))

        # --------------------------------------------------------------
        # H05 — any valid GPR producer / d3 RF boundary
        #
        # Use nearest-writer attribution so a shadowed d3 producer does
        # not incorrectly count.
        # --------------------------------------------------------------
        if self._is_positive_producer(p3):
            roles = self._used_source_roles(event, p3.rd)

            if (
                roles
                and self._is_nearest_writer(p3, p3.rd)
            ):
                add_hit("H05", (p3,), roles)

        # --------------------------------------------------------------
        # H06 — LOAD d1 / RS1_ONLY / RS1
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p1)
            and p1.producer_type == "MEM_DATA"
            and event.consumer_type == "RS1_ONLY"
            and self._uses_rs1(event, p1.rd)
            and self._is_nearest_writer(p1, p1.rd)
        ):
            add_hit("H06", (p1,), ("RS1",))

        # --------------------------------------------------------------
        # H07 — LOAD d1 / RS1_RS2 / RS2
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p1)
            and p1.producer_type == "MEM_DATA"
            and event.consumer_type == "RS1_RS2"
            and self._uses_rs2(event, p1.rd)
            and self._is_nearest_writer(p1, p1.rd)
        ):
            add_hit("H07", (p1,), ("RS2",))

        # --------------------------------------------------------------
        # H08 — LOAD d2 / RS1_ONLY / RS1
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p2)
            and p2.producer_type == "MEM_DATA"
            and event.consumer_type == "RS1_ONLY"
            and self._uses_rs1(event, p2.rd)
            and self._is_nearest_writer(p2, p2.rd)
        ):
            add_hit("H08", (p2,), ("RS1",))

        # --------------------------------------------------------------
        # H09 — LOAD d2 / RS1_RS2 / RS2
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p2)
            and p2.producer_type == "MEM_DATA"
            and event.consumer_type == "RS1_RS2"
            and self._uses_rs2(event, p2.rd)
            and self._is_nearest_writer(p2, p2.rd)
        ):
            add_hit("H09", (p2,), ("RS2",))

        # --------------------------------------------------------------
        # H10 — two distinct ALU producers feeding a dual-source consumer
        #        at d1 + d2.
        #
        # Either source orientation is accepted because H10 is one
        # behavioral equivalence class. The canonical directed witness has
        # d1 on RS1 and d2 on RS2.
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p1)
            and self._is_positive_producer(p2)
            and p1.producer_type == "ALU_RESULT"
            and p2.producer_type == "ALU_RESULT"
            and p1.rd != p2.rd
            and event.consumer_type == "RS1_RS2"
            and event.uses_rs1
            and event.uses_rs2
        ):
            canonical = (
                event.rs1 == p1.rd
                and event.rs2 == p2.rd
            )

            reversed_roles = (
                event.rs1 == p2.rd
                and event.rs2 == p1.rd
            )

            if canonical or reversed_roles:
                add_hit(
                    "H10",
                    (p2, p1),
                    ("RS1", "RS2"),
                )

        # --------------------------------------------------------------
        # H11 — LUI / IMM d1 / RS1
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p1)
            and p1.producer_type == "IMM"
            and self._uses_rs1(event, p1.rd)
            and self._is_nearest_writer(p1, p1.rd)
        ):
            add_hit("H11", (p1,), ("RS1",))

        # --------------------------------------------------------------
        # H12 — LUI / IMM d2 / RS1
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p2)
            and p2.producer_type == "IMM"
            and self._uses_rs1(event, p2.rd)
            and self._is_nearest_writer(p2, p2.rd)
        ):
            add_hit("H12", (p2,), ("RS1",))

        # --------------------------------------------------------------
        # H13 — AUIPC / PC_PLUS_IMM d1 / RS1
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p1)
            and p1.producer_type == "PC_PLUS_IMM"
            and self._uses_rs1(event, p1.rd)
            and self._is_nearest_writer(p1, p1.rd)
        ):
            add_hit("H13", (p1,), ("RS1",))

        # --------------------------------------------------------------
        # H14 — AUIPC / PC_PLUS_IMM d2 / RS1
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p2)
            and p2.producer_type == "PC_PLUS_IMM"
            and self._uses_rs1(event, p2.rd)
            and self._is_nearest_writer(p2, p2.rd)
        ):
            add_hit("H14", (p2,), ("RS1",))

        # --------------------------------------------------------------
        # H15 — JAL/JALR link producer followed by the next EXECUTED
        #        target consumer.
        #
        # Flushed fall-through instructions are absent from ExecutionEvent
        # history, so executed d1 is naturally represented by p1.
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p1)
            and p1.producer_type == "PC_PLUS_4"
        ):
            roles = self._used_source_roles(event, p1.rd)

            if roles and self._is_nearest_writer(p1, p1.rd):
                add_hit("H15", (p1,), roles)

        # --------------------------------------------------------------
        # H16 — ALU d1 -> STORE data / RS2
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p1)
            and p1.producer_type == "ALU_RESULT"
            and self._opcode(event) == OP_STORE
            and self._uses_rs2(event, p1.rd)
            and self._is_nearest_writer(p1, p1.rd)
        ):
            add_hit("H16", (p1,), ("RS2",))

        # --------------------------------------------------------------
        # H17 — newest-producer priority:
        #
        # p2 writes xR
        # p1 writes xR
        # current consumer reads xR
        #
        # p1 is newest d1 producer; p2 is older d2 producer.
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p1)
            and self._is_positive_producer(p2)
            and p1.rd == p2.rd
        ):
            roles = self._used_source_roles(event, p1.rd)

            if roles:
                add_hit(
                    "H17",
                    (p2, p1),
                    roles,
                )

        # --------------------------------------------------------------
        # H18 — x0 forwarding exclusion.
        #
        # An instruction with an architectural GPR destination field x0 is
        # immediately followed by a consumer that architecturally reads x0.
        #
        # This is intentionally NOT a positive RAW dependency.
        # --------------------------------------------------------------
        if (
            p1 is not None
            and p1.writes_rd
            and p1.rd == 0
        ):
            roles = self._used_source_roles(event, 0)

            if roles:
                add_hit("H18", (p1,), roles)

        # --------------------------------------------------------------
        # H19 — LOAD destination x0 followed by a valid consumer reading x0.
        #
        # Intent occurrence is independent of whether the frozen detector
        # incorrectly stalls.
        # --------------------------------------------------------------
        if (
            p1 is not None
            and p1.writes_rd
            and p1.producer_type == "MEM_DATA"
            and p1.rd == 0
        ):
            roles = self._used_source_roles(event, 0)

            if roles:
                add_hit("H19", (p1,), roles)

        # --------------------------------------------------------------
        # H20 — LOAD followed by instruction whose raw rs2 field matches
        #        load rd although rs2 is not architecturally used.
        #
        # Ensure there is no real dependency through another used source.
        # --------------------------------------------------------------
        if (
            self._is_positive_producer(p1)
            and p1.producer_type == "MEM_DATA"
            and not event.uses_rs2
            and self._raw_rs2(event) == p1.rd
            and p1.rd not in event.architectural_sources()
        ):
            add_hit("H20", (p1,), ("RAW_RS2_UNUSED",))

        self._history.append(event)
        self._last_instruction_index = event.instruction_index

        return tuple(hits)
