from __future__ import annotations

import re

import pytest

from research.week5.impl.execution_event import (
    ExecutionEvent,
)
from research.week10.adaptive.wrap_aware_architectural_model import (
    WrapAwareRV32ArchitecturalModel,
)
from research.week13.pure_random.campaign_seed import (
    build_campaign_rngs,
)
from research.week13.pure_random.family_sampler import (
    InstructionFamily,
    sample_family,
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


@pytest.mark.parametrize(
    "budget",
    tuple(range(1, 65)),
)
def test_exact_accepted_prefix_for_small_budgets(
    budget: int,
):
    plan = generate_pure_random_plan(
        ROOT,
        budget,
    )

    assert (
        plan.accepted_instruction_count
        == budget
    )

    assert sum(
        block.accepted_instruction_count
        for block in plan.blocks
    ) == budget

    partial = [
        block
        for block in plan.blocks
        if block.is_partial
    ]

    assert len(partial) <= 1

    if partial:
        assert partial[0] is plan.blocks[-1]


def test_budget_three_terminates_inside_known_jalr_block():
    """
    Frozen root 11001 family prefix:

        ADD, LW, JALR, ...

    ADD contributes 1 accepted instruction.
    LW contributes 1.
    JALR normally contributes executed offsets (0,3).

    Budget 3 therefore consumes only JALR offset 0 and discards
    the remaining resident suffix.
    """
    plan = generate_pure_random_plan(
        ROOT,
        3,
    )

    assert len(plan.blocks) == 3

    final = plan.blocks[-1]

    assert (
        final.realized.family
        is InstructionFamily.JALR
    )

    assert (
        final.realized
        .expected_executed_word_indices
        == (0, 3)
    )

    assert (
        final.accepted_word_indices
        == (0,)
    )

    assert final.is_partial


def test_same_seed_same_budget_produces_identical_plan():
    first = generate_pure_random_plan(
        ROOT,
        256,
    )

    second = generate_pure_random_plan(
        ROOT,
        256,
    )

    assert first == second
    assert first.plan_hash == second.plan_hash


def test_different_seed_changes_plan_hash():
    first = generate_pure_random_plan(
        11001,
        256,
    )

    second = generate_pure_random_plan(
        11002,
        256,
    )

    assert first.plan_hash != second.plan_hash


def test_plan_hash_is_sha256_hex():
    plan = generate_pure_random_plan(
        ROOT,
        128,
    )

    assert re.fullmatch(
        r"[0-9a-f]{64}",
        plan.plan_hash,
    )


def test_family_trace_matches_independent_family_stream():
    plan = generate_pure_random_plan(
        ROOT,
        256,
    )

    independent = build_campaign_rngs(
        ROOT
    )

    expected = tuple(
        sample_family(
            independent.family_rng
        )
        for _ in range(
            len(plan.blocks)
        )
    )

    observed = tuple(
        block.realized.family
        for block in plan.blocks
    )

    assert observed == expected


def test_complete_plan_replays_cleanly_through_golden():
    plan = generate_pure_random_plan(
        ROOT,
        512,
    )

    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    instruction_index = 1

    for block in plan.blocks:
        for word_index in (
            block.accepted_word_indices
        ):
            pc = (
                block.realized
                .physical_pc_for_word(
                    word_index
                )
            )

            assert pc == model.expected_pc

            step = model.step(
                _event(
                    instruction_index,
                    pc,
                    block.realized.words[
                        word_index
                    ],
                )
            )

            assert step.pc_match
            instruction_index += 1

    assert (
        instruction_index - 1
        == plan.accepted_instruction_count
    )

    assert (
        model.expected_pc
        == plan.final_expected_pc
    )


def test_all_block_start_pcs_are_canonical():
    plan = generate_pure_random_plan(
        ROOT,
        1024,
    )

    for block in plan.blocks:
        assert (
            0
            <= block.realized.start_pc
            <= 508
        )

        assert (
            block.realized.start_pc
            % 4
            == 0
        )


@pytest.mark.parametrize(
    "invalid",
    (
        0,
        -1,
        True,
        1.5,
        "100",
        None,
    ),
)
def test_invalid_budget_is_rejected(
    invalid,
):
    with pytest.raises(
        ValueError,
        match="accepted_budget must be",
    ):
        generate_pure_random_plan(
            ROOT,
            invalid,  # type: ignore[arg-type]
        )

@pytest.mark.parametrize(
    (
        "root_seed",
        "expected_blocks",
        "expected_final_pc",
        "expected_hash",
    ),
    (
        (
            11001,
            6863,
            0x98,
            "f77c00eab3636c4ce89c4d882d254d0af85f8515f641c29268226e27ac6a329a",
        ),
        (
            11002,
            6915,
            0x48,
            "87f5529359d0b9e142cb4083c3ba5d1a7aec0bf19582885d36733649cd3af103",
        ),
        (
            11003,
            6924,
            0x00,
            "d9ab04a387f4e13e247e0d20e39f8ee877dcf7422128c46027f326757b5dca28",
        ),
    ),
)
def test_pilot_10k_plan_known_answer(
    root_seed: int,
    expected_blocks: int,
    expected_final_pc: int,
    expected_hash: str,
):
    plan = generate_pure_random_plan(
        root_seed,
        10_000,
    )

    assert plan.accepted_instruction_count == 10_000
    assert len(plan.blocks) == expected_blocks
    assert plan.final_expected_pc == expected_final_pc
    assert plan.plan_hash == expected_hash

    # These three frozen pilot plans happen to terminate exactly
    # at a complete block boundary.
    assert not plan.blocks[-1].is_partial
