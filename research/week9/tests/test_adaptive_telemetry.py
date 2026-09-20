import pytest

from research.week9.adaptive_telemetry import (
    AdaptiveTelemetryRecord,
    AdaptiveTelemetrySink,
)


def make_record(**overrides):
    values = dict(
        epoch=1,
        instruction_count=1000,
        arm_id="A2",
        reward=3.0,
        q_value=1.25,
        epsilon=0.10,
        alpha=0.30,
        pull_count=1,
    )
    values.update(overrides)
    return AdaptiveTelemetryRecord(**values)


def test_valid_record():
    record = make_record()

    assert record.epoch == 1
    assert record.instruction_count == 1000
    assert record.arm_id == "A2"
    assert record.reward == pytest.approx(3.0)
    assert record.q_value == pytest.approx(1.25)
    assert record.epsilon == pytest.approx(0.10)
    assert record.alpha == pytest.approx(0.30)
    assert record.pull_count == 1


@pytest.mark.parametrize(
    "arm_id",
    ["A0", "A1", "A2", "A3", "A4",
     "A5", "A6", "A7", "A8", "A9"],
)
def test_all_frozen_arms_are_accepted(arm_id):
    record = make_record(arm_id=arm_id)
    assert record.arm_id == arm_id


@pytest.mark.parametrize(
    "arm_id",
    ["A10", "A-1", "ALU_D1", "", None],
)
def test_invalid_arm_is_rejected(arm_id):
    with pytest.raises(ValueError):
        make_record(arm_id=arm_id)


@pytest.mark.parametrize(
    "epsilon",
    [0.05, 0.10, 0.20],
)
def test_frozen_epsilon_values_are_accepted(epsilon):
    record = make_record(epsilon=epsilon)
    assert record.epsilon == pytest.approx(epsilon)


@pytest.mark.parametrize(
    "epsilon",
    [0.0, 0.15, 0.25, 1.0],
)
def test_non_preregistered_epsilon_is_rejected(epsilon):
    with pytest.raises(ValueError):
        make_record(epsilon=epsilon)


@pytest.mark.parametrize(
    "alpha",
    [0.1, 0.3, 0.5],
)
def test_frozen_alpha_values_are_accepted(alpha):
    record = make_record(alpha=alpha)
    assert record.alpha == pytest.approx(alpha)


@pytest.mark.parametrize(
    "alpha",
    [0.0, 0.2, 0.4, 1.0],
)
def test_non_preregistered_alpha_is_rejected(alpha):
    with pytest.raises(ValueError):
        make_record(alpha=alpha)


def test_negative_reward_is_rejected():
    with pytest.raises(ValueError):
        make_record(reward=-0.01)


def test_pull_count_must_be_positive():
    with pytest.raises(ValueError):
        make_record(pull_count=0)


def test_epoch_must_be_positive():
    with pytest.raises(ValueError):
        make_record(epoch=0)


def test_instruction_count_must_be_nonnegative():
    with pytest.raises(ValueError):
        make_record(instruction_count=-1)


def test_sink_streams_without_retaining_records():
    emitted = []

    sink = AdaptiveTelemetrySink(
        retain_records=False,
        record_sink=emitted.append,
    )

    sink.emit(make_record(epoch=1))
    sink.emit(
        make_record(
            epoch=2,
            instruction_count=2000,
            pull_count=2,
        )
    )

    assert sink.records == []
    assert [record.epoch for record in emitted] == [1, 2]


def test_sink_can_retain_records_for_short_tests():
    sink = AdaptiveTelemetrySink(
        retain_records=True,
    )

    sink.emit(make_record())

    assert len(sink.records) == 1
    assert sink.records[0].arm_id == "A2"


def test_epochs_must_be_contiguous():
    sink = AdaptiveTelemetrySink()

    sink.emit(make_record(epoch=1))

    with pytest.raises(ValueError):
        sink.emit(
            make_record(
                epoch=3,
                instruction_count=3000,
                pull_count=2,
            )
        )


def test_instruction_count_must_not_go_backwards():
    sink = AdaptiveTelemetrySink()

    sink.emit(
        make_record(
            epoch=1,
            instruction_count=2000,
        )
    )

    with pytest.raises(ValueError):
        sink.emit(
            make_record(
                epoch=2,
                instruction_count=1000,
                pull_count=2,
            )
        )
