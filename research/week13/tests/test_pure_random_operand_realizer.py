from __future__ import annotations

from random import Random

import pytest

from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week5.impl.rv32_encode import (
    add,
    addi,
    auipc,
    lui,
    lw,
    sw,
)

from research.week13.pure_random.campaign_seed import (
    build_campaign_rngs,
)
from research.week13.pure_random.family_sampler import (
    InstructionFamily,
)
from research.week13.pure_random.operand_realizer import (
    MemoryBaseChoice,
    memory_base_choices,
    realize_non_control,
    signed32,
)


PILOT_ROOT = 11001


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        (0x00000000, 0),
        (0x00000001, 1),
        (0x7FFFFFFF, 2147483647),
        (0x80000000, -2147483648),
        (0xFFFFFFFF, -1),
        (0x100000000, 0),
        (0x1FFFFFFFF, -1),
    ),
)
def test_signed32_boundaries(
    raw: int,
    expected: int,
):
    assert signed32(raw) == expected


def test_memory_choices_include_x0_for_every_canonical_ea():
    registers = tuple(
        0 for _ in range(32)
    )

    for effective_address in range(
        0,
        512,
        4,
    ):
        choices = memory_base_choices(
            registers,
            effective_address,
        )

        assert choices

        assert MemoryBaseChoice(
            rs1=0,
            immediate=effective_address,
        ) in choices


def test_memory_choices_are_state_dependent():
    registers = [0] * 32

    # x1 cannot reach EA=508 with signed imm12.
    registers[1] = 0x10000000

    # x2 reaches 508 with immediate -4.
    registers[2] = 512

    choices = memory_base_choices(
        tuple(registers),
        508,
    )

    by_register = {
        choice.rs1: choice.immediate
        for choice in choices
    }

    assert 0 in by_register
    assert by_register[0] == 508

    assert 1 not in by_register

    assert by_register[2] == -4


def _fresh_operand_rng() -> Random:
    return build_campaign_rngs(
        PILOT_ROOT
    ).operand_rng


def test_known_answer_add_operands():
    result = realize_non_control(
        InstructionFamily.ADD,
        operand_rng=_fresh_operand_rng(),
        model=RV32ArchitecturalModel(),
        start_pc=0,
    )

    assert (
        result.rd,
        result.rs1,
        result.rs2,
    ) == (
        8,
        0,
        30,
    )

    assert result.words == (
        add(8, 0, 30),
    )

    assert (
        result.expected_executed_word_indices
        == (0,)
    )

    assert (
        result.structural_word_indices
        == ()
    )


def test_known_answer_addi_operands():
    result = realize_non_control(
        InstructionFamily.ADDI,
        operand_rng=_fresh_operand_rng(),
        model=RV32ArchitecturalModel(),
        start_pc=0,
    )

    assert (
        result.rd,
        result.rs1,
        result.immediate,
    ) == (
        8,
        0,
        1900,
    )

    assert result.words == (
        addi(8, 0, 1900),
    )


def test_known_answer_lw_operands():
    result = realize_non_control(
        InstructionFamily.LW,
        operand_rng=_fresh_operand_rng(),
        model=RV32ArchitecturalModel(),
        start_pc=0,
    )

    assert (
        result.effective_address,
        result.rs1,
        result.rd,
        result.immediate,
    ) == (
        248,
        0,
        20,
        248,
    )

    assert result.words == (
        lw(20, 0, 248),
    )


def test_known_answer_sw_operands():
    result = realize_non_control(
        InstructionFamily.SW,
        operand_rng=_fresh_operand_rng(),
        model=RV32ArchitecturalModel(),
        start_pc=0,
    )

    assert (
        result.effective_address,
        result.rs1,
        result.rs2,
        result.immediate,
    ) == (
        248,
        0,
        30,
        248,
    )

    assert result.words == (
        sw(30, 0, 248),
    )


@pytest.mark.parametrize(
    ("family", "encoder"),
    (
        (
            InstructionFamily.LUI,
            lui,
        ),
        (
            InstructionFamily.AUIPC,
            auipc,
        ),
    ),
)
def test_known_answer_u_type_operands(
    family,
    encoder,
):
    result = realize_non_control(
        family,
        operand_rng=_fresh_operand_rng(),
        model=RV32ArchitecturalModel(),
        start_pc=0,
    )

    assert (
        result.rd,
        result.immediate,
    ) == (
        8,
        16173,
    )

    assert result.words == (
        encoder(
            8,
            16173,
        ),
    )


@pytest.mark.parametrize(
    "family",
    (
        InstructionFamily.ADD,
        InstructionFamily.ADDI,
        InstructionFamily.LW,
        InstructionFamily.LUI,
        InstructionFamily.AUIPC,
    ),
)
def test_gpr_writing_payload_never_uses_x0_destination(
    family: InstructionFamily,
):
    rng = _fresh_operand_rng()
    model = RV32ArchitecturalModel()

    for _ in range(500):
        result = realize_non_control(
            family,
            operand_rng=rng,
            model=model,
            start_pc=0,
        )

        assert result.rd is not None
        assert 1 <= result.rd <= 31


@pytest.mark.parametrize(
    "family",
    (
        InstructionFamily.LW,
        InstructionFamily.SW,
    ),
)
def test_memory_realization_always_matches_canonical_ea(
    family: InstructionFamily,
):
    rng = _fresh_operand_rng()
    model = RV32ArchitecturalModel()

    for _ in range(500):
        result = realize_non_control(
            family,
            operand_rng=rng,
            model=model,
            start_pc=0,
        )

        assert result.effective_address is not None
        assert result.rs1 is not None
        assert result.immediate is not None

        base = model.read_register(
            result.rs1
        )

        realized_ea = (
            base
            + result.immediate
        ) & 0xFFFFFFFF

        assert (
            realized_ea
            == result.effective_address
        )

        assert (
            result.effective_address
            % 4
            == 0
        )

        assert (
            0
            <= result.effective_address
            <= 508
        )


@pytest.mark.parametrize(
    "family",
    (
        InstructionFamily.BRANCH,
        InstructionFamily.JAL,
        InstructionFamily.JALR,
    ),
)
def test_control_family_is_not_silently_realized_here(
    family: InstructionFamily,
):
    with pytest.raises(
        ValueError,
        match="control family requires",
    ):
        realize_non_control(
            family,
            operand_rng=_fresh_operand_rng(),
            model=RV32ArchitecturalModel(),
            start_pc=0,
        )
