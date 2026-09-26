from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import (
    FallingEdge,
    ReadOnly,
    RisingEdge,
    Timer,
)

from research.week5.impl.rv32_encode import (
    addi,
    bltu,
    lui,
    nop,
)
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week10.adaptive.wrap_aware_architectural_model import (
    WrapAwareRV32ArchitecturalModel,
)


CLOCK_NS = 10
INSTRUCTION_BYTES = 4


def signal_int(signal) -> int:
    return int(signal.value)


async def patch_word(
    dut,
    *,
    address: int,
    word: int,
) -> None:
    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = address
    dut.imem_patch_data.value = word

    await Timer(1, units="ns")

    dut.imem_patch_strobe.value = 1

    await Timer(1, units="ns")

    dut.imem_patch_strobe.value = 0

    await Timer(1, units="ns")


async def reset_active_high(
    dut,
    *,
    cycles: int = 3,
) -> None:
    dut.reset.value = 1

    for _ in range(cycles):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)

    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


async def run_program(
    dut,
    *,
    words: tuple[int, ...],
    accepted_count: int,
):
    """
    Execute one small directed image and return exactly the requested
    accepted ExecutionEvents.
    """

    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    await Timer(1, units="ns")

    for index, word in enumerate(words):
        await patch_word(
            dut,
            address=index * INSTRUCTION_BYTES,
            word=word,
        )

    adapter = ExecutionEventAdapter()

    clock = Clock(
        dut.clk,
        CLOCK_NS,
        units="ns",
    )

    clock_task = cocotb.start_soon(
        clock.start()
    )

    await reset_active_high(
        dut,
        cycles=3,
    )

    events = []

    for cycle in range(1, 256):
        await FallingEdge(dut.clk)
        await ReadOnly()

        snapshot = PreEdgeSnapshot(
            cycle=cycle,
            reset=bool(
                signal_int(dut.reset)
            ),
            stall=bool(
                signal_int(dut.probe_stall)
            ),
            flush_redirect=bool(
                signal_int(dut.probe_flush)
            ),
            pc=signal_int(
                dut.probe_a_pc
            ),
            instruction=signal_int(
                dut.probe_a_instr
            ),
        )

        pending = (
            adapter.observe_pre_edge(
                snapshot
            )
        )

        await RisingEdge(dut.clk)
        await ReadOnly()

        if pending is None:
            continue

        assert (
            signal_int(dut.probe_b_pc)
            == pending.pc
        )

        assert (
            signal_int(dut.probe_b_instr)
            == pending.instruction
        )

        event = (
            adapter.finalize_post_edge(
                pending,
                forward_a=signal_int(
                    dut.probe_fwd_a
                ),
                forward_b=signal_int(
                    dut.probe_fwd_b
                ),
            )
        )

        events.append(event)

        if len(events) == accepted_count:
            clock_task.kill()

            assert clock_task.done()

            assert signal_int(dut.clk) == 1

            await Timer(
                1,
                units="ns",
            )

            return tuple(events)

    clock_task.kill()

    raise AssertionError(
        "directed forwarding witness exceeded cycle budget"
    )


def golden_branch_next_pc(
    events,
    *,
    branch_event_count: int,
) -> tuple[int, WrapAwareRV32ArchitecturalModel]:
    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    step = None

    for event in events[
        :branch_event_count
    ]:
        step = model.step(event)

        assert step.pc_match

    assert step is not None

    return step.next_pc, model


@cocotb.test()
async def test_special_writeback_d1_forwarding_defect(
    dut,
):
    """
    Directed witness:

        settled x11 = 172
        LUI x17 = 0x00973000
        immediately-following BLTU consumes x17 at d1

    Architectural branch must be taken.

    Canonical RTL recognizes the dependency (Forward_B=10), but that
    select routes C.Alu_Result rather than the LUI writeback value.
    """

    words = (
        addi(11, 0, 172),
        nop(),
        nop(),

        lui(17, 0x973),

        bltu(11, 17, 12),

        nop(),
        nop(),

        addi(6, 0, 3),
    )

    events = await run_program(
        dut,
        words=words,
        accepted_count=6,
    )

    branch = events[4]
    successor = events[5]

    assert branch.pc == 16
    assert branch.forward_a == 0b00
    assert branch.forward_b == 0b10

    golden_next_pc, model = (
        golden_branch_next_pc(
            events,
            branch_event_count=5,
        )
    )

    assert (
        model.read_register(11)
        == 172
    )

    assert (
        model.read_register(17)
        == 0x00973000
    )

    # Architectural BLTU:
    # 172 < 0x00973000 => taken.
    assert golden_next_pc == 28

    # Canonical DUT defect:
    # d1 EX/MEM forwarding supplies LUI C.Alu_Result (=1), so
    # 172 < 1 => false and execution falls through.
    assert successor.pc == 20

    assert successor.pc != golden_next_pc

    dut._log.info(
        "SPECIAL_WB_D1_DEFECT_CAUGHT=PASS "
        "producer=LUI "
        "consumer=BLTU "
        "forward_b=10 "
        f"golden_next=0x{golden_next_pc:03x} "
        f"rtl_next=0x{successor.pc:03x}"
    )


@cocotb.test()
async def test_special_writeback_d2_control_passes(
    dut,
):
    """
    Control experiment: insert one NOP between LUI and BLTU.

    Producer reaches MEM/WB, so Forward_B=01 selects WRMuxResult,
    which already contains the correct special writeback value.
    """

    words = (
        addi(11, 0, 172),
        nop(),
        nop(),

        lui(17, 0x973),
        nop(),

        bltu(11, 17, 12),

        nop(),
        nop(),

        addi(6, 0, 3),
    )

    events = await run_program(
        dut,
        words=words,
        accepted_count=7,
    )

    branch = events[5]
    successor = events[6]

    assert branch.pc == 20
    assert branch.forward_b == 0b01

    golden_next_pc, model = (
        golden_branch_next_pc(
            events,
            branch_event_count=6,
        )
    )

    assert (
        model.read_register(17)
        == 0x00973000
    )

    assert golden_next_pc == 32
    assert successor.pc == 32

    dut._log.info(
        "SPECIAL_WB_D2_CONTROL=PASS "
        "producer=LUI "
        "consumer=BLTU "
        "forward_b=01"
    )


@cocotb.test()
async def test_normal_alu_d1_control_passes(
    dut,
):
    """
    Control experiment: ordinary ADDI producer at d1.

    Forward_B=10 is correct here because C.Alu_Result is exactly the
    architectural ADDI writeback value.
    """

    words = (
        addi(11, 0, 172),
        nop(),
        nop(),

        addi(17, 0, 1000),

        bltu(11, 17, 12),

        nop(),
        nop(),

        addi(6, 0, 3),
    )

    events = await run_program(
        dut,
        words=words,
        accepted_count=6,
    )

    branch = events[4]
    successor = events[5]

    assert branch.pc == 16
    assert branch.forward_b == 0b10

    golden_next_pc, model = (
        golden_branch_next_pc(
            events,
            branch_event_count=5,
        )
    )

    assert model.read_register(17) == 1000

    assert golden_next_pc == 28
    assert successor.pc == 28

    dut._log.info(
        "NORMAL_ALU_D1_CONTROL=PASS "
        "producer=ADDI "
        "consumer=BLTU "
        "forward_b=10"
    )
