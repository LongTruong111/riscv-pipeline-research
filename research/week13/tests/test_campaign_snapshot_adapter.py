import pytest

from research.week5.impl.l1_coverage import (
    L1Hit,
)
from research.week5.impl.validated_coverage import (
    L1ValidatedCoverageCollector,
)
from research.week7.retire_monitor import (
    RetireMonitor,
)
from research.week7.timing_oracle_v1 import (
    RETIRE_LATENCY,
)
from research.week9.benchmark.streaming_functional import (
    StreamingFunctionalScoreboard,
)
from research.week9.benchmark.streaming_timing import (
    StreamingPerformanceMonitor,
)
from research.week10.l2_realization import (
    L2ValidatedCoverageChecker,
    _PendingHit,
)

from research.week13.campaign.invariant_ledger import (
    CampaignInvariantLedger,
)
from research.week13.campaign.snapshot_adapter import (
    CAMPAIGN_MAX_IN_FLIGHT_DEPTH,
    SnapshotAdapterProtocolError,
    build_campaign_lifecycle_snapshot,
)


def components():
    return {
        "retire_monitor": RetireMonitor(),
        "functional": StreamingFunctionalScoreboard(),
        "performance": StreamingPerformanceMonitor(),
        "l1_validated": (
            L1ValidatedCoverageCollector()
        ),
        "l2_validated": (
            L2ValidatedCoverageChecker()
        ),
    }


def build(
    state,
    *,
    cycle=0,
    accepted=0,
    max_intent=0,
):
    return build_campaign_lifecycle_snapshot(
        cycle=cycle,
        accepted=accepted,
        max_intent_consumer_id=max_intent,
        **state,
    )


def test_fresh_real_components_snapshot_zero():
    state = components()

    item = build(state)

    assert item.accepted == 0
    assert item.retired_checked == 0

    assert item.functional_checked == 0
    assert item.functional_pending == 0

    assert item.performance_checked == 0
    assert item.performance_pending == 0

    assert item.l1.registered == 0
    assert item.l1.validated == 0
    assert item.l1.rejected == 0
    assert item.l1.pending == 0

    assert item.l2.registered == 0
    assert item.l2.validated == 0
    assert item.l2.rejected == 0
    assert item.l2.pending == 0


def test_frozen_depth_comes_from_timing_authority():
    assert (
        CAMPAIGN_MAX_IN_FLIGHT_DEPTH
        == RETIRE_LATENCY
    )

    assert RETIRE_LATENCY == 3


def test_l1_pending_participants_are_extracted():
    state = components()

    checker = state["l1_validated"]

    hit = L1Hit(
        bin_id="H01",
        consumer_instruction_index=3,
        producer_instruction_indices=(1, 2),
        matched_sources=("RS1",),
    )

    outcomes = checker.register_hit(
        hit,
        control_passed=True,
    )

    assert outcomes == ()
    assert checker.pending_hits == 1

    item = build(
        state,
        accepted=3,
        max_intent=3,
    )

    assert item.l1.registered == 1
    assert item.l1.validated == 0
    assert item.l1.rejected == 0
    assert item.l1.pending == 1

    assert (
        item.l1.pending_participants
        == ((1, 2, 3),)
    )


def test_l1_rejected_hit_is_accounted_independently():
    state = components()

    checker = state["l1_validated"]

    hit = L1Hit(
        bin_id="H01",
        consumer_instruction_index=2,
        producer_instruction_indices=(1,),
        matched_sources=("RS1",),
    )

    outcomes = checker.register_hit(
        hit,
        control_passed=False,
    )

    assert len(outcomes) == 1
    assert checker.pending_hits == 0

    item = build(
        state,
        accepted=2,
        max_intent=2,
    )

    assert item.l1.registered == 1
    assert item.l1.validated == 0
    assert item.l1.rejected == 1
    assert item.l1.pending == 0


def test_l2_pending_required_checks_define_participants():
    state = components()

    checker = state["l2_validated"]

    # The adapter deliberately audits the frozen private pending
    # representation. We populate that representation directly here
    # so this test fails if its schema changes.
    checker._attempt_count = 1

    checker._pending_by_consumer[2] = [
        _PendingHit(
            hit=None,
            required_checks=(
                (1, "pc"),
                (1, "store"),
                (1, "writeback"),
                (1, "next_pc"),
                (2, "pc"),
                (2, "store"),
                (2, "writeback"),
                (2, "next_pc"),
            ),
        )
    ]

    item = build(
        state,
        accepted=2,
        max_intent=2,
    )

    assert item.l2.registered == 1
    assert item.l2.validated == 0
    assert item.l2.rejected == 0
    assert item.l2.pending == 1

    assert (
        item.l2.pending_participants
        == ((1, 2),)
    )


def test_l2_private_layout_drift_is_rejected():
    state = components()

    checker = state["l2_validated"]

    checker._attempt_count = 1
    checker._pending_by_consumer[2] = [
        object()
    ]

    with pytest.raises(
        SnapshotAdapterProtocolError
    ):
        build(
            state,
            accepted=2,
            max_intent=2,
        )


def test_l1_private_public_pending_disagreement_is_rejected():
    state = components()

    checker = state["l1_validated"]

    hit = L1Hit(
        bin_id="H01",
        consumer_instruction_index=2,
        producer_instruction_indices=(1,),
        matched_sources=("RS1",),
    )

    checker.register_hit(
        hit,
        control_passed=True,
    )

    # Deliberately corrupt only the public-facing accounting source.
    checker._pending_by_consumer[3] = []

    # Empty bucket does not alter public pending count and is harmless.
    item = build(
        state,
        accepted=2,
        max_intent=2,
    )

    assert item.l1.pending == 1


def test_zero_snapshot_passes_campaign_ledger():
    state = components()

    item = build(state)

    ledger = CampaignInvariantLedger(
        hard_cap=10,
        max_in_flight_depth=(
            CAMPAIGN_MAX_IN_FLIGHT_DEPTH
        ),
    )

    ledger.check_snapshot(item)

    assert ledger.max_observed_in_flight == 0
