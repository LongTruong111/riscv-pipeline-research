import pytest

from research.week13.campaign.cut_driver import (
    CampaignCutDriver,
    CampaignInfrastructureError,
)
from research.week13.campaign.invariant_ledger import (
    CampaignInvariantLedger,
    CampaignLifecycleSnapshot,
    HitLifecycleSnapshot,
)


class FakeCoverage:
    def __init__(
        self,
        *,
        checkpoint_interval=2,
    ):
        self.executed_instructions = 0
        self.checkpoint_interval = (
            checkpoint_interval
        )

        self.observer_state = 0
        self.records = []
        self.checkpoints = []

    def record_instruction(
        self,
        *,
        instruction_id,
        cycle,
    ):
        # Proves observer mutation happened before record/checkpoint.
        assert (
            self.observer_state
            == instruction_id
        )

        assert (
            instruction_id
            == self.executed_instructions + 1
        )

        self.executed_instructions = (
            instruction_id
        )

        self.records.append(
            (instruction_id, cycle)
        )

        if (
            instruction_id
            % self.checkpoint_interval
            == 0
        ):
            self.checkpoints.append(
                (
                    instruction_id,
                    self.observer_state,
                )
            )


def empty_hits():
    return HitLifecycleSnapshot(
        registered=0,
        validated=0,
        rejected=0,
        pending=0,
    )


def lifecycle_snapshot(
    *,
    accepted,
    cycle,
    max_intent,
    retired=None,
):
    if retired is None:
        retired = accepted

    pending = accepted - retired

    return CampaignLifecycleSnapshot(
        cycle=cycle,
        accepted=accepted,
        retired_checked=retired,
        functional_checked=retired,
        functional_pending=pending,
        performance_checked=retired,
        performance_pending=pending,
        max_intent_consumer_id=max_intent,
        l1=empty_hits(),
        l2=empty_hits(),
    )


def build_driver(
    *,
    hard_cap=4,
    depth=3,
    checkpoint_interval=2,
):
    coverage = FakeCoverage(
        checkpoint_interval=(
            checkpoint_interval
        )
    )

    ledger = CampaignInvariantLedger(
        hard_cap=hard_cap,
        max_in_flight_depth=depth,
    )

    driver = CampaignCutDriver(
        hard_cap=hard_cap,
        coverage=coverage,
        ledger=ledger,
    )

    return driver, coverage


def complete(
    driver,
    coverage,
    *,
    instruction_index,
    cycle=None,
    retired=None,
):
    if cycle is None:
        cycle = instruction_index

    def observe():
        coverage.observer_state = (
            instruction_index
        )

    def snapshot_factory(max_intent):
        return lifecycle_snapshot(
            accepted=instruction_index,
            cycle=cycle,
            max_intent=max_intent,
            retired=retired,
        )

    return driver.complete_accepted_event(
        instruction_index=(
            instruction_index
        ),
        cycle=cycle,
        adapter_instruction_count=(
            instruction_index
        ),
        observe_coverage=observe,
        snapshot_factory=snapshot_factory,
    )


def test_nonterminal_cut_continues():
    driver, coverage = build_driver()

    result = complete(
        driver,
        coverage,
        instruction_index=1,
    )

    assert not result.exact_cut
    assert driver.accepted_count == 1
    assert (
        driver.coverage_observed_count
        == 1
    )


def test_final_checkpoint_uses_same_cut_path():
    driver, coverage = build_driver(
        hard_cap=4,
        checkpoint_interval=2,
    )

    for instruction_index in range(
        1,
        5,
    ):
        result = complete(
            driver,
            coverage,
            instruction_index=(
                instruction_index
            ),
        )

    assert result.exact_cut

    assert coverage.records == [
        (1, 1),
        (2, 2),
        (3, 3),
        (4, 4),
    ]

    assert coverage.checkpoints == [
        (2, 2),
        (4, 4),
    ]


def test_adapter_count_must_match_event():
    driver, coverage = build_driver()

    with pytest.raises(
        CampaignInfrastructureError
    ):
        driver.complete_accepted_event(
            instruction_index=1,
            cycle=1,
            adapter_instruction_count=0,
            observe_coverage=lambda: None,
            snapshot_factory=lambda _max: (
                lifecycle_snapshot(
                    accepted=1,
                    cycle=1,
                    max_intent=0,
                )
            ),
        )


def test_accepted_stream_must_be_contiguous():
    driver, coverage = build_driver()

    with pytest.raises(
        CampaignInfrastructureError
    ):
        complete(
            driver,
            coverage,
            instruction_index=2,
        )


def test_snapshot_accepted_count_must_match():
    driver, coverage = build_driver()

    def observe():
        coverage.observer_state = 1

    with pytest.raises(
        CampaignInfrastructureError
    ):
        driver.complete_accepted_event(
            instruction_index=1,
            cycle=1,
            adapter_instruction_count=1,
            observe_coverage=observe,
            snapshot_factory=lambda _max: (
                lifecycle_snapshot(
                    accepted=0,
                    cycle=1,
                    max_intent=0,
                )
            ),
        )


def test_lifecycle_violation_becomes_infra_invalid():
    driver, coverage = build_driver()

    def observe():
        coverage.observer_state = 1

    def bad_snapshot(_max_intent):
        return CampaignLifecycleSnapshot(
            cycle=1,
            accepted=1,
            retired_checked=0,
            functional_checked=0,
            functional_pending=0,
            performance_checked=0,
            performance_pending=1,
            max_intent_consumer_id=0,
            l1=empty_hits(),
            l2=empty_hits(),
        )

    with pytest.raises(
        CampaignInfrastructureError
    ):
        driver.complete_accepted_event(
            instruction_index=1,
            cycle=1,
            adapter_instruction_count=1,
            observe_coverage=observe,
            snapshot_factory=bad_snapshot,
        )


def test_intent_consumer_is_independent_bound():
    driver, coverage = build_driver()

    driver.note_intent_consumer(
        consumer_instruction_id=1,
        accepted_prefix=1,
    )

    assert (
        driver.max_intent_consumer_id
        == 1
    )

    with pytest.raises(
        CampaignInfrastructureError
    ):
        driver.note_intent_consumer(
            consumer_instruction_id=2,
            accepted_prefix=1,
        )


def test_no_accepted_event_after_exact_cut():
    driver, coverage = build_driver(
        hard_cap=1,
    )

    result = complete(
        driver,
        coverage,
        instruction_index=1,
    )

    assert result.exact_cut

    with pytest.raises(
        CampaignInfrastructureError
    ):
        complete(
            driver,
            coverage,
            instruction_index=2,
        )


def test_post_cut_clock_edge_is_infra_invalid():
    driver, coverage = build_driver(
        hard_cap=1,
    )

    complete(
        driver,
        coverage,
        instruction_index=1,
    )

    with pytest.raises(
        CampaignInfrastructureError
    ):
        driver.note_clock_edge(
            cycle=2,
            edge="falling",
        )


def test_finalize_requires_clock_stopped_high():
    driver, coverage = build_driver(
        hard_cap=1,
    )

    complete(
        driver,
        coverage,
        instruction_index=1,
    )

    with pytest.raises(
        CampaignInfrastructureError
    ):
        driver.finalize_after_clock_stop(
            adapter_instruction_count=1,
            clock_task_done=False,
            clock_is_high=True,
        )

    with pytest.raises(
        CampaignInfrastructureError
    ):
        driver.finalize_after_clock_stop(
            adapter_instruction_count=1,
            clock_task_done=True,
            clock_is_high=False,
        )

    final = (
        driver.finalize_after_clock_stop(
            adapter_instruction_count=1,
            clock_task_done=True,
            clock_is_high=True,
        )
    )

    assert final.accepted == 1


def test_method_hook_runs_after_checkpoint_before_snapshot():
    driver, coverage = build_driver(
        hard_cap=2,
        checkpoint_interval=2,
    )

    complete(
        driver,
        coverage,
        instruction_index=1,
    )

    hook_ran = False

    def observe():
        coverage.observer_state = 2

    def after_post_cut():
        nonlocal hook_ran

        assert coverage.executed_instructions == 2

        assert coverage.checkpoints == [
            (2, 2),
        ]

        hook_ran = True

    def snapshot_factory(max_intent):
        assert hook_ran

        return lifecycle_snapshot(
            accepted=2,
            cycle=2,
            max_intent=max_intent,
        )

    decision = driver.complete_accepted_event(
        instruction_index=2,
        cycle=2,
        adapter_instruction_count=2,
        observe_coverage=observe,
        snapshot_factory=snapshot_factory,
        after_post_instruction_cut=(
            after_post_cut
        ),
    )

    assert decision.exact_cut
    assert hook_ran


def test_method_hook_failure_is_infra_invalid():
    driver, coverage = build_driver(
        hard_cap=1,
    )

    def observe():
        coverage.observer_state = 1

    def fail_post_cut():
        raise RuntimeError(
            "synthetic runtime ownership failure"
        )

    with pytest.raises(
        CampaignInfrastructureError,
        match="method-specific post-cut hook failed",
    ):
        driver.complete_accepted_event(
            instruction_index=1,
            cycle=1,
            adapter_instruction_count=1,
            observe_coverage=observe,
            snapshot_factory=lambda max_intent: (
                lifecycle_snapshot(
                    accepted=1,
                    cycle=1,
                    max_intent=max_intent,
                )
            ),
            after_post_instruction_cut=(
                fail_post_cut
            ),
        )

    # Exact cut must not be committed after method-specific
    # ownership cleanup failed.
    assert not driver.exact_cut_requested
    assert driver.accepted_count == 0
