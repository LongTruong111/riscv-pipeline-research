from types import SimpleNamespace

import pytest

from research.week9.coverage_collector import (
    CoverageCheckpoint,
    CoverageCollector,
)
from research.week10.adaptive.campaign_telemetry import (
    CHECKPOINT_SEMANTICS,
    SCHEMA_VERSION,
    CampaignTelemetryRecorder,
)
from research.week10.adaptive.template_library import ArmID


class FakeDecisionState:
    def __init__(
        self,
        *,
        epoch_index=0,
    ):
        self.epoch_index = epoch_index

        self._q_values = {
            arm: 0.0
            for arm in ArmID
        }

        self._pull_counts = {
            arm: 0
            for arm in ArmID
        }

        self._recent_rewards = {
            arm: 0.0
            for arm in ArmID
        }

    def q_values(self):
        return dict(self._q_values)

    def pull_counts(self):
        return dict(self._pull_counts)

    def recent_rewards(self):
        return dict(self._recent_rewards)

    def apply_update(
        self,
        *,
        arm,
        new_q,
        pull_count,
        reward,
    ):
        self._q_values[arm] = new_q
        self._pull_counts[arm] = pull_count
        self._recent_rewards[arm] = reward
        self.epoch_index += 1


def make_completion(
    *,
    epoch_index=0,
    arm=ArmID.A2,
    actual_executed=501,
    target_d1=7,
    target_d2=None,
    reward=2.0,
    old_q=0.0,
    new_q=0.6,
    pull_count=1,
):
    decision = SimpleNamespace(
        epoch_index=epoch_index,
        arm_id=arm,
        mode=SimpleNamespace(
            value="epsilon_exploration"
        ),
        candidate_arms=tuple(ArmID),
        q_value_before=old_q,
        max_q_before=old_q,
        epsilon=0.10,
    )

    start = SimpleNamespace(
        decision=decision,
        target=SimpleNamespace(
            d1=target_d1,
            d2=target_d2,
        ),
        covered_at_epoch_start=frozenset(),
    )

    reward_result = SimpleNamespace(
        arm_id=arm,
        actual_executed_instructions=(
            actual_executed
        ),
        observed_intent_bins=frozenset(
            {
                ("d1", 7),
                ("d2", 7),
            }
        ),
        attributable_observed_intent_bins=(
            frozenset(
                {
                    ("d1", 7),
                }
            )
        ),
        global_new_count=2,
        attributable_new_count=1,
        reward=reward,
    )

    update = SimpleNamespace(
        epoch_index=epoch_index,
        arm_id=arm,
        reward=reward,
        old_q=old_q,
        new_q=new_q,
        pull_count=pull_count,
    )

    return SimpleNamespace(
        start=start,
        reward_result=reward_result,
        bandit_update=update,
    )


def make_recorder(
    **kwargs,
):
    defaults = dict(
        seed=20260921,
        epsilon=0.10,
        alpha=0.30,
        q_floor=0.05,
        nominal_batch=500,
        instruction_budget=5000,
    )

    defaults.update(kwargs)

    return CampaignTelemetryRecorder(
        **defaults
    )


def test_checkpoint_record_preserves_post_instruction_semantics():
    recorder = make_recorder()
    state = FakeDecisionState(
        epoch_index=0
    )

    checkpoint = CoverageCheckpoint(
        executed_instructions=1000,
        cycle=1234,
        l1_intent_count=20,
        l1_validated_count=15,
        l2_intent_count=41,
        l2_validated_count=37,
    )

    record = recorder.record_checkpoint(
        checkpoint,
        epoch_index=0,
        decision_state=state,
    )

    assert record.schema_version == SCHEMA_VERSION

    assert (
        record.checkpoint_semantics
        == CHECKPOINT_SEMANTICS
    )

    assert record.executed_instructions == 1000
    assert record.cycle == 1234

    assert record.l1_intent_count == 20
    assert record.l1_validated_count == 15

    assert record.l2_intent_count == 41
    assert record.l2_validated_count == 37

    assert record.epoch_index == 0

    assert tuple(
        arm
        for arm, _ in record.q_values
    ) == tuple(
        sorted(
            arm.value
            for arm in ArmID
        )
    )


def test_epoch_record_uses_authoritative_completion_and_q_state():
    recorder = make_recorder()

    completion = make_completion()

    state = FakeDecisionState(
        epoch_index=0
    )

    state.apply_update(
        arm=ArmID.A2,
        new_q=0.6,
        pull_count=1,
        reward=2.0,
    )

    record = recorder.record_epoch(
        completion,
        decision_state=state,
    )

    assert record.epoch_index == 0
    assert record.selected_arm == "A2"

    assert (
        record.selection_mode
        == "epsilon_exploration"
    )

    assert record.target_d1 == 7
    assert record.target_d2 is None

    assert record.first_executed_instruction == 1
    assert record.last_executed_instruction == 501

    assert (
        record.actual_executed_instructions
        == 501
    )

    assert (
        record.global_observed_l2_intent_count
        == 2
    )

    assert (
        record.attributable_observed_l2_intent_count
        == 1
    )

    assert record.global_new_l2_intent_count == 2

    assert (
        record.attributable_new_l2_intent_count
        == 1
    )

    assert record.reward == 2.0
    assert record.old_q == 0.0
    assert record.new_q == 0.6
    assert record.pull_count == 1


def test_epoch_instruction_ranges_are_globally_contiguous():
    recorder = make_recorder()

    state = FakeDecisionState(
        epoch_index=0
    )

    first = make_completion(
        epoch_index=0,
        actual_executed=501,
        old_q=0.0,
        new_q=0.6,
        pull_count=1,
    )

    state.apply_update(
        arm=ArmID.A2,
        new_q=0.6,
        pull_count=1,
        reward=2.0,
    )

    first_record = recorder.record_epoch(
        first,
        decision_state=state,
    )

    second = make_completion(
        epoch_index=1,
        actual_executed=503,
        old_q=0.6,
        new_q=0.72,
        pull_count=2,
    )

    state.apply_update(
        arm=ArmID.A2,
        new_q=0.72,
        pull_count=2,
        reward=2.0,
    )

    second_record = recorder.record_epoch(
        second,
        decision_state=state,
    )

    assert first_record.first_executed_instruction == 1
    assert first_record.last_executed_instruction == 501

    assert (
        second_record.first_executed_instruction
        == 502
    )

    assert (
        second_record.last_executed_instruction
        == 1004
    )

    assert recorder.completed_epochs == 2

    assert (
        recorder.closed_epoch_executed_instructions
        == 1004
    )


def test_epoch_record_rejects_mismatched_arm_identity():
    recorder = make_recorder()

    completion = make_completion()

    completion.bandit_update.arm_id = ArmID.A3

    state = FakeDecisionState(
        epoch_index=1
    )

    with pytest.raises(
        AssertionError,
        match="decision/update arm mismatch",
    ):
        recorder.record_epoch(
            completion,
            decision_state=state,
        )


def test_streaming_mode_does_not_retain_epoch_or_checkpoint_history():
    epoch_stream = []
    checkpoint_stream = []
    summary_stream = []

    recorder = make_recorder(
        retain_records=False,
        epoch_sink=epoch_stream.append,
        checkpoint_sink=(
            checkpoint_stream.append
        ),
        summary_sink=summary_stream.append,
    )

    state = FakeDecisionState(
        epoch_index=0
    )

    checkpoint = CoverageCheckpoint(
        executed_instructions=1000,
        cycle=1500,
        l1_intent_count=20,
        l1_validated_count=15,
        l2_intent_count=40,
        l2_validated_count=35,
    )

    recorder.record_checkpoint(
        checkpoint,
        epoch_index=0,
        decision_state=state,
    )

    completion = make_completion(
        actual_executed=1000
    )

    state.apply_update(
        arm=ArmID.A2,
        new_q=0.6,
        pull_count=1,
        reward=2.0,
    )

    recorder.record_epoch(
        completion,
        decision_state=state,
    )

    summary = recorder.finalize(
        termination_reason=(
            "instruction_budget_reached"
        ),
        executed_instructions=1000,
        final_l1_intent_count=20,
        final_l1_validated_count=15,
        final_l2_intent_count=40,
        final_l2_validated_count=35,
        decision_state=state,
    )

    assert recorder.epoch_records == ()
    assert recorder.checkpoint_records == ()

    assert len(epoch_stream) == 1
    assert len(checkpoint_stream) == 1
    assert len(summary_stream) == 1

    assert summary_stream[0] == summary


def test_finalize_rejects_unclosed_instruction_accounting():
    recorder = make_recorder()

    state = FakeDecisionState(
        epoch_index=0
    )

    completion = make_completion(
        actual_executed=501
    )

    state.apply_update(
        arm=ArmID.A2,
        new_q=0.6,
        pull_count=1,
        reward=2.0,
    )

    recorder.record_epoch(
        completion,
        decision_state=state,
    )

    with pytest.raises(
        AssertionError,
        match="sum of closed adaptive epochs",
    ):
        recorder.finalize(
            termination_reason=(
                "instruction_budget_reached"
            ),
            executed_instructions=500,
            final_l1_intent_count=20,
            final_l1_validated_count=15,
            final_l2_intent_count=40,
            final_l2_validated_count=35,
            decision_state=state,
        )
def test_fixed_epoch_campaign_allows_no_instruction_budget():
    recorder = make_recorder(
        instruction_budget=None
    )

    state = FakeDecisionState(
        epoch_index=0
    )

    completion = make_completion(
        actual_executed=501
    )

    state.apply_update(
        arm=ArmID.A2,
        new_q=0.6,
        pull_count=1,
        reward=2.0,
    )

    recorder.record_epoch(
        completion,
        decision_state=state,
    )

    summary = recorder.finalize(
        termination_reason="fixed_epoch_count_reached",
        executed_instructions=501,
        final_l1_intent_count=20,
        final_l1_validated_count=15,
        final_l2_intent_count=40,
        final_l2_validated_count=35,
        decision_state=state,
    )

    assert summary.instruction_budget is None
    assert summary.completed_epochs == 1
    assert summary.executed_instructions == 501
def test_real_coverage_collector_streams_checkpoint_to_telemetry():
    recorder = make_recorder(
        instruction_budget=1000
    )

    state = FakeDecisionState(
        epoch_index=0
    )

    coverage = CoverageCollector(
        checkpoint_interval=1000,
        retain_checkpoints=False,
        checkpoint_sink=(
            lambda checkpoint:
            recorder.record_checkpoint(
                checkpoint,
                epoch_index=state.epoch_index,
                decision_state=state,
            )
        ),
    )

    for instruction_index in range(1, 1001):
        coverage.record_instruction(
            instruction_id=instruction_index,
            cycle=instruction_index,
        )

    assert coverage.executed_instructions == 1000

    assert len(recorder.checkpoint_records) == 1

    record = recorder.checkpoint_records[0]

    assert record.executed_instructions == 1000

    assert (
        record.checkpoint_semantics
        == "post_instruction_cut_v1"
    )
