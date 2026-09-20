"""Week 9 deterministic coverage state collector.

This module owns coverage bookkeeping only.

It does NOT decide whether DUT behavior is functionally or temporally
correct. Validation decisions are supplied later by the Week-9
validated-attribution layer.

Frozen coverage model:
    L1 = H01..H20
    L2 = {d1, d2} x {x1..x31} = 62 bins
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple


L1Bin = str
L2Bin = Tuple[str, int]


@dataclass(frozen=True)
class FirstHit:
    """Metadata captured for the first occurrence of a coverage state."""

    instruction_id: int
    cycle: int
    wall_ns: int


@dataclass
class BinState:
    """Intent and validated state for one coverage bin."""

    intent_seen: bool = False
    validated_seen: bool = False

    intent_first: Optional[FirstHit] = None
    validated_first: Optional[FirstHit] = None


@dataclass(frozen=True)
class CoverageCheckpoint:
    """Coverage snapshot at an executed-instruction boundary."""

    executed_instructions: int
    cycle: int

    l1_intent_count: int
    l1_validated_count: int

    l2_intent_count: int
    l2_validated_count: int


class CoverageCollector:
    """Deterministic L1/L2 coverage state collector.

    Complexity:
        hit/update:
            O(1)

        executed instruction accounting:
            O(1)

        total campaign:
            O(N)

        coverage-bin state:
            O(20 + 62) = O(1) with respect to campaign length

    Checkpoint retention is configurable. Production long-runs may use
    ``retain_checkpoints=False`` together with ``checkpoint_sink`` so
    checkpoint history can be streamed instead of accumulated in RAM.
    """

    L1_BINS: Tuple[L1Bin, ...] = tuple(
        f"H{i:02d}" for i in range(1, 21)
    )

    L2_BINS: Tuple[L2Bin, ...] = tuple(
        (distance, register)
        for distance in ("d1", "d2")
        for register in range(1, 32)
    )

    def __init__(
        self,
        checkpoint_interval: int = 1000,
        *,
        retain_checkpoints: bool = True,
        checkpoint_sink: Optional[
            Callable[[CoverageCheckpoint], None]
        ] = None,
    ) -> None:
        if (
            isinstance(checkpoint_interval, bool)
            or not isinstance(checkpoint_interval, int)
            or checkpoint_interval <= 0
        ):
            raise ValueError(
                "checkpoint_interval must be a positive integer"
            )

        self.checkpoint_interval = checkpoint_interval
        self.retain_checkpoints = retain_checkpoints
        self.checkpoint_sink = checkpoint_sink

        # Public immutable coverage universes.
        self.l1_bins = self.L1_BINS
        self.l2_bins = self.L2_BINS

        self.l1_state: Dict[L1Bin, BinState] = {
            bin_id: BinState()
            for bin_id in self.l1_bins
        }

        self.l2_state: Dict[L2Bin, BinState] = {
            bin_id: BinState()
            for bin_id in self.l2_bins
        }

        self.checkpoints = []

        self._executed_instructions = 0
        self._last_instruction_id = 0

    @property
    def executed_instructions(self) -> int:
        return self._executed_instructions

    @staticmethod
    def _validate_hit_metadata(
        instruction_id: int,
        cycle: int,
        wall_ns: int,
    ) -> None:
        if (
            isinstance(instruction_id, bool)
            or not isinstance(instruction_id, int)
            or instruction_id <= 0
        ):
            raise ValueError(
                "instruction_id must be a positive integer"
            )

        if (
            isinstance(cycle, bool)
            or not isinstance(cycle, int)
            or cycle < 0
        ):
            raise ValueError(
                "cycle must be a non-negative integer"
            )

        if (
            isinstance(wall_ns, bool)
            or not isinstance(wall_ns, int)
            or wall_ns < 0
        ):
            raise ValueError(
                "wall_ns must be a non-negative integer"
            )

    def _validate_l1_bin(self, bin_id: L1Bin) -> None:
        if bin_id not in self.l1_state:
            raise ValueError(f"invalid L1 bin: {bin_id!r}")

    def _validate_l2_bin(
        self,
        distance: str,
        register: int,
    ) -> L2Bin:
        key = (distance, register)

        if key not in self.l2_state:
            raise ValueError(
                "invalid L2 bin: "
                f"distance={distance!r}, register={register!r}"
            )

        return key

    @staticmethod
    def _record_intent(
        state: BinState,
        *,
        instruction_id: int,
        cycle: int,
        wall_ns: int,
    ) -> None:
        """Record an Intent hit without overwriting first-hit metadata."""

        if not state.intent_seen:
            state.intent_seen = True
            state.intent_first = FirstHit(
                instruction_id=instruction_id,
                cycle=cycle,
                wall_ns=wall_ns,
            )

    @staticmethod
    def _record_validated(
        state: BinState,
        *,
        instruction_id: int,
        cycle: int,
        wall_ns: int,
    ) -> None:
        """Promote a bin to Validated state.

        A validated bin must already have Intent evidence.

        Per-hit correctness itself is intentionally decided outside this
        collector by the validated-attribution layer.
        """

        if not state.intent_seen:
            raise ValueError(
                "cannot record Validated coverage before Intent coverage"
            )

        if not state.validated_seen:
            state.validated_seen = True
            state.validated_first = FirstHit(
                instruction_id=instruction_id,
                cycle=cycle,
                wall_ns=wall_ns,
            )

    def record_l1_intent(
        self,
        bin_id: L1Bin,
        *,
        instruction_id: int,
        cycle: int,
        wall_ns: int,
    ) -> None:
        self._validate_l1_bin(bin_id)
        self._validate_hit_metadata(
            instruction_id,
            cycle,
            wall_ns,
        )

        self._record_intent(
            self.l1_state[bin_id],
            instruction_id=instruction_id,
            cycle=cycle,
            wall_ns=wall_ns,
        )

    def record_l1_validated(
        self,
        bin_id: L1Bin,
        *,
        instruction_id: int,
        cycle: int,
        wall_ns: int,
    ) -> None:
        self._validate_l1_bin(bin_id)
        self._validate_hit_metadata(
            instruction_id,
            cycle,
            wall_ns,
        )

        self._record_validated(
            self.l1_state[bin_id],
            instruction_id=instruction_id,
            cycle=cycle,
            wall_ns=wall_ns,
        )

    def record_l2_intent(
        self,
        distance: str,
        register: int,
        *,
        instruction_id: int,
        cycle: int,
        wall_ns: int,
    ) -> None:
        key = self._validate_l2_bin(distance, register)
        self._validate_hit_metadata(
            instruction_id,
            cycle,
            wall_ns,
        )

        self._record_intent(
            self.l2_state[key],
            instruction_id=instruction_id,
            cycle=cycle,
            wall_ns=wall_ns,
        )

    def record_l2_validated(
        self,
        distance: str,
        register: int,
        *,
        instruction_id: int,
        cycle: int,
        wall_ns: int,
    ) -> None:
        key = self._validate_l2_bin(distance, register)
        self._validate_hit_metadata(
            instruction_id,
            cycle,
            wall_ns,
        )

        self._record_validated(
            self.l2_state[key],
            instruction_id=instruction_id,
            cycle=cycle,
            wall_ns=wall_ns,
        )

    def record_instruction(
        self,
        *,
        instruction_id: int,
        cycle: int,
    ) -> None:
        """Record one accepted executed-program-order instruction."""

        if (
            isinstance(instruction_id, bool)
            or not isinstance(instruction_id, int)
            or instruction_id <= 0
        ):
            raise ValueError(
                "instruction_id must be a positive integer"
            )

        if (
            isinstance(cycle, bool)
            or not isinstance(cycle, int)
            or cycle < 0
        ):
            raise ValueError(
                "cycle must be a non-negative integer"
            )

        expected_id = self._last_instruction_id + 1

        if instruction_id != expected_id:
            raise ValueError(
                "instruction IDs must be strictly contiguous: "
                f"expected {expected_id}, got {instruction_id}"
            )

        self._last_instruction_id = instruction_id
        self._executed_instructions += 1

        if (
            self._executed_instructions
            % self.checkpoint_interval
            == 0
        ):
            self._emit_checkpoint(cycle)

    def _emit_checkpoint(self, cycle: int) -> None:
        checkpoint = CoverageCheckpoint(
            executed_instructions=self._executed_instructions,
            cycle=cycle,
            l1_intent_count=sum(
                state.intent_seen
                for state in self.l1_state.values()
            ),
            l1_validated_count=sum(
                state.validated_seen
                for state in self.l1_state.values()
            ),
            l2_intent_count=sum(
                state.intent_seen
                for state in self.l2_state.values()
            ),
            l2_validated_count=sum(
                state.validated_seen
                for state in self.l2_state.values()
            ),
        )

        if self.retain_checkpoints:
            self.checkpoints.append(checkpoint)

        if self.checkpoint_sink is not None:
            self.checkpoint_sink(checkpoint)

    @staticmethod
    def _deterministic_bin_state(state: BinState):
        """Return deterministic state while excluding wall-clock metadata."""

        intent_first = None
        if state.intent_first is not None:
            intent_first = (
                state.intent_first.instruction_id,
                state.intent_first.cycle,
            )

        validated_first = None
        if state.validated_first is not None:
            validated_first = (
                state.validated_first.instruction_id,
                state.validated_first.cycle,
            )

        return (
            state.intent_seen,
            state.validated_seen,
            intent_first,
            validated_first,
        )

    def deterministic_snapshot(self):
        """Return reproducible coverage state excluding wall-time values."""

        l1 = tuple(
            (
                bin_id,
                self._deterministic_bin_state(
                    self.l1_state[bin_id]
                ),
            )
            for bin_id in self.l1_bins
        )

        l2 = tuple(
            (
                bin_id,
                self._deterministic_bin_state(
                    self.l2_state[bin_id]
                ),
            )
            for bin_id in self.l2_bins
        )

        checkpoints = tuple(
            (
                checkpoint.executed_instructions,
                checkpoint.cycle,
                checkpoint.l1_intent_count,
                checkpoint.l1_validated_count,
                checkpoint.l2_intent_count,
                checkpoint.l2_validated_count,
            )
            for checkpoint in self.checkpoints
        )

        return (
            self._executed_instructions,
            l1,
            l2,
            checkpoints,
        )
