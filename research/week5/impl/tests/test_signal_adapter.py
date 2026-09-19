import pytest

from research.week5.impl.isa_decode import OP_IMM
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)


def make_addi(*, rd, rs1, imm_low5=0):
    """
    Minimal structurally valid OP-IMM encoding.

    Only fields required by the structural decoder matter here.
    """
    return (
        OP_IMM
        | (rd << 7)
        | (rs1 << 15)
        | ((imm_low5 & 0x1F) << 20)
    )


def snap(
    cycle,
    instruction,
    *,
    pc=0,
    reset=False,
    stall=False,
    flush=False,
):
    return PreEdgeSnapshot(
        cycle=cycle,
        reset=reset,
        stall=stall,
        flush_redirect=flush,
        pc=pc,
        instruction=instruction,
    )


def test_normal_instruction_is_admitted():
    adapter = ExecutionEventAdapter()
    instr = make_addi(rd=5, rs1=1)

    pending = adapter.observe_pre_edge(
        snap(
            10,
            instr,
            pc=0x20,
        )
    )

    assert pending is not None

    event = adapter.finalize_post_edge(
        pending,
        forward_a=0b10,
        forward_b=0b00,
    )

    assert event.instruction_index == 1
    assert event.pc == 0x20
    assert event.rd == 5
    assert event.rs1 == 1
    assert event.stall_cycles_before_accept == 0
    assert event.forward_a == 0b10


def test_stall_does_not_create_execution_event():
    adapter = ExecutionEventAdapter()
    instr = make_addi(rd=6, rs1=5)

    pending = adapter.observe_pre_edge(
        snap(
            10,
            instr,
            pc=0x24,
            stall=True,
        )
    )

    assert pending is None
    assert adapter.instruction_count == 0


def test_stalled_instruction_is_counted_only_when_accepted():
    adapter = ExecutionEventAdapter()
    instr = make_addi(rd=6, rs1=5)

    assert adapter.observe_pre_edge(
        snap(
            10,
            instr,
            pc=0x24,
            stall=True,
        )
    ) is None

    pending = adapter.observe_pre_edge(
        snap(
            11,
            instr,
            pc=0x24,
            stall=False,
        )
    )

    assert pending is not None

    event = adapter.finalize_post_edge(
        pending,
        forward_a=0b01,
        forward_b=0b00,
    )

    assert event.instruction_index == 1
    assert event.stall_cycles_before_accept == 1


def test_multiple_stall_cycles_are_preserved():
    adapter = ExecutionEventAdapter()
    instr = make_addi(rd=6, rs1=5)

    assert adapter.observe_pre_edge(
        snap(
            10,
            instr,
            pc=0x24,
            stall=True,
        )
    ) is None

    assert adapter.observe_pre_edge(
        snap(
            11,
            instr,
            pc=0x24,
            stall=True,
        )
    ) is None

    pending = adapter.observe_pre_edge(
        snap(
            12,
            instr,
            pc=0x24,
        )
    )

    assert pending is not None

    event = adapter.finalize_post_edge(
        pending,
        forward_a=0,
        forward_b=0,
    )

    assert event.stall_cycles_before_accept == 2


def test_flush_discards_if_id_instruction():
    adapter = ExecutionEventAdapter()
    instr = make_addi(rd=5, rs1=1)

    pending = adapter.observe_pre_edge(
        snap(
            10,
            instr,
            pc=0x20,
            flush=True,
        )
    )

    assert pending is None
    assert adapter.instruction_count == 0


def test_reset_discards_if_id_instruction():
    adapter = ExecutionEventAdapter()
    instr = make_addi(rd=5, rs1=1)

    pending = adapter.observe_pre_edge(
        snap(
            10,
            instr,
            pc=0x20,
            reset=True,
        )
    )

    assert pending is None
    assert adapter.instruction_count == 0


def test_unknown_opcode_is_not_admitted():
    adapter = ExecutionEventAdapter()

    pending = adapter.observe_pre_edge(
        snap(
            10,
            0x00000000,
            pc=0x20,
        )
    )

    assert pending is None
    assert adapter.instruction_count == 0


def test_flush_clears_previous_stall_history():
    adapter = ExecutionEventAdapter()
    instr = make_addi(rd=5, rs1=1)

    adapter.observe_pre_edge(
        snap(
            10,
            instr,
            pc=0x20,
            stall=True,
        )
    )

    adapter.observe_pre_edge(
        snap(
            11,
            instr,
            pc=0x20,
            flush=True,
        )
    )

    pending = adapter.observe_pre_edge(
        snap(
            12,
            instr,
            pc=0x20,
        )
    )

    assert pending is not None

    event = adapter.finalize_post_edge(
        pending,
        forward_a=0,
        forward_b=0,
    )

    assert event.stall_cycles_before_accept == 0


def test_different_instruction_does_not_inherit_stall_count():
    adapter = ExecutionEventAdapter()

    stalled = make_addi(rd=5, rs1=1)
    different = make_addi(rd=6, rs1=2)

    adapter.observe_pre_edge(
        snap(
            10,
            stalled,
            pc=0x20,
            stall=True,
        )
    )

    pending = adapter.observe_pre_edge(
        snap(
            11,
            different,
            pc=0x24,
        )
    )

    assert pending is not None

    event = adapter.finalize_post_edge(
        pending,
        forward_a=0,
        forward_b=0,
    )

    assert event.stall_cycles_before_accept == 0


def test_adapter_reset_restarts_instruction_index():
    adapter = ExecutionEventAdapter()

    instr = make_addi(rd=5, rs1=1)

    pending = adapter.observe_pre_edge(
        snap(1, instr)
    )
    event = adapter.finalize_post_edge(
        pending,
        forward_a=0,
        forward_b=0,
    )

    assert event.instruction_index == 1

    adapter.reset()

    pending = adapter.observe_pre_edge(
        snap(2, instr)
    )
    event = adapter.finalize_post_edge(
        pending,
        forward_a=0,
        forward_b=0,
    )

    assert event.instruction_index == 1


def test_invalid_forward_select_is_rejected():
    adapter = ExecutionEventAdapter()

    instr = make_addi(rd=5, rs1=1)

    pending = adapter.observe_pre_edge(
        snap(1, instr)
    )

    with pytest.raises(ValueError):
        adapter.finalize_post_edge(
            pending,
            forward_a=4,
            forward_b=0,
        )
