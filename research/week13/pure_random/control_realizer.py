from __future__ import annotations

from copy import deepcopy
from random import Random
from typing import Callable

from research.week5.impl.execution_event import (
    ExecutionEvent,
)
from research.week5.impl.rv32_encode import (
    beq,
    bge,
    bgeu,
    blt,
    bltu,
    bne,
    jal,
    jalr,
    nop,
)
from research.week10.adaptive.wrap_aware_architectural_model import (
    WrapAwareRV32ArchitecturalModel,
)
from research.week13.pure_random.family_sampler import (
    InstructionFamily,
)
from research.week13.pure_random.realized_block import (
    RealizedPureRandomBlock,
)


CONTROL_OFFSET = 12
PHYSICAL_PC_MASK = 0x1FF

BRANCH_VARIANTS: tuple[
    tuple[str, Callable[[int, int, int], int]],
    ...,
] = (
    ("BEQ", beq),
    ("BNE", bne),
    ("BLT", blt),
    ("BGE", bge),
    ("BLTU", bltu),
    ("BGEU", bgeu),
)


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
    model: WrapAwareRV32ArchitecturalModel,
) -> None:
    if not isinstance(
        model,
        WrapAwareRV32ArchitecturalModel,
    ):
        raise TypeError(
            "model must be a "
            "WrapAwareRV32ArchitecturalModel"
        )


def _validate_start_pc(
    model: WrapAwareRV32ArchitecturalModel,
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

    if start_pc != model.expected_pc:
        raise ValueError(
            "start_pc must equal model.expected_pc: "
            f"start_pc={start_pc:#x}, "
            f"expected_pc={model.expected_pc:#x}"
        )


def control_target_pc(
    start_pc: int,
) -> int:
    return (
        start_pc
        + CONTROL_OFFSET
    ) & PHYSICAL_PC_MASK


def jalr_immediate_for_target(
    register_value: int,
    target_pc: int,
) -> int:
    """
    Derive the frozen canonical JALR signed immediate.

    Only the DUT-visible low 9 address bits participate in physical
    fetch targeting.

        v = R[rs1] & 0x1ff
        d = (target - v) mod 512

        imm = d       if d < 256
              d-512   otherwise

    Therefore imm is always in [-256, 255].
    """
    if (
        isinstance(register_value, bool)
        or not isinstance(register_value, int)
    ):
        raise TypeError(
            "register_value must be an integer"
        )

    if (
        isinstance(target_pc, bool)
        or not isinstance(target_pc, int)
        or not 0 <= target_pc <= 508
        or target_pc % 4 != 0
    ):
        raise ValueError(
            "target_pc must be aligned in 0..508"
        )

    visible_base = (
        register_value
        & PHYSICAL_PC_MASK
    )

    distance = (
        target_pc
        - visible_base
    ) % 512

    if distance < 256:
        immediate = distance
    else:
        immediate = distance - 512

    if not -256 <= immediate <= 255:
        raise AssertionError(
            "canonical JALR immediate outside "
            "frozen range"
        )

    return immediate


def _speculative_step(
    model: WrapAwareRV32ArchitecturalModel,
    *,
    pc: int,
    instruction: int,
):
    """
    Execute one instruction on an isolated copy of the shadow model.

    This deliberately reuses the frozen Golden semantic implementation
    rather than duplicating branch signed/unsigned comparison logic.

    The frozen Week-5 model does not expose its next instruction index
    publicly, so the private counter is read only from the disposable
    copy and is isolated here.
    """
    probe = deepcopy(
        model
    )

    last_index = getattr(
        probe,
        "_last_instruction_index",
        None,
    )

    if (
        isinstance(last_index, bool)
        or not isinstance(last_index, int)
        or last_index < 0
    ):
        raise RuntimeError(
            "architectural model instruction-index "
            "state is unavailable"
        )

    event = ExecutionEvent(
        instruction_index=(
            last_index + 1
        ),
        cycle=(
            last_index + 1
        ),
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

    return probe.step(
        event
    )


def _control_block(
    *,
    family: InstructionFamily,
    mnemonic: str,
    start_pc: int,
    control_word: int,
    expected_indices: tuple[int, ...],
    rd: int | None = None,
    rs1: int | None = None,
    rs2: int | None = None,
    immediate: int | None = None,
) -> RealizedPureRandomBlock:
    structural_nop = nop()

    return RealizedPureRandomBlock(
        family=family,
        mnemonic=mnemonic,
        start_pc=start_pc,
        words=(
            control_word,
            structural_nop,
            structural_nop,
            structural_nop,
        ),
        expected_executed_word_indices=(
            expected_indices
        ),
        structural_word_indices=(
            1,
            2,
            3,
        ),
        rd=rd,
        rs1=rs1,
        rs2=rs2,
        immediate=immediate,
    )


def realize_control(
    family: InstructionFamily,
    *,
    operand_rng: Random,
    model: WrapAwareRV32ArchitecturalModel,
    start_pc: int,
) -> RealizedPureRandomBlock:
    """
    Realize one frozen M1-PR control-flow block.

    Supported:
        BRANCH
        JAL
        JALR

    Structural layout:
        word 0 : stochastic control payload
        word 1 : NOP
        word 2 : NOP
        word 3 : redirect-target NOP
    """
    _validate_operand_rng(
        operand_rng
    )

    _validate_model(
        model
    )

    _validate_start_pc(
        model,
        start_pc,
    )

    target_pc = control_target_pc(
        start_pc
    )

    if family is InstructionFamily.BRANCH:
        # Frozen draw order:
        # subtype -> rs1 -> rs2
        variant_index = operand_rng.randrange(
            len(BRANCH_VARIANTS)
        )

        mnemonic, encoder = (
            BRANCH_VARIANTS[
                variant_index
            ]
        )

        rs1 = operand_rng.randrange(
            0,
            32,
        )

        rs2 = operand_rng.randrange(
            0,
            32,
        )

        word = encoder(
            rs1,
            rs2,
            CONTROL_OFFSET,
        )

        step = _speculative_step(
            model,
            pc=start_pc,
            instruction=word,
        )

        sequential_pc = (
            start_pc + 4
        ) & PHYSICAL_PC_MASK

        if step.next_pc == target_pc:
            expected_indices = (
                0,
                3,
            )

        elif step.next_pc == sequential_pc:
            expected_indices = (
                0,
                1,
                2,
                3,
            )

        else:
            raise AssertionError(
                "Golden branch produced unexpected "
                "next fetch PC: "
                f"{step.next_pc:#x}"
            )

        return _control_block(
            family=family,
            mnemonic=mnemonic,
            start_pc=start_pc,
            control_word=word,
            expected_indices=(
                expected_indices
            ),
            rs1=rs1,
            rs2=rs2,
            immediate=CONTROL_OFFSET,
        )

    if family is InstructionFamily.JAL:
        # Frozen draw order:
        # rd
        rd = operand_rng.randrange(
            1,
            32,
        )

        word = jal(
            rd,
            CONTROL_OFFSET,
        )

        step = _speculative_step(
            model,
            pc=start_pc,
            instruction=word,
        )

        if step.next_pc != target_pc:
            raise AssertionError(
                "Golden JAL target mismatch"
            )

        return _control_block(
            family=family,
            mnemonic="JAL",
            start_pc=start_pc,
            control_word=word,
            expected_indices=(
                0,
                3,
            ),
            rd=rd,
            immediate=CONTROL_OFFSET,
        )

    if family is InstructionFamily.JALR:
        # Frozen draw order:
        # rd -> rs1
        rd = operand_rng.randrange(
            1,
            32,
        )

        rs1 = operand_rng.randrange(
            0,
            32,
        )

        register_value = (
            model.read_register(
                rs1
            )
        )

        immediate = (
            jalr_immediate_for_target(
                register_value,
                target_pc,
            )
        )

        raw_target = (
            register_value
            + immediate
        ) & 0xFFFFFFFF

        if raw_target % 4 != 0:
            raise AssertionError(
                "JALR raw target must be "
                "word-aligned"
            )

        if (
            raw_target
            & PHYSICAL_PC_MASK
        ) != target_pc:
            raise AssertionError(
                "JALR raw target does not map "
                "to frozen physical target"
            )

        word = jalr(
            rd,
            rs1,
            immediate,
        )

        step = _speculative_step(
            model,
            pc=start_pc,
            instruction=word,
        )

        if step.next_pc != target_pc:
            raise AssertionError(
                "Golden JALR target mismatch"
            )

        return _control_block(
            family=family,
            mnemonic="JALR",
            start_pc=start_pc,
            control_word=word,
            expected_indices=(
                0,
                3,
            ),
            rd=rd,
            rs1=rs1,
            immediate=immediate,
        )

    raise ValueError(
        "family must be BRANCH, JAL, or JALR"
    )
