from __future__ import annotations

from dataclasses import dataclass

from research.week5.impl.execution_event import (
    ExecutionEvent,
)
from research.week13.pure_random.runtime_stream import (
    IMEM_WORD_CAPACITY,
    PureRandomRuntimeEntry,
    PureRandomRuntimeWindow,
)
from research.week14.weighted_random.runtime_adapter import (
    WeightedRandomRuntimeEntry,
    build_weighted_runtime_entries,
)
from research.week14.weighted_random.static_generator import (
    WeightedRandomPlan,
    generate_weighted_random_plan,
)


SEED = 14001
N = 1000

EXPECTED_PLAN_HASH = (
    "3b23d6e4887e305100542416c77f9399"
    "4b229c9f9dab91ac4c0ac9f86465d2c9"
)


@dataclass(frozen=True)
class ReplayResult:
    accepted: int
    max_resident_words: int
    final_pending_entries: int
    final_used_words: int
    suffix_discarded: bool
    last_logical_generation: int


def event_for(
    *,
    instruction_index: int,
    entry: WeightedRandomRuntimeEntry,
    offset: int,
) -> ExecutionEvent:
    logical_word = (
        entry.logical_word_start
        + offset
    )

    pc = (
        logical_word * 4
    ) & 0x1FF

    return ExecutionEvent(
        instruction_index=(
            instruction_index
        ),
        cycle=instruction_index,
        pc=pc,
        instruction=(
            entry.image_words[offset]
        ),
        rs1=0,
        rs2=0,
        rd=0,
        uses_rs1=False,
        uses_rs2=False,
        writes_rd=False,
        producer_type="NONE",
        consumer_type="NONE",
        stall_cycles_before_accept=0,
        forward_a=0,
        forward_b=0,
    )


def replay_plan(
    plan: WeightedRandomPlan,
) -> ReplayResult:
    entries = build_weighted_runtime_entries(
        plan
    )

    window = PureRandomRuntimeWindow()

    next_entry = 0
    max_resident_words = 0

    def refill() -> None:
        nonlocal next_entry
        nonlocal max_resident_words

        while next_entry < len(entries):
            entry = entries[next_entry]

            if not window.can_commit(entry):
                break

            window.commit_patched_entry(
                entry
            )

            next_entry += 1

            max_resident_words = max(
                max_resident_words,
                window.used_words,
            )

            assert (
                window.used_words
                <= IMEM_WORD_CAPACITY
            )

    refill()

    accepted_sequence = [
        (
            entry,
            offset,
        )
        for entry in entries
        for offset in (
            entry
            .planned_accepted_word_offsets
        )
    ]

    assert (
        len(accepted_sequence)
        == plan.accepted_instruction_budget
    )

    last_logical_word = 0

    for instruction_index, (
        entry,
        offset,
    ) in enumerate(
        accepted_sequence,
        start=1,
    ):
        logical_word = (
            entry.logical_word_start
            + offset
        )

        last_logical_word = (
            logical_word
        )

        event = event_for(
            instruction_index=(
                instruction_index
            ),
            entry=entry,
            offset=offset,
        )

        completed = (
            window.finalize_accepted_event(
                event
            )
        )

        assert (
            window.accepted_count
            == instruction_index
        )

        if completed is not None:
            refill()

        assert (
            window.used_words
            <= IMEM_WORD_CAPACITY
        )

    assert next_entry == len(entries)

    suffix_discarded = False

    if window.pending_entry_count:
        discarded = (
            window
            .discard_unexecuted_suffix()
        )

        suffix_discarded = True

        assert (
            discarded
            .accepted_count_at_termination
            == plan.accepted_instruction_budget
        )

    return ReplayResult(
        accepted=window.accepted_count,
        max_resident_words=(
            max_resident_words
        ),
        final_pending_entries=(
            window.pending_entry_count
        ),
        final_used_words=(
            window.used_words
        ),
        suffix_discarded=(
            suffix_discarded
        ),
        last_logical_generation=(
            last_logical_word
            // IMEM_WORD_CAPACITY
        ),
    )


def test_adapter_is_frozen_runtime_subtype():
    plan = generate_weighted_random_plan(
        SEED,
        32,
    )

    entries = build_weighted_runtime_entries(
        plan
    )

    assert entries

    assert all(
        isinstance(
            entry,
            PureRandomRuntimeEntry,
        )
        for entry in entries
    )

    assert all(
        isinstance(
            entry,
            WeightedRandomRuntimeEntry,
        )
        for entry in entries
    )

    assert all(
        entry.stream_entry_key
        == ("M2", entry.block_index)
        for entry in entries
    )


def test_runtime_adapter_preserves_plan_identity():
    plan = generate_weighted_random_plan(
        SEED,
        N,
    )

    assert plan.plan_hash == (
        EXPECTED_PLAN_HASH
    )

    entries = build_weighted_runtime_entries(
        plan
    )

    assert len(entries) == len(plan.blocks)

    for entry, block in zip(
        entries,
        plan.blocks,
        strict=True,
    ):
        assert (
            entry.planned
            is block
        )

        assert (
            entry.image_words
            == block.realized.words
        )

        assert (
            entry
            .planned_accepted_word_offsets
            == block.accepted_word_indices
        )

        assert (
            entry
            .expected_executed_word_offsets
            == block.realized
            .expected_executed_word_indices
        )


def test_seed14001_n1000_bounded_replay():
    plan = generate_weighted_random_plan(
        SEED,
        N,
    )

    result = replay_plan(plan)

    assert result.accepted == N

    assert (
        result.max_resident_words
        <= IMEM_WORD_CAPACITY
    )

    assert result.final_pending_entries == 0
    assert result.final_used_words == 0

    # 1048 image words prove many physical
    # IMEM generations are crossed.
    assert plan.image_word_count == 1048

    assert (
        result.last_logical_generation
        >= 7
    )


def test_partial_final_block_exact_cut():
    """
    Explicitly exercise the hard-cap suffix path.

    N=1000 happens to land on a complete M2 block,
    so search a nearby deterministic non-final budget
    whose final template is partial.
    """
    selected = None

    for budget in range(980, 1000):
        candidate = (
            generate_weighted_random_plan(
                SEED,
                budget,
            )
        )

        if candidate.blocks[-1].is_partial:
            selected = candidate
            break

    assert selected is not None
    assert selected.blocks[-1].is_partial

    result = replay_plan(selected)

    assert (
        result.accepted
        == selected
        .accepted_instruction_budget
    )

    assert result.suffix_discarded is True
    assert result.final_pending_entries == 0
    assert result.final_used_words == 0


def test_replay_is_deterministic():
    a = generate_weighted_random_plan(
        SEED,
        N,
    )

    b = generate_weighted_random_plan(
        SEED,
        N,
    )

    assert a.plan_hash == b.plan_hash

    assert replay_plan(a) == replay_plan(b)
