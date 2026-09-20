from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from research.week8.functional_scoreboard import FunctionalResult
from research.week8.performance_monitor import PerformanceResult


class CrossVerdictProtocolError(RuntimeError):
    """Raised when functional and timing results cannot be correlated."""


class CrossVerdictClass(str, Enum):
    CORRECT_ON_TIME = "CORRECT_ON_TIME"
    FUNCTIONAL_ONLY_FAIL = "FUNCTIONAL_ONLY_FAIL"
    PERFORMANCE_ONLY_FAIL = "PERFORMANCE_ONLY_FAIL"
    FUNCTIONAL_AND_PERFORMANCE_FAIL = (
        "FUNCTIONAL_AND_PERFORMANCE_FAIL"
    )


@dataclass(frozen=True, slots=True)
class CrossVerdict:
    instruction_id: int

    functional_pass: bool
    performance_pass: bool

    classification: CrossVerdictClass

    functional_failed_checks: Tuple[str, ...]
    timing_delta_cycles: int

    @property
    def overall_pass(self) -> bool:
        return (
            self.functional_pass
            and self.performance_pass
        )


def combine_verdicts(
    functional: FunctionalResult,
    performance: PerformanceResult,
) -> CrossVerdict:
    """
    Combine independent WHAT and WHEN verdicts.

    This function does not recompute either verdict.

    Functional correctness comes only from FunctionalResult.
    Performance correctness comes only from PerformanceResult.
    """

    if (
        functional.instruction_id
        != performance.instruction_id
    ):
        raise CrossVerdictProtocolError(
            "functional/performance instruction_id mismatch: "
            f"functional={functional.instruction_id}, "
            f"performance={performance.instruction_id}"
        )

    functional_pass = functional.passed
    performance_pass = performance.passed

    if functional_pass and performance_pass:
        classification = CrossVerdictClass.CORRECT_ON_TIME

    elif not functional_pass and performance_pass:
        classification = (
            CrossVerdictClass.FUNCTIONAL_ONLY_FAIL
        )

    elif functional_pass and not performance_pass:
        classification = (
            CrossVerdictClass.PERFORMANCE_ONLY_FAIL
        )

    else:
        classification = (
            CrossVerdictClass.FUNCTIONAL_AND_PERFORMANCE_FAIL
        )

    return CrossVerdict(
        instruction_id=functional.instruction_id,
        functional_pass=functional_pass,
        performance_pass=performance_pass,
        classification=classification,
        functional_failed_checks=tuple(
            check.name
            for check in functional.failed_checks
        ),
        timing_delta_cycles=performance.delta_cycles,
    )
