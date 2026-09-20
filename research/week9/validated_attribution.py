"""Week 9 per-hit validated coverage attribution.

This layer combines already-independent verification evidence.

It does not recompute:
- hazard/control realization,
- architectural functional correctness,
- retirement performance correctness.

Frozen promotion contract:

    ValidatedHit
        = IntentHit
        AND ControlPass
        AND RequiredArchitecturePass

Performance evidence is retained independently for telemetry and
consistency checking.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from research.week5.impl.l1_coverage import L1_BIN_IDS
from research.week7.hazard_attribution import HazardAttribution
from research.week8.functional_scoreboard import FunctionalResult
from research.week8.performance_monitor import PerformanceResult


class ValidationStatus(str, Enum):
    INTENDED = "INTENDED"
    REALIZED_CORRECTLY = "REALIZED_CORRECTLY"
    TIMING_MISMATCH = "TIMING_MISMATCH"
    FUNCTIONAL_MISMATCH = "FUNCTIONAL_MISMATCH"
    TIMING_AND_FUNCTIONAL_MISMATCH = (
        "TIMING_AND_FUNCTIONAL_MISMATCH"
    )
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class ValidatedAttributionRecord:
    instruction_id: int

    intent_bin: str
    validated_bin: Optional[str]

    validated: bool
    status: ValidationStatus

    control_pass: Optional[bool]
    functional_pass: Optional[bool]
    performance_pass: Optional[bool]

    failed_control_checks: Tuple[str, ...]
    failed_functional_checks: Tuple[str, ...]

    timing_delta_cycles: Optional[int]


def _validate_identity(
    *,
    bin_id: str,
    instruction_id: int,
    hazard: Optional[HazardAttribution],
    functional: Optional[FunctionalResult],
    performance: Optional[PerformanceResult],
) -> None:
    if bin_id not in L1_BIN_IDS:
        raise ValueError(f"unknown L1 bin: {bin_id!r}")

    if (
        isinstance(instruction_id, bool)
        or not isinstance(instruction_id, int)
        or instruction_id <= 0
    ):
        raise ValueError(
            "instruction_id must be a positive integer"
        )

    if hazard is not None:
        if hazard.bin_id != bin_id:
            raise ValueError(
                "hazard bin does not match Intent bin: "
                f"intent={bin_id}, hazard={hazard.bin_id}"
            )

        if hazard.consumer_instruction_id != instruction_id:
            raise ValueError(
                "hazard instruction_id does not match Intent: "
                f"intent={instruction_id}, "
                f"hazard={hazard.consumer_instruction_id}"
            )

    if (
        functional is not None
        and functional.instruction_id != instruction_id
    ):
        raise ValueError(
            "functional instruction_id does not match Intent: "
            f"intent={instruction_id}, "
            f"functional={functional.instruction_id}"
        )

    if (
        performance is not None
        and performance.instruction_id != instruction_id
    ):
        raise ValueError(
            "performance instruction_id does not match Intent: "
            f"intent={instruction_id}, "
            f"performance={performance.instruction_id}"
        )


def _validate_retire_timing_consistency(
    hazard: HazardAttribution,
    performance: PerformanceResult,
) -> None:
    """Require both timing layers to refer to the same retire evidence."""

    retire_checks = tuple(
        check
        for check in hazard.checks
        if check.name == "retire_cycle"
    )

    if len(retire_checks) != 1:
        raise ValueError(
            "HazardAttribution must contain exactly one "
            "retire_cycle check"
        )

    retire_check = retire_checks[0]

    if retire_check.expected != performance.expected_retire_cycle:
        raise ValueError(
            "inconsistent expected retire cycle between "
            "hazard attribution and performance result"
        )

    if retire_check.observed != performance.observed_retire_cycle:
        raise ValueError(
            "inconsistent observed retire cycle between "
            "hazard attribution and performance result"
        )


def attribute_l1_hit(
    *,
    bin_id: str,
    instruction_id: int,
    hazard: Optional[HazardAttribution] = None,
    functional: Optional[FunctionalResult] = None,
    performance: Optional[PerformanceResult] = None,
) -> ValidatedAttributionRecord:
    """Classify one L1 Intent hit using existing independent evidence."""

    _validate_identity(
        bin_id=bin_id,
        instruction_id=instruction_id,
        hazard=hazard,
        functional=functional,
        performance=performance,
    )

    evidence = (
        hazard,
        functional,
        performance,
    )

    if all(item is None for item in evidence):
        return ValidatedAttributionRecord(
            instruction_id=instruction_id,
            intent_bin=bin_id,
            validated_bin=None,
            validated=False,
            status=ValidationStatus.INTENDED,
            control_pass=None,
            functional_pass=None,
            performance_pass=None,
            failed_control_checks=(),
            failed_functional_checks=(),
            timing_delta_cycles=None,
        )

    if any(item is None for item in evidence):
        return ValidatedAttributionRecord(
            instruction_id=instruction_id,
            intent_bin=bin_id,
            validated_bin=None,
            validated=False,
            status=ValidationStatus.UNRESOLVED,
            control_pass=(
                None if hazard is None else hazard.passed
            ),
            functional_pass=(
                None if functional is None else functional.passed
            ),
            performance_pass=(
                None if performance is None else performance.passed
            ),
            failed_control_checks=(
                ()
                if hazard is None
                else tuple(
                    check.name
                    for check in hazard.failed_checks
                )
            ),
            failed_functional_checks=(
                ()
                if functional is None
                else tuple(
                    check.name
                    for check in functional.failed_checks
                )
            ),
            timing_delta_cycles=(
                None
                if performance is None
                else performance.delta_cycles
            ),
        )

    assert hazard is not None
    assert functional is not None
    assert performance is not None

    _validate_retire_timing_consistency(
        hazard,
        performance,
    )

    control_pass = hazard.passed
    functional_pass = functional.passed
    performance_pass = performance.passed

    # Frozen coverage promotion criterion.
    validated = control_pass and functional_pass

    timing_mismatch = (
        not control_pass
        or not performance_pass
    )
    functional_mismatch = not functional_pass

    if timing_mismatch and functional_mismatch:
        status = (
            ValidationStatus.TIMING_AND_FUNCTIONAL_MISMATCH
        )
    elif timing_mismatch:
        status = ValidationStatus.TIMING_MISMATCH
    elif functional_mismatch:
        status = ValidationStatus.FUNCTIONAL_MISMATCH
    else:
        status = ValidationStatus.REALIZED_CORRECTLY

    return ValidatedAttributionRecord(
        instruction_id=instruction_id,
        intent_bin=bin_id,
        validated_bin=bin_id if validated else None,
        validated=validated,
        status=status,
        control_pass=control_pass,
        functional_pass=functional_pass,
        performance_pass=performance_pass,
        failed_control_checks=tuple(
            check.name
            for check in hazard.failed_checks
        ),
        failed_functional_checks=tuple(
            check.name
            for check in functional.failed_checks
        ),
        timing_delta_cycles=performance.delta_cycles,
    )
