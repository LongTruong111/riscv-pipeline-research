import pytest

from research.week12.telemetry.first_failure import (
    FailureRecord,
    FirstFailureRecorder,
)


def failure(
    *,
    instruction_id=5,
    cycle=8,
    checker="functional",
    check_name="write_data",
    expected=7,
    observed=3,
):
    return FailureRecord(
        instruction_id=instruction_id,
        cycle=cycle,
        pc=(instruction_id - 1) * 4,
        instruction=0x002081B3,
        checker=checker,
        check_name=check_name,
        expected=expected,
        observed=observed,
        forward_a=0b10,
        forward_b=0b00,
        stall_cycles_before_accept=0,
    )


def test_initial_state_is_empty():
    recorder = FirstFailureRecorder()

    assert recorder.empty
    assert recorder.first_failure is None
    assert recorder.first_control_failure is None
    assert recorder.first_functional_failure is None
    assert recorder.first_performance_failure is None


def test_first_failure_is_immutable():
    recorder = FirstFailureRecorder()

    first = failure(
        instruction_id=5,
        cycle=8,
    )
    later = failure(
        instruction_id=9,
        cycle=12,
        observed=99,
    )

    assert recorder.record(
        "functional",
        first,
    )

    assert not recorder.record(
        "functional",
        later,
    )

    assert recorder.first_failure == first
    assert recorder.first_functional_failure == first


def test_global_first_failure_is_first_recorded_event():
    recorder = FirstFailureRecorder()

    control = failure(
        instruction_id=5,
        cycle=8,
        checker="control",
        check_name="forward_a",
        expected=0b10,
        observed=0b00,
    )

    functional = failure(
        instruction_id=5,
        cycle=9,
    )

    assert recorder.record(
        "control",
        control,
    )

    assert recorder.record(
        "functional",
        functional,
    )

    assert recorder.first_failure == control
    assert recorder.first_control_failure == control
    assert recorder.first_functional_failure == functional


def test_snapshot_is_reporting_only_copy():
    recorder = FirstFailureRecorder()

    record = failure()

    recorder.record(
        "functional",
        record,
    )

    snapshot = recorder.snapshot()

    assert (
        snapshot["first_failure"]["instruction_id"]
        == 5
    )

    snapshot["first_failure"]["instruction_id"] = 99

    assert recorder.first_failure.instruction_id == 5


def test_invalid_kind_rejected():
    recorder = FirstFailureRecorder()

    with pytest.raises(
        ValueError,
        match="unknown failure kind",
    ):
        recorder.record(
            "other",
            failure(),
        )


def test_failure_record_validates_frozen_domains():
    with pytest.raises(
        ValueError,
        match="instruction_id",
    ):
        FailureRecord(
            instruction_id=0,
            cycle=1,
            pc=0,
            instruction=0,
            checker="control",
            check_name="forward_a",
            expected=2,
            observed=0,
        )

    with pytest.raises(
        ValueError,
        match="9-bit PC",
    ):
        FailureRecord(
            instruction_id=1,
            cycle=1,
            pc=0x200,
            instruction=0,
            checker="control",
            check_name="forward_a",
            expected=2,
            observed=0,
        )
