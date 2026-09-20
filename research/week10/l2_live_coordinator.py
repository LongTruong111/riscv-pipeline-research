"""Bounded live coordination for authoritative L2 Validated coverage."""

from typing import Tuple

from research.week5.impl.coverage_model import (
    L2CoverageCollector,
    L2Hit,
)
from research.week5.impl.execution_event import ExecutionEvent
from research.week7.timing_oracle_v1 import TimingExpectationV1
from research.week9.coverage_collector import CoverageCollector

from research.week10.l2_realization import (
    L2ValidationOutcome,
    L2ValidatedCoverageChecker,
    check_l2_source_control,
)


class L2LiveCoordinator:
    """Connect concrete L2 realization outcomes to coverage promotion.

    Retained state belongs to L2ValidatedCoverageChecker and is bounded
    by unresolved architectural evidence rather than campaign length.
    """

    def __init__(
        self,
        *,
        l2_coverage: L2CoverageCollector,
        coverage: CoverageCollector,
    ) -> None:
        if not isinstance(
            l2_coverage,
            L2CoverageCollector,
        ):
            raise TypeError(
                "l2_coverage must be L2CoverageCollector"
            )

        if not isinstance(
            coverage,
            CoverageCollector,
        ):
            raise TypeError(
                "coverage must be CoverageCollector"
            )

        self.l2_coverage = l2_coverage
        self.coverage = coverage
        self.checker = L2ValidatedCoverageChecker()

    @property
    def pending_hit_count(self) -> int:
        return self.checker.pending_hits

    @property
    def architectural_cache_entries(self) -> int:
        return self.checker.architectural_cache_entries

    @property
    def validated_hit_count(self) -> int:
        return self.checker.validated_hit_count

    @property
    def rejected_hit_count(self) -> int:
        return self.checker.rejected_hit_count

    def _handle_outcomes(
        self,
        outcomes: Tuple[L2ValidationOutcome, ...],
        *,
        cycle: int,
        wall_ns: int,
    ) -> Tuple[L2ValidationOutcome, ...]:
        for outcome in outcomes:
            if not outcome.validated:
                continue

            hit = outcome.hit

            # Frozen Week-5 L2 state promotion.
            self.l2_coverage.promote_validated(
                (hit,)
            )

            # Week-9 deterministic metadata/telemetry state.
            self.coverage.record_l2_validated(
                f"d{hit.distance}",
                hit.register,
                instruction_id=(
                    hit.consumer_instruction_index
                ),
                cycle=cycle,
                wall_ns=wall_ns,
            )

        return outcomes

    def register_hit(
        self,
        hit: L2Hit,
        *,
        producer: ExecutionEvent,
        consumer: ExecutionEvent,
        expectation: TimingExpectationV1,
        cycle: int,
        wall_ns: int,
    ) -> Tuple[L2ValidationOutcome, ...]:
        """Record Intent and begin authoritative realization checking."""

        self.coverage.record_l2_intent(
            f"d{hit.distance}",
            hit.register,
            instruction_id=(
                hit.consumer_instruction_index
            ),
            cycle=cycle,
            wall_ns=wall_ns,
        )

        control = check_l2_source_control(
            hit,
            consumer,
            expectation,
        )

        outcomes = self.checker.register_hit(
            hit,
            control=control,
            producer=producer,
            consumer=consumer,
        )

        return self._handle_outcomes(
            outcomes,
            cycle=cycle,
            wall_ns=wall_ns,
        )

    def record_architectural_result(
        self,
        *,
        instruction_id: int,
        kind: str,
        passed: bool,
        cycle: int,
        wall_ns: int,
    ) -> Tuple[L2ValidationOutcome, ...]:
        outcomes = (
            self.checker.record_architectural_result(
                instruction_id=instruction_id,
                kind=kind,
                passed=passed,
            )
        )

        return self._handle_outcomes(
            outcomes,
            cycle=cycle,
            wall_ns=wall_ns,
        )

    def record_successor_pc(
        self,
        *,
        predecessor_instruction_id: int,
        expected_next_pc: int,
        successor: ExecutionEvent,
        cycle: int,
        wall_ns: int,
    ) -> Tuple[L2ValidationOutcome, ...]:
        """Resolve predecessor next-PC using the next accepted event.

        Golden next_pc is deliberately not truncated to DUT PC width.
        """

        if predecessor_instruction_id <= 0:
            raise ValueError(
                "predecessor_instruction_id must be positive"
            )

        if (
            successor.instruction_index
            != predecessor_instruction_id + 1
        ):
            raise ValueError(
                "successor must be the next executed instruction"
            )

        passed = successor.pc == expected_next_pc

        return self.record_architectural_result(
            instruction_id=predecessor_instruction_id,
            kind="next_pc",
            passed=passed,
            cycle=cycle,
            wall_ns=wall_ns,
        )

    def prune(
        self,
        *,
        latest_instruction_id: int,
    ) -> None:
        self.checker.prune(
            latest_instruction_id=latest_instruction_id
        )
