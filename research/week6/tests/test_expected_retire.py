import pytest

from research.week5.impl.execution_event import ExecutionEvent
from research.week5.impl.rv32_encode import (
    addi,
    beq,
    sw,
)
from research.week6.expected_retire import (
    build_expected_retire_log,
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


def test_register_write_retire():
    log = build_expected_retire_log(
        [
            event(1, 0, addi(5, 0, 42)),
        ]
    )

    assert len(log) == 1

    retire = log[0]

    assert retire.instruction_id == 1
    assert retire.pc == 0
    assert retire.next_pc == 4

    assert retire.regwrite
    assert retire.rd == 5
    assert retire.wdata == 42

    assert retire.store_address is None
    assert retire.store_data is None


def test_x0_write_has_no_architectural_regwrite():
    log = build_expected_retire_log(
        [
            event(1, 0, addi(0, 0, 42)),
        ]
    )

    retire = log[0]

    assert not retire.regwrite
    assert retire.rd is None
    assert retire.wdata is None


def test_store_retire():
    log = build_expected_retire_log(
        [
            event(1, 0, addi(1, 0, 100)),
            event(2, 4, addi(2, 0, 55)),
            event(3, 8, sw(2, 1, 0)),
        ]
    )

    retire = log[2]

    assert not retire.regwrite
    assert retire.store_address == 100
    assert retire.store_data == 55
    assert retire.store_width_bytes == 4


def test_taken_branch_changes_expected_next_pc():
    log = build_expected_retire_log(
        [
            event(1, 0, addi(1, 0, 7)),
            event(2, 4, addi(2, 0, 7)),
            event(3, 8, beq(1, 2, 8)),
            event(4, 16, addi(3, 0, 1)),
        ]
    )

    branch = log[2]

    assert branch.pc == 8
    assert branch.next_pc == 16
    assert not branch.regwrite

    assert log[3].pc == 16


def test_retire_log_preserves_instruction_order():
    log = build_expected_retire_log(
        [
            event(1, 0, addi(1, 0, 1)),
            event(2, 4, addi(2, 0, 2)),
            event(3, 8, addi(3, 0, 3)),
        ]
    )

    assert [r.instruction_id for r in log] == [1, 2, 3]
    assert [r.pc for r in log] == [0, 4, 8]


def test_pc_inconsistent_trace_is_rejected():
    with pytest.raises(
        ValueError,
        match="architectural PC mismatch",
    ):
        build_expected_retire_log(
            [
                event(1, 0, addi(1, 0, 1)),
                event(2, 8, addi(2, 0, 2)),
            ]
        )

