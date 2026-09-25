from __future__ import annotations

from random import Random

import pytest

from research.week5.impl.execution_event import (
    ExecutionEvent,
)
from research.week5.impl.rv32_encode import (
    addi,
    bne,
    jal,
    jalr,
    nop,
)
from research.week10.adaptive.wrap_aware_architectural_model import (
    WrapAwareRV32ArchitecturalModel,
)
from research.week13.pure_random.campaign_seed import (
    build_campaign_rngs,
)
from research.week13.pure_random.control_realizer import (
    CONTROL_OFFSET,
    control_target_pc,
    jalr_immediate_for_target,
    realize_control,
)
from research.week13.pure_random.family_sampler import (
    InstructionFamily,
)


PILOT_ROOT = 11001


def _fresh_operand_rng() -> Random:
    return build_campaign_rngs(
        PILOT_ROOT
    ).operand_rng


def _event(
    index: int,
    pc: int,
    instruction: int,
) -> ExecutionEvent:
    return ExecutionEvent(
        instruction_index=index,
        cycle=index,
        pc=pc,
        instruction=instruction,
        rs1=(instruction >> 15) & 0x1F,
        rs2=(instruction >> 20) & 0x1F,
        rd=(instruction >> 7) & 0x1F,
        uses_rs1=False,
        uses_rs2=False,
        writes_rd=False,
        producer_type="NONE",
        consumer_type="NONE",
    )


def test_control_target_wraps_at_physical_boundary():
    assert control_target_pc(0) == 12
    assert control_target_pc(496) == 508
    assert control_target_pc(500) == 0
    assert control_target_pc(504) == 4
    assert control_target_pc(508) == 8


@pytest.mark.parametrize(
    ("register_value", "target", "expected"),
    (
        (0, 12, 12),
        (0, 508, -4),
        (512, 12, 12),
        (508, 0, 4),
        (0xFFFFFFFF, 0, 1),
        (0x10000004, 12, 8),
    ),
)
def test_jalr_immediate_derivation(
    register_value: int,
    target: int,
    expected: int,
):
    immediate = (
        jalr_immediate_for_target(
            register_value,
            target,
        )
    )

    assert immediate == expected

    raw_target = (
        register_value
        + immediate
    ) & 0xFFFFFFFF

    assert (
        raw_target & 0x1FF
    ) == target

    assert raw_target % 4 == 0


def test_known_answer_branch_initial_zero_state_is_not_taken():
    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    result = realize_control(
        InstructionFamily.BRANCH,
        operand_rng=_fresh_operand_rng(),
        model=model,
        start_pc=0,
    )

    # Fresh operand stream:
    # subtype index 1 -> BNE
    # rs1 = x0
    # rs2 = x30
    #
    # Initial architectural state has x0=x30=0,
    # therefore BNE is not taken.
    assert result.mnemonic == "BNE"
    assert result.rs1 == 0
    assert result.rs2 == 30
    assert result.immediate == 12

    assert result.words == (
        bne(0, 30, 12),
        nop(),
        nop(),
        nop(),
    )

    assert (
        result.expected_executed_word_indices
        == (0, 1, 2, 3)
    )

    assert (
        result.structural_word_indices
        == (1, 2, 3)
    )

    # Realization must not mutate the supplied model.
    assert model.expected_pc == 0
    assert model.read_register(30) == 0


def test_same_branch_becomes_taken_from_golden_state():
    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    # Establish x30=1 using the actual Golden model.
    setup_word = addi(
        30,
        0,
        1,
    )

    model.step(
        _event(
            1,
            0,
            setup_word,
        )
    )

    assert model.expected_pc == 4
    assert model.read_register(30) == 1

    result = realize_control(
        InstructionFamily.BRANCH,
        operand_rng=_fresh_operand_rng(),
        model=model,
        start_pc=4,
    )

    # The stochastic draw is still BNE x0,x30,+12.
    # Golden state now has 0 != 1, so it must be taken.
    assert result.mnemonic == "BNE"
    assert result.rs1 == 0
    assert result.rs2 == 30

    assert (
        result.expected_executed_word_indices
        == (0, 3)
    )

    # Speculation still must not advance the supplied model.
    assert model.expected_pc == 4
    assert model.read_register(30) == 1


def test_known_answer_jal():
    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    result = realize_control(
        InstructionFamily.JAL,
        operand_rng=_fresh_operand_rng(),
        model=model,
        start_pc=0,
    )

    assert result.rd == 8
    assert result.immediate == CONTROL_OFFSET

    assert result.words == (
        jal(8, 12),
        nop(),
        nop(),
        nop(),
    )

    assert (
        result.expected_executed_word_indices
        == (0, 3)
    )

    assert model.expected_pc == 0


def test_known_answer_jalr():
    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    result = realize_control(
        InstructionFamily.JALR,
        operand_rng=_fresh_operand_rng(),
        model=model,
        start_pc=0,
    )

    assert result.rd == 8
    assert result.rs1 == 0
    assert result.immediate == 12

    assert result.words == (
        jalr(8, 0, 12),
        nop(),
        nop(),
        nop(),
    )

    assert (
        result.expected_executed_word_indices
        == (0, 3)
    )

    raw_target = (
        model.read_register(
            result.rs1
        )
        + result.immediate
    ) & 0xFFFFFFFF

    assert raw_target % 4 == 0
    assert (
        raw_target & 0x1FF
    ) == 12

    assert model.expected_pc == 0


@pytest.mark.parametrize(
    "family",
    (
        InstructionFamily.JAL,
        InstructionFamily.JALR,
    ),
)
def test_jump_control_wraps_from_pc_508(
    family: InstructionFamily,
):
    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    # Public expected_pc is the wrapper's fetch-state scalar.
    model.expected_pc = 508

    result = realize_control(
        family,
        operand_rng=_fresh_operand_rng(),
        model=model,
        start_pc=508,
    )

    assert control_target_pc(508) == 8

    assert (
        result.expected_executed_word_indices
        == (0, 3)
    )

    assert (
        result.physical_pc_for_word(3)
        == 8
    )

    assert model.expected_pc == 508


def test_jalr_raw_target_is_always_word_aligned():
    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    rng = _fresh_operand_rng()

    for start_pc in range(
        0,
        512,
        4,
    ):
        model.expected_pc = start_pc

        result = realize_control(
            InstructionFamily.JALR,
            operand_rng=rng,
            model=model,
            start_pc=start_pc,
        )

        assert result.rs1 is not None
        assert result.immediate is not None

        raw_target = (
            model.read_register(
                result.rs1
            )
            + result.immediate
        ) & 0xFFFFFFFF

        assert raw_target % 4 == 0

        assert (
            raw_target & 0x1FF
        ) == control_target_pc(
            start_pc
        )


def test_wrong_start_pc_is_rejected():
    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    with pytest.raises(
        ValueError,
        match="model.expected_pc",
    ):
        realize_control(
            InstructionFamily.JAL,
            operand_rng=_fresh_operand_rng(),
            model=model,
            start_pc=4,
        )


def test_non_control_family_is_rejected():
    with pytest.raises(
        ValueError,
        match="family must be BRANCH",
    ):
        realize_control(
            InstructionFamily.ADD,
            operand_rng=_fresh_operand_rng(),
            model=WrapAwareRV32ArchitecturalModel(),
            start_pc=0,
        )
