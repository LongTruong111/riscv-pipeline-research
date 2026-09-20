import pytest

from research.week7.hazard_attribution import (
    AttributionCheck,
    HazardAttribution,
)
from research.week8.functional_scoreboard import (
    FunctionalCheck,
    FunctionalResult,
)
from research.week8.performance_monitor import PerformanceResult

from research.week9.validated_attribution import (
    ValidationStatus,
    attribute_l1_hit,
)

def make_hazard(
    *,
    bin_id="H01",
    instruction_id=2,
    control_pass=True,
    retire_delta=0,
):
    checks = (
        AttributionCheck(
            name="forward_a",
            expected=2,
            observed=2 if control_pass else 1,
        ),
        AttributionCheck(
            name="retire_cycle",
            expected=5,
            observed=5 + retire_delta,
        ),
    )

    return HazardAttribution(
        bin_id=bin_id,
        consumer_instruction_id=instruction_id,
        producer_instruction_ids=(1,),
        matched_sources=("RS1",),
        checks=checks,
    )

def make_functional(
    *,
    instruction_id=2,
    passed=True,
):
    check = FunctionalCheck(
        name="write_data",
        expected=10,
        observed=10 if passed else 99,
    )

    return FunctionalResult(
        instruction_id=instruction_id,
        checks=(check,),
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
    assert result.status == ValidationStatus.INTENDED


def test_partial_validation_evidence_is_unresolved():
    result = attribute_l1_hit(
        bin_id="H01",
        instruction_id=2,
        hazard=make_hazard(),
    )

    assert result.validated is False
    assert result.status == ValidationStatus.UNRESOLVED


def test_all_pass_promotes_validated_bin():
    result = attribute_l1_hit(
        bin_id="H01",
        instruction_id=2,
        hazard=make_hazard(),
        functional=make_functional(),
        performance=make_performance(),
    )

    assert result.control_pass is True
    assert result.functional_pass is True
    assert result.performance_pass is True

    assert result.validated is True
    assert result.validated_bin == "H01"
    assert result.status == ValidationStatus.REALIZED_CORRECTLY

def test_control_failure_is_timing_mismatch():
    result = attribute_l1_hit(
        bin_id="H19",
        instruction_id=2,
        hazard=make_hazard(
            bin_id="H19",
            control_pass=False,
        ),
        functional=make_functional(),
        performance=make_performance(),
    )

    assert result.control_pass is False
    assert result.functional_pass is True
    assert result.performance_pass is True

    assert result.validated is False
    assert result.validated_bin is None
    assert result.status == ValidationStatus.TIMING_MISMATCH

def test_retire_timing_failure_is_timing_mismatch():
    result = attribute_l1_hit(
        bin_id="H01",
        instruction_id=2,
        hazard=make_hazard(
            retire_delta=1,
        ),
        functional=make_functional(),
        performance=make_performance(delta=1),
    )

    assert result.control_pass is False
    assert result.functional_pass is True
    assert result.performance_pass is False

    assert result.validated is False
    assert result.validated_bin is None
    assert result.status == ValidationStatus.TIMING_MISMATCH

def test_inconsistent_retire_timing_evidence_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            hazard=make_hazard(
                retire_delta=0,
            ),
            functional=make_functional(),
            performance=make_performance(delta=1),
        )

def test_functional_failure_only():
    result = attribute_l1_hit(
        bin_id="H11",
        instruction_id=2,
        hazard=make_hazard(
            bin_id="H11",
        ),
        functional=make_functional(
    	    passed=False,
        ),
        performance=make_performance(),
    )

    assert result.control_pass is True
    assert result.functional_pass is False
    assert result.performance_pass is True

    assert result.validated is False
    assert result.status == ValidationStatus.FUNCTIONAL_MISMATCH

def test_functional_and_timing_failure():
    result = attribute_l1_hit(
        bin_id="H01",
        instruction_id=2,
        hazard=make_hazard(
            control_pass=False,
            retire_delta=1,
        ),
        functional=make_functional(
            passed=False,
        ),
        performance=make_performance(delta=1),
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
        hazard=make_hazard(
            control_pass=False,
            retire_delta=1,
        ),
        functional=make_functional(
            passed=False,
        ),
        performance=make_performance(delta=1),
    )

    assert result.failed_control_checks == (
        "forward_a",
        "retire_cycle",
    )
    assert result.failed_functional_checks == ("write_data",)
    assert result.timing_delta_cycles == 1

def test_hazard_instruction_id_mismatch_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            hazard=make_hazard(
                instruction_id=3,
            ),
            functional=make_functional(),
            performance=make_performance(),
        )


def test_functional_instruction_id_mismatch_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            hazard=make_hazard(),
            functional=make_functional(
                instruction_id=3,
            ),
            performance=make_performance(),
        )


def test_performance_instruction_id_mismatch_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            hazard=make_hazard(),
            functional=make_functional(),
            performance=make_performance(
                instruction_id=3,
            ),
        )


def test_hazard_bin_mismatch_is_rejected():
    with pytest.raises(ValueError):
        attribute_l1_hit(
            bin_id="H01",
            instruction_id=2,
            hazard=make_hazard(
                bin_id="H02",
            ),
            functional=make_functional(),
            performance=make_performance(),
        )
