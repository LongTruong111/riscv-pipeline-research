import pytest

from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week5.impl.execution_event import ExecutionEvent
from research.week5.impl.rv32_encode import (
    addi,
    beq,
    bne,
    blt,
    bge,
    bltu,
    bgeu,
)


def event(index, pc, instruction):
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


@pytest.mark.parametrize(
    ("encoder", "lhs", "rhs", "taken"),
    [
        (beq, 5, 5, True),
        (beq, 5, 6, False),
        (bne, 5, 6, True),
        (bne, 5, 5, False),

        (blt, -1, 1, True),
        (blt, 1, -1, False),
        (bge, 1, -1, True),
        (bge, -1, 1, False),

        (bltu, -1, 1, False),
        (bltu, 1, -1, True),
        (bgeu, -1, 1, True),
        (bgeu, 1, -1, False),
    ],
)
def test_branch_taken_and_not_taken(
    encoder,
    lhs,
    rhs,
    taken,
):
    model = RV32ArchitecturalModel()

    model.step(event(1, 0, addi(1, 0, lhs)))
    model.step(event(2, 4, addi(2, 0, rhs)))

    step = model.step(
        event(
            3,
            8,
            encoder(1, 2, 8),
        )
    )

    assert step.next_pc == (16 if taken else 12)
    assert step.register_write is None
    assert step.store is None
