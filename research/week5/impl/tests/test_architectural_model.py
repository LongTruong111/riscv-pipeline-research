import pytest

from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
    UnsupportedArchitecturalInstruction,
)
from research.week5.impl.execution_event import ExecutionEvent
from research.week5.impl.rv32_encode import (
    add,
    addi,
    auipc,
    jal,
    jalr,
    lui,
    lw,
    sw,
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


def test_initial_state_is_zero():
    model = RV32ArchitecturalModel()

    assert model.read_register(0) == 0
    assert model.read_register(5) == 0
    assert model.read_word(0) == 0
    assert model.read_word(100) == 0


def test_addi_and_add():
    model = RV32ArchitecturalModel()

    s1 = model.step(
        event(
            1,
            0,
            addi(5, 0, 7),
        )
    )

    assert s1.pc_match
    assert s1.register_write.rd == 5
    assert s1.register_write.value == 7

    s2 = model.step(
        event(
            2,
            4,
            addi(6, 0, 3),
        )
    )

    assert s2.pc_match

    s3 = model.step(
        event(
            3,
            8,
            add(7, 5, 6),
        )
    )

    assert s3.pc_match
    assert model.read_register(7) == 10
    assert s3.register_write.value == 10


def test_architectural_x0_is_immutable():
    model = RV32ArchitecturalModel()

    step = model.step(
        event(
            1,
            0,
            addi(0, 0, 7),
        )
    )

    assert step.register_write is None
    assert model.read_register(0) == 0


def test_lui():
    model = RV32ArchitecturalModel()

    step = model.step(
        event(
            1,
            0,
            lui(5, 0x12345),
        )
    )

    assert step.register_write.value == 0x12345000
    assert model.read_register(5) == 0x12345000


def test_auipc_uses_instruction_pc():
    model = RV32ArchitecturalModel()

    step = model.step(
        event(
            1,
            0,
            auipc(5, 0x12345),
        )
    )

    assert step.register_write.value == 0x12345000


def test_zero_initialized_lw():
    model = RV32ArchitecturalModel()

    step = model.step(
        event(
            1,
            0,
            lw(5, 0, 0),
        )
    )

    assert step.register_write.value == 0
    assert model.read_register(5) == 0


def test_sw_then_lw_round_trip():
    model = RV32ArchitecturalModel()

    model.step(
        event(
            1,
            0,
            addi(1, 0, 100),
        )
    )

    model.step(
        event(
            2,
            4,
            addi(5, 0, 42),
        )
    )

    store_step = model.step(
        event(
            3,
            8,
            sw(5, 1, 0),
        )
    )

    assert store_step.store is not None
    assert store_step.store.address == 100
    assert store_step.store.data == 42

    assert model.read_word(100) == 42

    load_step = model.step(
        event(
            4,
            12,
            lw(6, 1, 0),
        )
    )

    assert load_step.register_write.value == 42
    assert model.read_register(6) == 42


def test_jal_link_and_target():
    model = RV32ArchitecturalModel()

    step = model.step(
        event(
            1,
            0,
            jal(5, 12),
        )
    )

    assert step.pc_match
    assert step.register_write.value == 4
    assert step.next_pc == 12

    target = model.step(
        event(
            2,
            12,
            addi(6, 5, 1),
        )
    )

    assert target.pc_match
    assert model.read_register(6) == 5


def test_jalr_clears_target_bit_zero():
    model = RV32ArchitecturalModel()

    model.step(
        event(
            1,
            0,
            addi(1, 0, 9),
        )
    )

    step = model.step(
        event(
            2,
            4,
            jalr(5, 1, 2),
        )
    )

    # (9 + 2) & ~1 = 10
    assert step.next_pc == 10

    # Link address = producer PC + 4
    assert step.register_write.value == 8


def test_pc_mismatch_is_reported_without_destroying_model():
    model = RV32ArchitecturalModel()

    first = model.step(
        event(
            1,
            0,
            addi(1, 0, 1),
        )
    )

    assert first.pc_match

    second = model.step(
        event(
            2,
            8,
            addi(2, 0, 2),
        )
    )

    assert not second.pc_match
    assert second.expected_pc == 4
    assert second.pc == 8


def test_execution_order_must_be_contiguous():
    model = RV32ArchitecturalModel()

    model.step(
        event(
            1,
            0,
            addi(1, 0, 1),
        )
    )

    with pytest.raises(ValueError):
        model.step(
            event(
                3,
                4,
                addi(2, 0, 2),
            )
        )


def test_unsupported_instruction_rejected():
    model = RV32ArchitecturalModel()

    # SUB x1,x2,x3
    sub = (
        (0b0100000 << 25)
        | (3 << 20)
        | (2 << 15)
        | (0b000 << 12)
        | (1 << 7)
        | 0b0110011
    )

    with pytest.raises(
        UnsupportedArchitecturalInstruction
    ):
        model.step(
            event(
                1,
                0,
                sub,
            )
        )
