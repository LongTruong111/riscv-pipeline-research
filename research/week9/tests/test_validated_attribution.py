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
    producer_ids=(1,),
    control_pass=True,
    architectural_pass=True,
    validated=None,
    failed_arch=(),
):
    if validated is None:
        validated = (
            control_pass
            and architectural_pass is True
        )

    return L1ValidationOutcome(
        bin_id=bin_id,
        consumer_instruction_index=instruction_id,
        producer_instruction_indices=tuple(
            producer_ids
        ),
        control_passed=control_pass,
        architectural_passed=architectural_pass,
        validated=validated,
        failed_architectural_checks=tuple(
            failed_arch
        ),
    )


def make_hazard(
    *,
    bin_id="H01",
    instruction_id=2,
    producer_ids=(1,),
    hazard_pass=True,
    retire_delta=0,
):
    return HazardAttribution(
        bin_id=bin_id,
        consumer_instruction_id=instruction_id,
        producer_instruction_ids=tuple(
            producer_ids
        ),
        matched_sources=("RS1",),
        checks=(
            AttributionCheck(
                name="forward_a",
                expected=2,
                observed=(
                    2
                    if hazard_pass
                    else 1
                ),
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


def test_intent_without_validation_evidence_is_intended():
    result = attribute_l1_hit(
        bin_id="H01",
        instruction_id=2,
    )

    assert result.intent_bin == "H01"
    assert result.validated_bin is None
    assert result.validated is False

    assert (
        result.status
        == ValidationStatus.INTENDED
    )


def test_partial_validation_evidence_is_unresolved():
    result = attribute_l1_hit(
        bin_id="H01",
        instruction_id=2,
        hazard=make_hazard(),
    )

    assert result.validated is False
    assert result.validated_bin is None

    assert (
        result.status
        == ValidationStatus.UNRESOLVED
    )


def test_authoritative_all_pass_promotes_validated_bin():
    result = attribute_l1_hit(
        bin_id="H01",
        instruction_id=2,
        validation=make_validation(),
        hazard=make_hazard(),
        performance=make_performance(),
    )

    assert result.control_pass is True
    assert result.functional_pass is True
    assert result.performance_pass is True

    assert result.validated is True
    assert result.validated_bin == "H01"

    assert (
        result.status
        == ValidationStatus.REALIZED_CORRECTLY
    )


def test_frozen_control_failure_is_timing_mismatch():
    result = attribute_l1_hit(
        bin_id="H19",
        instruction_id=2,
        validation=make_validation(
            bin_id="H19",
            control_pass=False,
            architectural_pass=None,
            validated=False,
        ),
        hazard=make_hazard(
            bin_id="H19",
        ),
        performance=make_performance(),
    )

    assert result.control_pass is False
    assert result.functional_pass is None
    assert result.performance_pass is True

    assert result.validated is False
    assert result.validated_bin is None

    assert (
        result.status
        == ValidationStatus.TIMING_MISMATCH
    )


def test_additional_retire_timing_failure_does_not_remove_frozen_validation():
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

    # Frozen Week-5 coverage remains authoritative.
    assert result.validated is True
    assert result.validated_bin == "H01"

    # Week-9 diagnostic status still exposes the timing failure.
    assert result.control_pass is True
    assert result.functional_pass is True
    assert result.performance_pass is False

    assert (
        result.status
        == ValidationStatus.TIMING_MISMATCH
    )


def test_inconsistent_retire_timing_evidence_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            validation=make_validation(),
            hazard=make_hazard(
                retire_delta=0,
            ),
            performance=make_performance(
                delta=1,
            ),
        )


def test_architectural_failure_only():
    result = attribute_l1_hit(
        bin_id="H11",
        instruction_id=2,
        validation=make_validation(
            bin_id="H11",
            architectural_pass=False,
            validated=False,
            failed_arch=(
                (2, "writeback"),
            ),
        ),
        hazard=make_hazard(
            bin_id="H11",
        ),
        performance=make_performance(),
    )

    assert result.control_pass is True
    assert result.functional_pass is False
    assert result.performance_pass is True

    assert result.validated is False
    assert result.validated_bin is None

    assert (
        result.status
        == ValidationStatus.FUNCTIONAL_MISMATCH
    )


def test_architectural_and_timing_failure():
    result = attribute_l1_hit(
        bin_id="H01",
        instruction_id=2,
        validation=make_validation(
            architectural_pass=False,
            validated=False,
            failed_arch=(
                (2, "writeback"),
            ),
        ),
        hazard=make_hazard(
            hazard_pass=False,
            retire_delta=1,
        ),
        performance=make_performance(
            delta=1,
        ),
    )

    assert result.validated is False

    assert (
        result.status
        == ValidationStatus.TIMING_AND_FUNCTIONAL_MISMATCH
    )


def test_failed_check_names_are_preserved():
    result = attribute_l1_hit(
        bin_id="H01",
        instruction_id=2,
        validation=make_validation(
            architectural_pass=False,
            validated=False,
            failed_arch=(
                (1, "writeback"),
                (2, "store"),
            ),
        ),
        hazard=make_hazard(
            hazard_pass=False,
            retire_delta=1,
        ),
        performance=make_performance(
            delta=1,
        ),
    )

    assert result.failed_control_checks == (
        "forward_a",
        "retire_cycle",
    )

    assert result.failed_functional_checks == (
        "1:writeback",
        "2:store",
    )

    assert result.timing_delta_cycles == 1


def test_validation_instruction_id_mismatch_is_rejected():
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


def test_hazard_instruction_id_mismatch_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            validation=make_validation(),
            hazard=make_hazard(
                instruction_id=3,
            ),
            performance=make_performance(),
        )


def test_performance_instruction_id_mismatch_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            validation=make_validation(),
            hazard=make_hazard(),
            performance=make_performance(
                instruction_id=3,
            ),
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


def test_hazard_bin_mismatch_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            validation=make_validation(),
            hazard=make_hazard(
                bin_id="H02",
            ),
            performance=make_performance(),
        )


def test_producer_identity_mismatch_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            validation=make_validation(
                producer_ids=(1,),
            ),
            hazard=make_hazard(
                producer_ids=(3,),
            ),
            performance=make_performance(),
        )


def test_malformed_validated_outcome_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            validation=make_validation(
                control_pass=True,
                architectural_pass=False,
                validated=True,
            ),
            hazard=make_hazard(),
            performance=make_performance(),
        )
