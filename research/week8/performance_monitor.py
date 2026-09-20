from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

from research.week7.retire_monitor import RetireEvent
from research.week7.timing_oracle_v1 import TimingExpectationV1


class PerformanceMonitorProtocolError(RuntimeError):
    """Observed retire stream violates the expected timing protocol."""


@dataclass(frozen=True, slots=True)
class PerformanceResult:
    instruction_id: int
    expected_retire_cycle: int
    observed_retire_cycle: int
    delta_cycles: int

    @property
    def passed(self) -> bool:
        return self.delta_cycles == 0

    @property
    def late(self) -> bool:
        return self.delta_cycles > 0

    @property
    def early(self) -> bool:
        return self.delta_cycles < 0


class PerformanceMonitor:
    """
    Week-8 timing/performance checker.

    WHEN is checked here.

    Functional fields such as:
        - regwrite
        - rd
        - wdata
        - store state
        - x0

    are intentionally ignored.

    Timing expectation comes only from Timing Oracle v1.
    """

    def __init__(
        self,
        expectations: Iterable[TimingExpectationV1],
    ) -> None:
        items = tuple(expectations)

        self._expected_by_id: Dict[
            int,
            TimingExpectationV1,
        ] = {}

        for expected_id, item in enumerate(
            items,
            start=1,
        ):
            if item.instruction_id != expected_id:
                raise ValueError(
                    "timing expectation stream must be contiguous: "
                    f"expected instruction_id={expected_id}, "
                    f"got {item.instruction_id}"
                )

            self._expected_by_id[
                item.instruction_id
            ] = item

        self._results_by_id: Dict[
            int,
            PerformanceResult,
        ] = {}

        self._last_observed_id = 0

    @property
    def expected_count(self) -> int:
        return len(self._expected_by_id)

    @property
    def checked_count(self) -> int:
        return len(self._results_by_id)

    @property
    def passed_count(self) -> int:
        return sum(
            result.passed
            for result in self._results_by_id.values()
        )

    @property
    def failed_count(self) -> int:
        return self.checked_count - self.passed_count

    @property
    def late_count(self) -> int:
        return sum(
            result.late
            for result in self._results_by_id.values()
        )

    @property
    def early_count(self) -> int:
        return sum(
            result.early
            for result in self._results_by_id.values()
        )

    @property
    def total_excess_cycles(self) -> int:
        return sum(
            max(0, result.delta_cycles)
            for result in self._results_by_id.values()
        )

    @property
    def max_excess_cycles(self) -> int:
        return max(
            (
                max(0, result.delta_cycles)
                for result in self._results_by_id.values()
            ),
            default=0,
        )

    @property
    def total_early_cycles(self) -> int:
        return sum(
            max(0, -result.delta_cycles)
            for result in self._results_by_id.values()
        )

    @property
    def failed_instruction_ids(self) -> Tuple[int, ...]:
        return tuple(
            instruction_id
            for instruction_id, result
            in sorted(self._results_by_id.items())
            if not result.passed
        )

    @property
    def missing_instruction_ids(self) -> Tuple[int, ...]:
        return tuple(
            instruction_id
            for instruction_id
            in sorted(self._expected_by_id)
            if instruction_id not in self._results_by_id
        )

    @property
    def complete(self) -> bool:
        return self.checked_count == self.expected_count

    @property
    def overall_pass(self) -> bool:
        return self.complete and self.failed_count == 0

    def _require_expected(
        self,
        instruction_id: int,
    ) -> TimingExpectationV1:
        try:
            return self._expected_by_id[instruction_id]
        except KeyError as exc:
            raise PerformanceMonitorProtocolError(
                "retirement has no matching timing expectation: "
                f"instruction_id={instruction_id}"
            ) from exc

    def observe_retire(
        self,
        retire: RetireEvent,
    ) -> PerformanceResult:
        """
        Compare one observed retirement against Timing Oracle v1.

        Only:
            instruction_id
            cycle

        affect the performance verdict.
        """

        instruction_id = retire.instruction_id

        expected = self._require_expected(
            instruction_id
        )

        if instruction_id in self._results_by_id:
            raise PerformanceMonitorProtocolError(
                "duplicate performance observation for "
                f"instruction_id={instruction_id}"
            )

        expected_next_id = self._last_observed_id + 1

        if instruction_id != expected_next_id:
            raise PerformanceMonitorProtocolError(
                "performance retire order violation: "
                f"expected instruction_id={expected_next_id}, "
                f"got {instruction_id}"
            )

        delta = (
            retire.cycle
            - expected.retire_cycle
        )

        result = PerformanceResult(
            instruction_id=instruction_id,
            expected_retire_cycle=expected.retire_cycle,
            observed_retire_cycle=retire.cycle,
            delta_cycles=delta,
        )

        self._results_by_id[instruction_id] = result
        self._last_observed_id = instruction_id

        return result
