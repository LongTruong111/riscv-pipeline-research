import pytest

from research.week10.adaptive.register_policy import (
    TargetSelection,
)
from research.week10.adaptive.reward_engine import (
    EpochRewardTracker,
    L2IntentBin,
    attribution_targets_for,
)
from research.week10.adaptive.template_library import (
    ArmID,
    Distance,
)


def d1(register):
    return L2IntentBin(
        distance=Distance.D1,
        register=register,
    )


def d2(register):
    return L2IntentBin(
        distance=Distance.D2,
        register=register,
    )


def test_l2_bin_rejects_x0():
    with pytest.raises(ValueError):
        d1(0)


def test_l2_bin_rejects_register_above_x31():
    with pytest.raises(ValueError):
        d2(32)


def test_l2_bin_rejects_combined_distance():
    with pytest.raises(ValueError):
        L2IntentBin(
            distance=Distance.D1_D2,
            register=5,
        )


@pytest.mark.parametrize(
    "arm_id",
    [
        ArmID.A0,
        ArmID.A2,
        ArmID.A5,
        ArmID.A7,
        ArmID.A8,
        ArmID.A9,
    ],
)
def test_d1_arm_has_exactly_one_attribution_target(
    arm_id,
):
    targets = attribution_targets_for(
        arm_id,
        TargetSelection(d1=7),
    )

    assert targets == frozenset({d1(7)})


@pytest.mark.parametrize(
    "arm_id",
    [
        ArmID.A1,
        ArmID.A3,
        ArmID.A6,
    ],
)
def test_d2_arm_has_exactly_one_attribution_target(
    arm_id,
):
    targets = attribution_targets_for(
        arm_id,
        TargetSelection(d2=9),
    )

    assert targets == frozenset({d2(9)})


def test_a4_has_two_attribution_targets():
    targets = attribution_targets_for(
        ArmID.A4,
        TargetSelection(
            d1=7,
            d2=13,
        ),
    )

    assert targets == frozenset(
        {
            d1(7),
            d2(13),
        }
    )


def test_d1_arm_rejects_d2_target_shape():
    with pytest.raises(ValueError):
        attribution_targets_for(
            ArmID.A0,
            TargetSelection(d2=5),
        )


def test_d2_arm_rejects_d1_target_shape():
    with pytest.raises(ValueError):
        attribution_targets_for(
            ArmID.A1,
            TargetSelection(d1=5),
        )


def test_a4_rejects_single_target_shape():
    with pytest.raises(ValueError):
        attribution_targets_for(
            ArmID.A4,
            TargetSelection(d1=5),
        )


def test_new_attributable_hit_generates_reward():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(d1=7),
        covered_at_epoch_start=set(),
    )

    tracker.record_attributable_intent_hit(
        d1(7)
    )

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.global_new_count == 1
    assert result.attributable_new_count == 1
    assert result.reward == pytest.approx(2.0)

def test_reward_uses_actual_executed_count():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(d1=7),
        covered_at_epoch_start=set(),
    )

    tracker.record_attributable_intent_hit(
        d1(7)
    )

    result = tracker.finalize(
        actual_executed_instructions=503
    )

    assert result.reward == pytest.approx(
        1000.0 / 503.0
    )


def test_attributable_and_incidental_hits_are_separated():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(d1=7),
        covered_at_epoch_start=set(),
    )

    # Exact-provenance selected-arm hit.
    tracker.record_attributable_intent_hit(
        d1(7)
    )

    # Incidental global-only hits.
    tracker.record_intent_hit(
        d2(20)
    )

    tracker.record_intent_hit(
        d1(21)
    )

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.global_new_intent_bins == frozenset(
        {
            d1(7),
            d2(20),
            d1(21),
        }
    )

    assert result.attributable_new_intent_bins == frozenset(
        {
            d1(7),
        }
    )

    assert result.reward == pytest.approx(
        2.0
    )


def test_duplicate_attributable_hits_count_once():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(d1=11),
        covered_at_epoch_start=set(),
    )

    for _ in range(20):
        tracker.record_attributable_intent_hit(
            d1(11)
        )

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.global_new_count == 1
    assert result.attributable_new_count == 1

    assert result.reward == pytest.approx(
        2.0
    )


def test_a4_can_reward_two_new_bins():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A4,
        target=TargetSelection(
            d1=7,
            d2=13,
        ),
        covered_at_epoch_start=set(),
    )

    tracker.record_attributable_intent_hit(
        d1(7)
    )

    tracker.record_attributable_intent_hit(
        d2(13)
    )

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.global_new_count == 2
    assert result.attributable_new_count == 2

    assert result.reward == pytest.approx(
        4.0
    )

def test_start_snapshot_is_immutable_against_caller_mutation():
    covered = {
        d1(1),
    }

    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(d1=2),
        covered_at_epoch_start=covered,
    )

    # Mutate caller-owned state after tracker construction.
    # The tracker must retain the frozen original snapshot.
    covered.add(
        d1(2)
    )

    tracker.record_attributable_intent_hit(
        d1(2)
    )

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.global_new_intent_bins == frozenset(
        {
            d1(2),
        }
    )

    assert result.attributable_new_intent_bins == frozenset(
        {
            d1(2),
        }
    )

    assert result.global_new_count == 1
    assert result.attributable_new_count == 1

    assert result.reward == pytest.approx(
        2.0
    )

def test_a4_one_old_one_new_rewards_only_new_bin():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A4,
        target=TargetSelection(
            d1=7,
            d2=13,
        ),
        covered_at_epoch_start={
            d1(7),
        },
    )

    # Both dependencies are exact-provenance hits.
    # d1(7) was already covered at epoch start, so only d2(13)
    # contributes new attributable coverage.
    tracker.record_attributable_intent_hit(
        d1(7)
    )

    tracker.record_attributable_intent_hit(
        d2(13)
    )

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.global_new_intent_bins == frozenset(
        {
            d2(13),
        }
    )

    assert result.attributable_new_intent_bins == frozenset(
        {
            d2(13),
        }
    )

    assert result.global_new_count == 1
    assert result.attributable_new_count == 1

    assert result.reward == pytest.approx(
        2.0
    )

def test_a4_incidental_third_bin_does_not_increase_reward():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A4,
        target=TargetSelection(
            d1=7,
            d2=13,
        ),
        covered_at_epoch_start=set(),
    )

    # Exact-provenance selected-arm dependencies.
    tracker.record_attributable_intent_hit(
        d1(7)
    )

    tracker.record_attributable_intent_hit(
        d2(13)
    )

    # Global novelty only. This hit is incidental and must not
    # contribute adaptive reward.
    tracker.record_intent_hit(
        d1(22)
    )

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.global_new_intent_bins == frozenset(
        {
            d1(7),
            d2(13),
            d1(22),
        }
    )

    assert result.attributable_new_intent_bins == frozenset(
        {
            d1(7),
            d2(13),
        }
    )

    assert result.global_new_count == 3
    assert result.attributable_new_count == 2

    assert result.reward == pytest.approx(
        4.0
    )

def test_no_hits_gives_zero_reward():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A3,
        target=TargetSelection(d2=8),
        covered_at_epoch_start=set(),
    )

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.global_new_count == 0
    assert result.attributable_new_count == 0
    assert result.reward == 0.0


def test_all_62_bins_may_be_present_in_start_snapshot():
    all_bins = {
        L2IntentBin(distance, register)
        for distance in (
            Distance.D1,
            Distance.D2,
        )
        for register in range(1, 32)
    }

    assert len(all_bins) == 62

    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(d1=4),
        covered_at_epoch_start=all_bins,
    )

    tracker.record_intent_hit(d1(4))

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.reward == 0.0
    assert result.global_new_count == 0


@pytest.mark.parametrize(
    "invalid_count",
    [0, -1, -500],
)
def test_nonpositive_executed_count_rejected(
    invalid_count,
):
    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(d1=4),
        covered_at_epoch_start=set(),
    )

    with pytest.raises(ValueError):
        tracker.finalize(
            actual_executed_instructions=invalid_count
        )


def test_tracker_rejects_non_l2_bin_hit():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(d1=4),
        covered_at_epoch_start=set(),
    )

    with pytest.raises(TypeError):
        tracker.record_intent_hit(("d1", 4))


def test_tracker_rejects_invalid_start_snapshot_type():
    with pytest.raises(TypeError):
        EpochRewardTracker(
            arm_id=ArmID.A0,
            target=TargetSelection(d1=4),
            covered_at_epoch_start={
                ("d1", 4),
            },
        )


def test_cannot_record_after_finalize():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(d1=4),
        covered_at_epoch_start=set(),
    )

    tracker.finalize(
        actual_executed_instructions=500
    )

    with pytest.raises(RuntimeError):
        tracker.record_intent_hit(d1(4))


def test_cannot_finalize_twice():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(d1=4),
        covered_at_epoch_start=set(),
    )

    tracker.finalize(
        actual_executed_instructions=500
    )

    with pytest.raises(RuntimeError):
        tracker.finalize(
            actual_executed_instructions=500
        )

def test_result_exposes_exact_attribution_target():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A6,
        target=TargetSelection(d2=19),
        covered_at_epoch_start=set(),
    )

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.attributable_targets == frozenset(
        {d2(19)}
    )

def test_same_target_bin_without_provenance_gives_no_reward():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(d1=7),
        covered_at_epoch_start=set(),
    )

    # Same exact selected L2 bin, but only global observation.
    tracker.record_intent_hit(
        d1(7)
    )

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.global_new_intent_bins == frozenset(
        {d1(7)}
    )

    assert (
        result.attributable_observed_intent_bins
        == frozenset()
    )

    assert result.attributable_new_count == 0
    assert result.reward == 0.0


def test_attributable_observation_must_be_selected_target():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(d1=7),
        covered_at_epoch_start=set(),
    )

    with pytest.raises(ValueError):
        tracker.record_attributable_intent_hit(
            d1(18)
        )
