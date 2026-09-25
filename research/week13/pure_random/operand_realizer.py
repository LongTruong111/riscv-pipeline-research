from __future__ import annotations

from dataclasses import dataclass
from random import Random

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

from research.week13.pure_random.family_sampler import (
    InstructionFamily,
)
from research.week13.pure_random.realized_block import (
    RealizedPureRandomBlock,
)


MASK32 = 0xFFFFFFFF

SIGNED12_MIN = -2048
SIGNED12_MAX = 2047

DMEM_BYTES = 512
DMEM_WORD_BYTES = 4


@dataclass(frozen=True)
class MemoryBaseChoice:
    rs1: int
    immediate: int


def signed32(
    value: int,
) -> int:
    """
    Interpret the low 32 bits of value as a signed RV32 integer.
    """
    value &= MASK32

    if value < 0x80000000:
        return value

    return value - 0x100000000


def memory_base_choices(
    registers: tuple[int, ...],
    effective_address: int,
) -> tuple[MemoryBaseChoice, ...]:
    """
    Return all x0..x31 bases that can realize the canonical EA using
    one signed 12-bit immediate.

    Candidate ordering is architectural register order x0..x31.
    """
    if len(registers) != 32:
        raise ValueError(
            "register state must contain exactly 32 GPR values"
        )

    if (registers[0] & MASK32) != 0:
        raise ValueError(
            "architectural x0 must be zero"
        )

    if (
        not 0 <= effective_address < DMEM_BYTES
        or effective_address % DMEM_WORD_BYTES != 0
    ):
        raise ValueError(
            "effective_address must be one of "
            "{0,4,...,508}"
        )

    choices: list[MemoryBaseChoice] = []

    for rs1, register_value in enumerate(
        registers
    ):
        delta = signed32(
            (
                effective_address
                - (register_value & MASK32)
            )
            & MASK32
        )

        if (
            SIGNED12_MIN
            <= delta
            <= SIGNED12_MAX
        ):
            choices.append(
                MemoryBaseChoice(
                    rs1=rs1,
                    immediate=delta,
                )
            )

    if not choices:
        raise AssertionError(
            "canonical memory EA must always have at least x0 viable"
        )

    return tuple(choices)


def _validate_operand_rng(
    operand_rng: Random,
) -> None:
    if not isinstance(
        operand_rng,
        Random,
    ):
        raise TypeError(
            "operand_rng must be random.Random"
        )


def _validate_model(
    model: RV32ArchitecturalModel,
) -> None:
    if not isinstance(
        model,
        RV32ArchitecturalModel,
    ):
        raise TypeError(
            "model must be an RV32ArchitecturalModel"
        )


def _validate_start_pc(
    start_pc: int,
) -> None:
    if (
        isinstance(start_pc, bool)
        or not isinstance(start_pc, int)
        or not 0 <= start_pc <= 508
        or start_pc % 4 != 0
    ):
        raise ValueError(
            "start_pc must be aligned in 0..508"
        )


def _single_word_block(
    *,
    family: InstructionFamily,
    mnemonic: str,
    start_pc: int,
    word: int,
    rd: int | None = None,
    rs1: int | None = None,
    rs2: int | None = None,
    immediate: int | None = None,
    effective_address: int | None = None,
) -> RealizedPureRandomBlock:
    return RealizedPureRandomBlock(
        family=family,
        mnemonic=mnemonic,
        start_pc=start_pc,
        words=(word,),
        expected_executed_word_indices=(0,),
        structural_word_indices=(),
        rd=rd,
        rs1=rs1,
        rs2=rs2,
        immediate=immediate,
        effective_address=effective_address,
    )


def realize_non_control(
    family: InstructionFamily,
    *,
    operand_rng: Random,
    model: RV32ArchitecturalModel,
    start_pc: int,
) -> RealizedPureRandomBlock:
    """
    Realize one non-control M1-PR payload family.

    This function consumes operand_rng only.

    Supported here:
        ADD, ADDI, LW, SW, LUI, AUIPC

    BRANCH/JAL/JALR are deliberately handled later by the
    shadow-aware control-flow realizer.
    """
    _validate_operand_rng(
        operand_rng
    )

    _validate_model(
        model
    )

    _validate_start_pc(
        start_pc
    )

    if family is InstructionFamily.ADD:
        rd = operand_rng.randrange(1, 32)
        rs1 = operand_rng.randrange(0, 32)
        rs2 = operand_rng.randrange(0, 32)

        return _single_word_block(
            family=family,
            mnemonic="ADD",
            start_pc=start_pc,
            word=add(
                rd,
                rs1,
                rs2,
            ),
            rd=rd,
            rs1=rs1,
            rs2=rs2,
        )

    if family is InstructionFamily.ADDI:
        rd = operand_rng.randrange(1, 32)
        rs1 = operand_rng.randrange(0, 32)
        immediate = operand_rng.randrange(
            SIGNED12_MIN,
            SIGNED12_MAX + 1,
        )

        return _single_word_block(
            family=family,
            mnemonic="ADDI",
            start_pc=start_pc,
            word=addi(
                rd,
                rs1,
                immediate,
            ),
            rd=rd,
            rs1=rs1,
            immediate=immediate,
        )

    if family is InstructionFamily.LW:
        # Frozen draw order:
        # EA -> rs1 from V(EA) -> rd
        effective_address = operand_rng.randrange(
            0,
            DMEM_BYTES,
            DMEM_WORD_BYTES,
        )

        choices = memory_base_choices(
            model.registers(),
            effective_address,
        )

        base = operand_rng.choice(
            choices
        )

        rd = operand_rng.randrange(
            1,
            32,
        )

        return _single_word_block(
            family=family,
            mnemonic="LW",
            start_pc=start_pc,
            word=lw(
                rd,
                base.rs1,
                base.immediate,
            ),
            rd=rd,
            rs1=base.rs1,
            immediate=base.immediate,
            effective_address=effective_address,
        )

    if family is InstructionFamily.SW:
        # Frozen draw order:
        # EA -> rs1 from V(EA) -> rs2
        effective_address = operand_rng.randrange(
            0,
            DMEM_BYTES,
            DMEM_WORD_BYTES,
        )

        choices = memory_base_choices(
            model.registers(),
            effective_address,
        )

        base = operand_rng.choice(
            choices
        )

        rs2 = operand_rng.randrange(
            0,
            32,
        )

        return _single_word_block(
            family=family,
            mnemonic="SW",
            start_pc=start_pc,
            word=sw(
                rs2,
                base.rs1,
                base.immediate,
            ),
            rs1=base.rs1,
            rs2=rs2,
            immediate=base.immediate,
            effective_address=effective_address,
        )

    if family is InstructionFamily.LUI:
        rd = operand_rng.randrange(
            1,
            32,
        )

        immediate = operand_rng.randrange(
            0,
            1 << 20,
        )

        return _single_word_block(
            family=family,
            mnemonic="LUI",
            start_pc=start_pc,
            word=lui(
                rd,
                immediate,
            ),
            rd=rd,
            immediate=immediate,
        )

    if family is InstructionFamily.AUIPC:
        rd = operand_rng.randrange(
            1,
            32,
        )

        immediate = operand_rng.randrange(
            0,
            1 << 20,
        )

        return _single_word_block(
            family=family,
            mnemonic="AUIPC",
            start_pc=start_pc,
            word=auipc(
                rd,
                immediate,
            ),
            rd=rd,
            immediate=immediate,
        )

    if family in (
        InstructionFamily.BRANCH,
        InstructionFamily.JAL,
        InstructionFamily.JALR,
    ):
        raise ValueError(
            "control family requires shadow-aware control realizer"
        )

    raise ValueError(
        f"unsupported family: {family!r}"
    )
