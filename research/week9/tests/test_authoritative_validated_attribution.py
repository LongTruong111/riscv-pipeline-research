import pytest

from research.week5.impl.validated_coverage import (
    L1ValidationOutcome,
)
from research.week7.hazard_attribution import (
    AttributionCheck,
    HazardAttribution,
)
from research.week8.performance_monitor import (
    PerformanceResult,
)
from research.week9.validated_attribution import (
    ValidationStatus,
    attribute_l1_hit,
)


def make_validation(
    *,
    bin_id="H01",
    instruction_id=2,
    control_passed=True,
    architectural_passed=True,
    validated=True,
    failed_arch=(),
):
    return L1ValidationOutcome(
        bin_id=bin_id,
        consumer_instruction_index=instruction_id,
        producer_instruction_indices=(1,),
        control_passed=control_passed,
        architectural_passed=architectural_passed,
        validated=validated,
        failed_architectural_checks=tuple(failed_arch),
    )


def make_hazard(
    *,
    bin_id="H01",
    instruction_id=2,
    retire_delta=0,
):
    return HazardAttribution(
        bin_id=bin_id,
        consumer_instruction_id=instruction_id,
        producer_instruction_ids=(1,),
        matched_sources=("RS1",),
        checks=(
            AttributionCheck(
                name="forward_a",
                expected=2,
                observed=2,
            ),
            AttributionCheck(
                name="retire_cycle",
                expected=5,
                observed=5 + retire_delta,
            ),
        ),
    )


def make_performance(
    *,
    instruction_id=2,
    delta=0,
):
    return PerformanceResult(
        instruction_id=instruction_id,
        expected_retire_cycle=5,
        observed_retire_cycle=5 + delta,
        delta_cycles=delta,
    )


def test_authoritative_validation_pass_promotes():
    result = attribute_l1_hit(
        bin_id="H01",
        instruction_id=2,
        validation=make_validation(),
        hazard=make_hazard(),
        performance=make_performance(),
    )

    assert result.validated is True
    assert result.validated_bin == "H01"
    assert result.control_pass is True
    assert result.functional_pass is True
    assert result.performance_pass is True
    assert result.status == ValidationStatus.REALIZED_CORRECTLY


def test_producer_architectural_failure_blocks_promotion():
    result = attribute_l1_hit(
        bin_id="H01",
        instruction_id=2,
        validation=make_validation(
            architectural_passed=False,
            validated=False,
            failed_arch=((1, "writeback"),),
        ),
        hazard=make_hazard(),
        performance=make_performance(),
    )

    assert result.validated is False
    assert result.validated_bin is None
    assert result.control_pass is True
    assert result.functional_pass is False
    assert result.status == ValidationStatus.FUNCTIONAL_MISMATCH

    assert "1:writeback" in result.failed_functional_checks


def test_frozen_control_failure_blocks_promotion():
    result = attribute_l1_hit(
        bin_id="H19",
        instruction_id=2,
        validation=make_validation(
            bin_id="H19",
            control_passed=False,
            architectural_passed=None,
            validated=False,
        ),
        hazard=make_hazard(
            bin_id="H19",
        ),
        performance=make_performance(),
    )

    assert result.validated is False
    assert result.control_pass is False
    assert result.status == ValidationStatus.TIMING_MISMATCH


def test_performance_mismatch_does_not_redefine_frozen_coverage():
    """
    Retirement-performance evidence is independent of the frozen
    Week-5 Validated-Coverage promotion rule.

    A later performance mismatch may classify the observation as timing
    mismatched, but must not retroactively redefine an authoritative
    Week-5 validation outcome.
    """

    result = attribute_l1_hit(
        bin_id="H01",
        instruction_id=2,
        validation=make_validation(),
        hazard=make_hazard(
            retire_delta=1,
        ),
        performance=make_performance(
            delta=1,
        ),
    )

    assert result.validated is True
    assert result.validated_bin == "H01"

    assert result.control_pass is True
    assert result.functional_pass is True
    assert result.performance_pass is False

    assert result.status == ValidationStatus.TIMING_MISMATCH


def test_validation_identity_mismatch_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            validation=make_validation(
                instruction_id=3,
            ),
            hazard=make_hazard(),
            performance=make_performance(),
        )


def test_validation_bin_mismatch_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            validation=make_validation(
                bin_id="H02",
            ),
            hazard=make_hazard(),
            performance=make_performance(),
        )
