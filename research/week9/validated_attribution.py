"""Week 9 per-hit validated coverage attribution.

Authoritative coverage promotion semantics come from the frozen Week-5
L1ValidatedCoverageCollector.

This module does NOT recompute Validated Coverage from Week-8 functional
or performance verdicts.

Frozen promotion contract:

    ValidatedHit
        = IntentHit
        AND frozen Week-5 control realization PASS
        AND frozen Week-5 required architectural realization PASS

Week-7 HazardAttribution and Week-8 PerformanceResult remain independent
diagnostic/timing evidence. They may change the Week-9 status classification,
but must not redefine a frozen Week-5 validation outcome.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from research.week5.impl.l1_coverage import L1_BIN_IDS
from research.week5.impl.validated_coverage import (
    L1ValidationOutcome,
)
from research.week7.hazard_attribution import (
    HazardAttribution,
)
from research.week8.performance_monitor import (
    PerformanceResult,
)


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

    # control_pass is the authoritative frozen Week-5 control result.
    control_pass: Optional[bool]

    # Kept as functional_pass for the Week-9 logging contract.
    # Semantically this is the frozen required architectural realization
    # result carried by L1ValidationOutcome.architectural_passed.
    functional_pass: Optional[bool]

    # Independent Week-8 retirement-performance verdict.
    performance_pass: Optional[bool]

    # Detailed Week-7 timing/hazard diagnostics.
    failed_control_checks: Tuple[str, ...]

    # Frozen architectural failures encoded as:
    #     "<instruction_id>:<kind>"
    failed_functional_checks: Tuple[str, ...]

    timing_delta_cycles: Optional[int]


def _validate_positive_instruction_id(
    instruction_id: int,
) -> None:
    if (
        isinstance(instruction_id, bool)
        or not isinstance(instruction_id, int)
        or instruction_id <= 0
    ):
        raise ValueError(
            "instruction_id must be a positive integer"
        )


def _validate_validation_consistency(
    validation: L1ValidationOutcome,
) -> None:
    """Reject malformed manually-constructed validation outcomes."""

    if validation.validated:
        if not validation.control_passed:
            raise ValueError(
                "validated L1 outcome requires "
                "control_passed=True"
            )

        if validation.architectural_passed is not True:
            raise ValueError(
                "validated L1 outcome requires "
                "architectural_passed=True"
            )

    if (
        validation.control_passed is False
        and validation.validated
    ):
        raise ValueError(
            "control-failed L1 outcome cannot be validated"
        )

    if (
        validation.architectural_passed is False
        and validation.validated
    ):
        raise ValueError(
            "architecturally failed L1 outcome "
            "cannot be validated"
        )


def _validate_identity(
    *,
    bin_id: str,
    instruction_id: int,
    validation: Optional[L1ValidationOutcome],
    hazard: Optional[HazardAttribution],
    performance: Optional[PerformanceResult],
) -> None:
    if bin_id not in L1_BIN_IDS:
        raise ValueError(
            f"unknown L1 bin: {bin_id!r}"
        )

    _validate_positive_instruction_id(
        instruction_id
    )

    if validation is not None:
        _validate_validation_consistency(
            validation
        )

        if validation.bin_id != bin_id:
            raise ValueError(
                "validation bin does not match Intent bin: "
                f"intent={bin_id}, "
                f"validation={validation.bin_id}"
            )

        if (
            validation.consumer_instruction_index
            != instruction_id
        ):
            raise ValueError(
                "validation instruction_id does not "
                "match Intent: "
                f"intent={instruction_id}, "
                "validation="
                f"{validation.consumer_instruction_index}"
            )

    if hazard is not None:
        if hazard.bin_id != bin_id:
            raise ValueError(
                "hazard bin does not match Intent bin: "
                f"intent={bin_id}, "
                f"hazard={hazard.bin_id}"
            )

        if (
            hazard.consumer_instruction_id
            != instruction_id
        ):
            raise ValueError(
                "hazard instruction_id does not "
                "match Intent: "
                f"intent={instruction_id}, "
                f"hazard="
                f"{hazard.consumer_instruction_id}"
            )

    if performance is not None:
        if performance.instruction_id != instruction_id:
            raise ValueError(
                "performance instruction_id does not "
                "match Intent: "
                f"intent={instruction_id}, "
                f"performance="
                f"{performance.instruction_id}"
            )

    # When both authoritative validation and detailed hazard attribution
    # exist, they must refer to exactly the same concrete L1 hit.
    if validation is not None and hazard is not None:
        if (
            tuple(validation.producer_instruction_indices)
            != tuple(hazard.producer_instruction_ids)
        ):
            raise ValueError(
                "validation and hazard producer identities "
                "do not match"
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
            "HazardAttribution must contain exactly "
            "one retire_cycle check"
        )

    retire_check = retire_checks[0]

    if (
        retire_check.expected
        != performance.expected_retire_cycle
    ):
        raise ValueError(
            "inconsistent expected retire cycle between "
            "hazard attribution and performance result"
        )

    if (
        retire_check.observed
        != performance.observed_retire_cycle
    ):
        raise ValueError(
            "inconsistent observed retire cycle between "
            "hazard attribution and performance result"
        )


def _failed_architectural_checks(
    validation: Optional[L1ValidationOutcome],
) -> Tuple[str, ...]:
    if validation is None:
        return ()

    return tuple(
        f"{instruction_id}:{kind}"
        for instruction_id, kind
        in validation.failed_architectural_checks
    )


def _failed_hazard_checks(
    hazard: Optional[HazardAttribution],
) -> Tuple[str, ...]:
    if hazard is None:
        return ()

    return tuple(
        check.name
        for check in hazard.failed_checks
    )


def attribute_l1_hit(
    *,
    bin_id: str,
    instruction_id: int,
    validation: Optional[
        L1ValidationOutcome
    ] = None,
    hazard: Optional[
        HazardAttribution
    ] = None,
    performance: Optional[
        PerformanceResult
    ] = None,
) -> ValidatedAttributionRecord:
    """Classify one L1 Intent hit using authoritative frozen evidence.

    Coverage promotion is taken ONLY from ``validation.validated``.

    Hazard/performance evidence may affect the Week-9 diagnostic status,
    but cannot retroactively redefine frozen Week-5 Validated Coverage.
    """

    _validate_identity(
        bin_id=bin_id,
        instruction_id=instruction_id,
        validation=validation,
        hazard=hazard,
        performance=performance,
    )

    evidence = (
        validation,
        hazard,
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

    authoritative_validated = (
        False
        if validation is None
        else validation.validated
    )

    control_pass = (
        None
        if validation is None
        else validation.control_passed
    )

    architectural_pass = (
        None
        if validation is None
        else validation.architectural_passed
    )

    performance_pass = (
        None
        if performance is None
        else performance.passed
    )

    failed_control_checks = (
        _failed_hazard_checks(hazard)
    )

    failed_functional_checks = (
        _failed_architectural_checks(validation)
    )

    timing_delta_cycles = (
        None
        if performance is None
        else performance.delta_cycles
    )

    # Full Week-9 status classification requires all three independent
    # evidence layers. Coverage promotion itself does not.
    if any(item is None for item in evidence):
        return ValidatedAttributionRecord(
            instruction_id=instruction_id,
            intent_bin=bin_id,
            validated_bin=(
                bin_id
                if authoritative_validated
                else None
            ),
            validated=authoritative_validated,
            status=ValidationStatus.UNRESOLVED,
            control_pass=control_pass,
            functional_pass=architectural_pass,
            performance_pass=performance_pass,
            failed_control_checks=(
                failed_control_checks
            ),
            failed_functional_checks=(
                failed_functional_checks
            ),
            timing_delta_cycles=(
                timing_delta_cycles
            ),
        )

    assert validation is not None
    assert hazard is not None
    assert performance is not None

    _validate_retire_timing_consistency(
        hazard,
        performance,
    )

    # Timing/control status contains:
    # - frozen Week-5 control realization, and
    # - additional Week-7/Week-8 timing evidence.
    #
    # Only the first item participates in frozen coverage promotion.
    timing_mismatch = (
        not validation.control_passed
        or not hazard.passed
        or not performance.passed
    )

    functional_mismatch = (
        validation.architectural_passed is False
    )

    if timing_mismatch and functional_mismatch:
        status = (
            ValidationStatus
            .TIMING_AND_FUNCTIONAL_MISMATCH
        )
    elif timing_mismatch:
        status = ValidationStatus.TIMING_MISMATCH
    elif functional_mismatch:
        status = (
            ValidationStatus.FUNCTIONAL_MISMATCH
        )
    else:
        status = (
            ValidationStatus.REALIZED_CORRECTLY
        )

    return ValidatedAttributionRecord(
        instruction_id=instruction_id,
        intent_bin=bin_id,
        validated_bin=(
            bin_id
            if authoritative_validated
            else None
        ),
        validated=authoritative_validated,
        status=status,
        control_pass=validation.control_passed,
        functional_pass=(
            validation.architectural_passed
        ),
        performance_pass=performance.passed,
        failed_control_checks=(
            failed_control_checks
        ),
        failed_functional_checks=(
            failed_functional_checks
        ),
        timing_delta_cycles=(
            performance.delta_cycles
        ),
    )
