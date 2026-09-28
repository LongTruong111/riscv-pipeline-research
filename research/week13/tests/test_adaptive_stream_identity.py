import pytest

from research.week10.adaptive.production_campaign import (
    ProductionCampaignConfig,
    build_production_adaptive_stack,
)
from research.week13.adaptive.stream_identity import (
    AdaptiveStreamIdentityProtocolError,
    peek_expected_accepted_identity,
)


def build_stack():
    config = ProductionCampaignConfig(
        seed=13001,
        epsilon=0.05,
        alpha=0.1,
        q_floor=0.05,
        nominal_batch=500,
        instruction_budget=10_000,
        checkpoint_interval=1_000,
    )

    return build_production_adaptive_stack(
        config=config
    )


def test_peek_boundary_identity_is_read_only():
    stack = build_stack()

    stack.planner.begin_epoch()

    boundary = (
        stack.planner
        .active_boundary_delimiter
    )

    assert boundary is not None

    stack.window.commit_patched_block(
        boundary
    )

    tracker = getattr(
        stack.window,
        "_accepted_tracker",
    )

    before = (
        tracker.accepted_count,
        tracker.next_expected_instruction_index,
        tracker.current_block_progress,
        tracker.pending_entries,
        stack.window.used_words,
    )

    expected = (
        peek_expected_accepted_identity(
            stack.window
        )
    )

    after = (
        tracker.accepted_count,
        tracker.next_expected_instruction_index,
        tracker.current_block_progress,
        tracker.pending_entries,
        stack.window.used_words,
    )

    assert after == before

    assert expected.instruction_index == 1
    assert expected.entry_progress == 0

    assert (
        expected.stream_entry_key
        == boundary.stream_entry_key
    )

    assert (
        expected.pc
        == boundary.expected_executed_pcs[0]
    )

    assert (
        expected.instruction
        == boundary.expected_executed_words[0]
    )

    assert (
        expected.logical_word_index
        == (
            boundary.logical_word_start
            + boundary
            .expected_executed_word_offsets[0]
        )
    )


def test_repeated_peek_is_deterministic():
    stack = build_stack()

    stack.planner.begin_epoch()

    boundary = (
        stack.planner
        .active_boundary_delimiter
    )

    assert boundary is not None

    stack.window.commit_patched_block(
        boundary
    )

    first = (
        peek_expected_accepted_identity(
            stack.window
        )
    )

    second = (
        peek_expected_accepted_identity(
            stack.window
        )
    )

    assert first == second
    assert stack.window.accepted_count == 0


def test_peek_rejects_empty_runtime_window():
    stack = build_stack()

    with pytest.raises(
        AdaptiveStreamIdentityProtocolError,
        match="no pending adaptive stream entry",
    ):
        peek_expected_accepted_identity(
            stack.window
        )
