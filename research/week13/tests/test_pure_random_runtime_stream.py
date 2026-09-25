from __future__ import annotations

import pytest

from research.week5.impl.execution_event import (
    ExecutionEvent,
)
from research.week13.pure_random.runtime_stream import (
    IMEM_WORD_CAPACITY,
    PureRandomRuntimeWindow,
    PureRandomStreamExecutionMismatch,
    PureRandomStreamPlanningError,
    build_runtime_entries,
    physical_pc_for_logical_word,
)
from research.week13.pure_random.stream_planner import (
    generate_pure_random_plan,
)


ROOT = 11001


def _event(
    index: int,
    pc: int,
    word: int,
) -> ExecutionEvent:
    return ExecutionEvent(
        instruction_index=index,
        cycle=index,
        pc=pc,
        instruction=word,
        rs1=(word >> 15) & 0x1F,
        rs2=(word >> 20) & 0x1F,
        rd=(word >> 7) & 0x1F,
        uses_rs1=False,
        uses_rs2=False,
        writes_rd=False,
        producer_type="NONE",
        consumer_type="NONE",
    )


def test_physical_ring_mapping():
    assert physical_pc_for_logical_word(0) == 0
    assert physical_pc_for_logical_word(1) == 4
    assert physical_pc_for_logical_word(127) == 508

    assert physical_pc_for_logical_word(128) == 0
    assert physical_pc_for_logical_word(129) == 4
    assert physical_pc_for_logical_word(255) == 508
    assert physical_pc_for_logical_word(256) == 0


def test_runtime_entries_follow_offline_physical_pcs():
    plan = generate_pure_random_plan(
        ROOT,
        512,
    )

    entries = build_runtime_entries(
        plan
    )

    assert len(entries) == len(plan.blocks)

    previous_end = 0

    for entry in entries:
        assert (
            entry.logical_word_start
            == previous_end
        )

        assert (
            entry.physical_word_addresses[0]
            == entry.planned.realized.start_pc
        )

        previous_end = (
            entry.logical_word_end_exclusive
        )


def test_budget_three_retains_full_final_jalr_runtime_path():
    plan = generate_pure_random_plan(
        ROOT,
        3,
    )

    entries = build_runtime_entries(
        plan
    )

    final = entries[-1]

    assert (
        final.planned_accepted_word_offsets
        == (0,)
    )

    # Runtime must retain the full path so the hard cap, rather than
    # fake block completion, performs final suffix reclamation.
    assert (
        final.expected_executed_word_offsets
        == (0, 3)
    )


def test_runtime_window_exact_three_discards_jalr_suffix():
    plan = generate_pure_random_plan(
        ROOT,
        3,
    )

    entries = build_runtime_entries(
        plan
    )

    window = PureRandomRuntimeWindow()

    for entry in entries:
        assert window.can_commit(
            entry
        )

        window.commit_patched_entry(
            entry
        )

    instruction_index = 1

    # Consume exactly the offline accepted prefix.
    for entry in entries:
        for word_offset in (
            entry
            .planned_accepted_word_offsets
        ):
            pc = physical_pc_for_logical_word(
                entry.logical_word_start
                + word_offset
            )

            word = entry.image_words[
                word_offset
            ]

            window.finalize_accepted_event(
                _event(
                    instruction_index,
                    pc,
                    word,
                )
            )

            instruction_index += 1

    assert window.accepted_count == 3

    # First two single-word entries completed/released.
    # Final JALR head is still resident after accepting offset 0 only.
    assert window.pending_entry_count == 1

    discarded = (
        window.discard_unexecuted_suffix()
    )

    assert (
        discarded
        .accepted_count_at_termination
        == 3
    )

    assert (
        discarded
        .head_accepted_instruction_count
        == 1
    )

    assert (
        discarded
        .discarded_expected_instruction_count
        == 1
    )

    assert window.accepted_count == 3
    assert window.pending_entry_count == 0
    assert window.used_words == 0


def test_stream_mismatch_does_not_increment_accepted_count():
    plan = generate_pure_random_plan(
        ROOT,
        1,
    )

    entry = build_runtime_entries(
        plan
    )[0]

    window = PureRandomRuntimeWindow()

    window.commit_patched_entry(
        entry
    )

    expected_pc = (
        entry.expected_executed_pcs[0]
    )

    expected_word = (
        entry.expected_executed_words[0]
    )

    with pytest.raises(
        PureRandomStreamExecutionMismatch,
        match="accepted PC diverged",
    ):
        window.finalize_accepted_event(
            _event(
                1,
                (expected_pc + 4) & 0x1FF,
                expected_word,
            )
        )

    assert window.accepted_count == 0


def test_runtime_ring_never_exceeds_128_words():
    plan = generate_pure_random_plan(
        ROOT,
        1000,
    )

    entries = build_runtime_entries(
        plan
    )

    window = PureRandomRuntimeWindow()

    next_entry = 0
    instruction_index = 1

    while (
        next_entry < len(entries)
        or window.pending_entry_count > 0
    ):
        # Fill every currently available complete-block slot.
        while (
            next_entry < len(entries)
            and window.can_commit(
                entries[next_entry]
            )
        ):
            window.commit_patched_entry(
                entries[next_entry]
            )

            assert (
                window.used_words
                <= IMEM_WORD_CAPACITY
            )

            next_entry += 1

        if window.pending_entry_count == 0:
            continue

        head = (
            window._ring.entries[0]
        )

        for offset in (
            head.expected_executed_word_offsets
        ):
            pc = physical_pc_for_logical_word(
                head.logical_word_start
                + offset
            )

            word = head.image_words[
                offset
            ]

            completed = (
                window.finalize_accepted_event(
                    _event(
                        instruction_index,
                        pc,
                        word,
                    )
                )
            )

            instruction_index += 1

        assert completed is not None

    assert window.used_words == 0
    assert window.pending_entry_count == 0
