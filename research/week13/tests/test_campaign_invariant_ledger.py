import pytest

from research.week13.campaign.invariant_ledger import (
    CampaignInvariantLedger,
    CampaignInvariantViolation,
    CampaignLifecycleSnapshot,
    HitLifecycleSnapshot,
)


def hits(
    *,
    registered=0,
    validated=0,
    rejected=0,
    pending=0,
    pending_participants=(),
    pruned_mid_run=0,
):
    return HitLifecycleSnapshot(
        registered=registered,
        validated=validated,
        rejected=rejected,
        pending=pending,
        pending_participants=(
            pending_participants
        ),
        pruned_mid_run=pruned_mid_run,
    )


def snapshot(
    *,
    cycle=10,
    accepted=5,
    retired=2,
    functional_pending=3,
    performance_pending=3,
    functional_checked=2,
    performance_checked=2,
    max_intent=5,
    l1=None,
    l2=None,
):
    return CampaignLifecycleSnapshot(
        cycle=cycle,
        accepted=accepted,
        retired_checked=retired,
        functional_checked=(
            functional_checked
        ),
        functional_pending=(
            functional_pending
        ),
        performance_checked=(
            performance_checked
        ),
        performance_pending=(
            performance_pending
        ),
        max_intent_consumer_id=max_intent,
        l1=hits() if l1 is None else l1,
        l2=hits() if l2 is None else l2,
    )


def ledger(
    *,
    hard_cap=10,
    depth=4,
):
    return CampaignInvariantLedger(
        hard_cap=hard_cap,
        max_in_flight_depth=depth,
    )


def test_valid_lifecycle_snapshot_passes():
    item = ledger()

    item.check_snapshot(
        snapshot()
    )

    assert (
        item.max_observed_in_flight
        == 3
    )


def test_accept_cannot_exceed_hard_cap():
    item = ledger(
        hard_cap=5,
        depth=4,
    )

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.check_snapshot(
            snapshot(
                accepted=6,
                retired=3,
                functional_pending=3,
                performance_pending=3,
                functional_checked=3,
                performance_checked=3,
                max_intent=6,
            )
        )


def test_functional_pending_must_equal_in_flight():
    item = ledger()

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.check_snapshot(
            snapshot(
                functional_pending=2,
            )
        )


def test_performance_pending_must_equal_in_flight():
    item = ledger()

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.check_snapshot(
            snapshot(
                performance_pending=2,
            )
        )


def test_in_flight_depth_is_bounded():
    item = ledger(
        depth=2,
    )

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.check_snapshot(
            snapshot()
        )


def test_hit_conservation_passes():
    item = ledger()

    l1 = hits(
        registered=3,
        validated=1,
        rejected=1,
        pending=1,
        pending_participants=(
            (2, 5),
        ),
    )

    item.check_snapshot(
        snapshot(
            l1=l1,
        )
    )


def test_hit_conservation_failure_is_infra_invalid():
    item = ledger()

    l1 = hits(
        registered=4,
        validated=1,
        rejected=1,
        pending=1,
        pending_participants=(
            (2, 5),
        ),
    )

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.check_snapshot(
            snapshot(
                l1=l1,
            )
        )


def test_pending_hit_requires_unresolved_tail_participant():
    item = ledger()

    l1 = hits(
        registered=1,
        pending=1,
        pending_participants=(
            (1, 2),
        ),
    )

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.check_snapshot(
            snapshot(
                retired=2,
                functional_checked=2,
                performance_checked=2,
                l1=l1,
            )
        )


def test_pending_hit_cannot_reference_future_instruction():
    item = ledger()

    l2 = hits(
        registered=1,
        pending=1,
        pending_participants=(
            (4, 6),
        ),
    )

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.check_snapshot(
            snapshot(
                l2=l2,
            )
        )


def test_mid_run_hit_pruning_is_forbidden():
    item = ledger()

    l2 = hits(
        pruned_mid_run=1,
    )

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.check_snapshot(
            snapshot(
                l2=l2,
            )
        )


def test_intent_cannot_look_beyond_accepted_prefix():
    item = ledger()

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.check_snapshot(
            snapshot(
                max_intent=6,
            )
        )


def test_counters_cannot_regress():
    item = ledger()

    item.check_snapshot(
        snapshot()
    )

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.check_snapshot(
            snapshot(
                cycle=11,
                accepted=4,
                retired=2,
                functional_pending=2,
                performance_pending=2,
                max_intent=4,
            )
        )


def test_exact_cut_contract_passes():
    item = ledger(
        hard_cap=5,
        depth=4,
    )

    final = snapshot(
        cycle=20,
        accepted=5,
        retired=2,
        functional_pending=3,
        performance_pending=3,
        functional_checked=2,
        performance_checked=2,
        max_intent=5,
    )

    item.check_snapshot(final)

    item.mark_exact_cut(
        current_cycle=20,
        kill_cycle=20,
        accepted=5,
        adapter_instruction_count=5,
    )

    item.finalize(final)

    assert item.cut_marked
    assert item.cut_cycle == 20
    assert item.kill_cycle == 20
    assert item.post_cut_clock_edges == 0


def test_cut_cannot_be_marked_before_hard_cap():
    item = ledger(
        hard_cap=5,
        depth=4,
    )

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.mark_exact_cut(
            current_cycle=20,
            kill_cycle=20,
            accepted=4,
            adapter_instruction_count=4,
        )


def test_post_cut_clock_edge_is_infra_invalid():
    item = ledger(
        hard_cap=5,
        depth=4,
    )

    item.mark_exact_cut(
        current_cycle=20,
        kill_cycle=20,
        accepted=5,
        adapter_instruction_count=5,
    )

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.note_clock_edge(
            cycle=21,
            edge="falling",
        )

    assert item.post_cut_clock_edges == 1


def test_finalize_requires_exact_cut():
    item = ledger()

    with pytest.raises(
        CampaignInvariantViolation
    ):
        item.finalize(
            snapshot()
        )
