import pytest

from research.week9.coverage_collector import CoverageCollector
from research.week9.validated_attribution import (
    ValidatedAttributionRecord,
    ValidationStatus,
)
from research.week9.coverage_promotion import promote_l1_attribution


def make_record(
    *,
    bin_id="H01",
    instruction_id=2,
    validated=True,
    status=ValidationStatus.REALIZED_CORRECTLY,
):
    return ValidatedAttributionRecord(
        instruction_id=instruction_id,
        intent_bin=bin_id,
        validated_bin=bin_id if validated else None,
        validated=validated,
        status=status,
        control_pass=True if validated else False,
        functional_pass=True,
        performance_pass=True if validated else False,
        failed_control_checks=(),
        failed_functional_checks=(),
        timing_delta_cycles=0 if validated else 1,
    )


def test_realized_hit_promotes_bin():
    collector = CoverageCollector()

    collector.record_l1_intent(
        "H01",
        instruction_id=2,
        cycle=3,
        wall_ns=100,
    )

    promoted = promote_l1_attribution(
        collector,
        make_record(),
        resolution_cycle=6,
        wall_ns=200,
    )

    state = collector.l1_state["H01"]

    assert promoted is True
    assert state.validated_seen is True
    assert state.validated_first.instruction_id == 2
    assert state.validated_first.cycle == 6
    assert state.validated_first.wall_ns == 200


@pytest.mark.parametrize(
    "status",
    [
        ValidationStatus.TIMING_MISMATCH,
        ValidationStatus.FUNCTIONAL_MISMATCH,
        ValidationStatus.TIMING_AND_FUNCTIONAL_MISMATCH,
        ValidationStatus.UNRESOLVED,
        ValidationStatus.INTENDED,
    ],
)
def test_nonvalidated_hit_does_not_promote(status):
    collector = CoverageCollector()

    collector.record_l1_intent(
        "H01",
        instruction_id=2,
        cycle=3,
        wall_ns=100,
    )

    record = make_record(
        validated=False,
        status=status,
    )

    promoted = promote_l1_attribution(
        collector,
        record,
        resolution_cycle=6,
        wall_ns=200,
    )

    assert promoted is False
    assert collector.l1_state["H01"].validated_seen is False


def test_rejected_hit_does_not_block_later_valid_hit():
    collector = CoverageCollector()

    # First intended hit.
    collector.record_l1_intent(
        "H01",
        instruction_id=2,
        cycle=3,
        wall_ns=100,
    )

    rejected = make_record(
        instruction_id=2,
        validated=False,
        status=ValidationStatus.TIMING_MISMATCH,
    )

    assert (
        promote_l1_attribution(
            collector,
            rejected,
            resolution_cycle=6,
            wall_ns=200,
        )
        is False
    )

    # Later occurrence of the same bin.
    collector.record_l1_intent(
        "H01",
        instruction_id=10,
        cycle=20,
        wall_ns=500,
    )

    accepted = make_record(
        instruction_id=10,
        validated=True,
        status=ValidationStatus.REALIZED_CORRECTLY,
    )

    assert (
        promote_l1_attribution(
            collector,
            accepted,
            resolution_cycle=23,
            wall_ns=600,
        )
        is True
    )

    state = collector.l1_state["H01"]

    # Intent first-hit remains the original rejected occurrence.
    assert state.intent_first.instruction_id == 2

    # Validated first-hit is the later successful occurrence.
    assert state.validated_first.instruction_id == 10
    assert state.validated_first.cycle == 23


def test_promotion_requires_prior_intent():
    collector = CoverageCollector()

    with pytest.raises(ValueError):
        promote_l1_attribution(
            collector,
            make_record(),
            resolution_cycle=6,
            wall_ns=200,
        )


def test_malformed_validated_record_is_rejected():
    collector = CoverageCollector()

    collector.record_l1_intent(
        "H01",
        instruction_id=2,
        cycle=3,
        wall_ns=100,
    )

    record = ValidatedAttributionRecord(
        instruction_id=2,
        intent_bin="H01",
        validated_bin=None,
        validated=True,
        status=ValidationStatus.REALIZED_CORRECTLY,
        control_pass=True,
        functional_pass=True,
        performance_pass=True,
        failed_control_checks=(),
        failed_functional_checks=(),
        timing_delta_cycles=0,
    )

    with pytest.raises(ValueError):
        promote_l1_attribution(
            collector,
            record,
            resolution_cycle=6,
            wall_ns=200,
        )


def test_duplicate_success_does_not_overwrite_first_validated_hit():
    collector = CoverageCollector()

    collector.record_l1_intent(
        "H01",
        instruction_id=2,
        cycle=3,
        wall_ns=100,
    )

    promote_l1_attribution(
        collector,
        make_record(instruction_id=2),
        resolution_cycle=6,
        wall_ns=200,
    )

    collector.record_l1_intent(
        "H01",
        instruction_id=10,
        cycle=27,
        wall_ns=800,
    )

    promote_l1_attribution(
        collector,
        make_record(instruction_id=10),
        resolution_cycle=30,
        wall_ns=999,
    )

    state = collector.l1_state["H01"]

    assert state.validated_first.instruction_id == 2
    assert state.validated_first.cycle == 6
    assert state.validated_first.wall_ns == 200

def test_authoritative_validated_hit_can_have_timing_mismatch():
    collector = CoverageCollector()

    collector.record_l1_intent(
        "H01",
        instruction_id=2,
        cycle=2,
        wall_ns=100,
    )

    record = ValidatedAttributionRecord(
        instruction_id=2,
        intent_bin="H01",
        validated_bin="H01",
        validated=True,
        status=ValidationStatus.TIMING_MISMATCH,
        control_pass=True,
        functional_pass=True,
        performance_pass=False,
        failed_control_checks=("retire_cycle",),
        failed_functional_checks=(),
        timing_delta_cycles=1,
    )

    promoted = promote_l1_attribution(
        collector,
        record,
        resolution_cycle=6,
        wall_ns=200,
    )

    assert promoted is True

    state = collector.l1_state["H01"]

    assert state.intent_seen is True
    assert state.validated_seen is True
    assert state.validated_first.instruction_id == 2
    assert state.validated_first.cycle == 6
