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
    beq,
    jal,
    jalr,
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
MAX_CYCLES = 256

PC_WRAP = 0x1FC
FULL_WIDTH_LINK = 0x200


def signal_int(signal) -> int:
    return int(signal.value)


async def patch_word(
    dut,
    *,
    address: int,
    word: int,
) -> None:
    if address % 4 != 0:
        raise ValueError(
            "IMEM patch address must be 4-byte aligned"
        )

    if not 0 <= address <= 508:
        raise ValueError(
            "IMEM patch address must be in [0, 508]"
        )

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


async def run_sparse_image(
    dut,
    *,
    image: dict[int, int],
    required_accepted: int,
    watched_registers: tuple[int, ...],
):
    """
    Execute one sparse directed image.

    Returns:
        first `required_accepted` accepted ExecutionEvents
        observed architectural writeback values for watched registers

    This witness deliberately permits later NOP execution while waiting
    for the target writebacks to retire. It is not the Week-13 exact-N
    campaign-cut driver.
    """
    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    await Timer(1, units="ns")

    for address in sorted(image):
        await patch_word(
            dut,
            address=address,
            word=image[address],
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
    writes: dict[int, int] = {}

    for cycle in range(1, MAX_CYCLES + 1):
        await FallingEdge(dut.clk)
        await ReadOnly()

        # These are the settled MEM/WB values that will be consumed by
        # the following active edge. Ignore unrelated writes.
        if bool(signal_int(dut.reg_write_sig)):
            rd = signal_int(dut.reg_num)

            if rd in watched_registers:
                writes.setdefault(
                    rd,
                    signal_int(dut.reg_data),
                )

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

        pending = adapter.observe_pre_edge(
            snapshot
        )

        await RisingEdge(dut.clk)
        await ReadOnly()

        if pending is not None:
            assert (
                signal_int(dut.probe_b_pc)
                == pending.pc
            )

            assert (
                signal_int(dut.probe_b_instr)
                == pending.instruction
            )

            event = adapter.finalize_post_edge(
                pending,
                forward_a=signal_int(
                    dut.probe_fwd_a
                ),
                forward_b=signal_int(
                    dut.probe_fwd_b
                ),
            )

            events.append(event)

        if (
            len(events) >= required_accepted
            and all(
                rd in writes
                for rd in watched_registers
            )
        ):
            clock_task.kill()

            assert clock_task.done()
            assert signal_int(dut.clk) == 1

            await Timer(
                1,
                units="ns",
            )

            return (
                tuple(
                    events[:required_accepted]
                ),
                writes,
            )

    clock_task.kill()

    raise AssertionError(
        "PC/link/wrap witness exceeded cycle budget: "
        f"accepted={len(events)}, "
        f"writes={writes}"
    )


def replay_golden(events):
    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    steps = []

    for event in events:
        step = model.step(event)

        assert step.pc_match

        steps.append(step)

    return model, tuple(steps)


@cocotb.test()
async def test_jal_at_1fc_preserves_full_link_and_wraps_fetch(
    dut,
):
    """
    Directed Revision-B witness:

        PC 0x000:
            beq x0, x0, +508
                -> physical 0x1fc

        PC 0x1fc:
            jal x5, +8

            architectural link = 0x200
            architectural target = 0x204
            physical target = 0x004

        PC 0x004:
            addi x6, x5, 1

    The ADDI is the immediately next accepted instruction after JAL.
    Redirect bubbles do not change accepted-program-order distance.
    """
    image = {
        0x000: beq(0, 0, 508),

        0x004: addi(6, 5, 1),
        0x008: nop(),
        0x00C: nop(),
        0x010: nop(),

        0x1FC: jal(5, 8),
    }

    events, writes = await run_sparse_image(
        dut,
        image=image,
        required_accepted=3,
        watched_registers=(5, 6),
    )

    assert tuple(
        event.pc
        for event in events
    ) == (
        0x000,
        0x1FC,
        0x004,
    )

    boundary_jump = events[1]
    consumer = events[2]

    assert (
        consumer.instruction_index
        == boundary_jump.instruction_index + 1
    )

    assert writes[5] == FULL_WIDTH_LINK
    assert writes[6] == FULL_WIDTH_LINK + 1

    model, steps = replay_golden(
        events
    )

    assert steps[1].next_pc == 0x004
    assert model.read_register(5) == 0x200
    assert model.read_register(6) == 0x201

    dut._log.info(
        "PC_LINK_WRAP_JAL=PASS "
        "pc=0x1fc "
        "link=0x200 "
        "physical_target=0x004 "
        "consumer_result=0x201"
    )


@cocotb.test()
async def test_jalr_at_1fc_preserves_full_link_and_aligned_wrap(
    dut,
):
    """
    JALR counterpart.

    The raw JALR target is deliberately word-aligned, so the known
    canonical missing-LSB-clear defect is not activated.

        x7 = 16

        PC 0x004:
            beq x0, x0, +504
                -> physical 0x1fc

        PC 0x1fc:
            jalr x5, x7, 0
                -> raw target 0x010
                -> link 0x200

        PC 0x010:
            addi x6, x5, 1
    """
    image = {
        0x000: addi(7, 0, 16),
        0x004: beq(0, 0, 504),

        0x008: nop(),
        0x00C: nop(),

        0x010: addi(6, 5, 1),
        0x014: nop(),
        0x018: nop(),
        0x01C: nop(),

        0x1FC: jalr(5, 7, 0),
    }

    events, writes = await run_sparse_image(
        dut,
        image=image,
        required_accepted=4,
        watched_registers=(5, 6, 7),
    )

    assert tuple(
        event.pc
        for event in events
    ) == (
        0x000,
        0x004,
        0x1FC,
        0x010,
    )

    boundary_jump = events[2]
    consumer = events[3]

    assert (
        consumer.instruction_index
        == boundary_jump.instruction_index + 1
    )

    assert writes[7] == 16
    assert writes[5] == FULL_WIDTH_LINK
    assert writes[6] == FULL_WIDTH_LINK + 1

    model, steps = replay_golden(
        events
    )

    assert steps[2].next_pc == 0x010

    assert model.read_register(7) == 16
    assert model.read_register(5) == 0x200
    assert model.read_register(6) == 0x201

    dut._log.info(
        "PC_LINK_WRAP_JALR=PASS "
        "pc=0x1fc "
        "raw_target=0x010 "
        "link=0x200 "
        "consumer_result=0x201"
    )


@cocotb.test()
async def test_branch_at_1fc_wraps_without_link_semantics(
    dut,
):
    """
    Control witness without link-register semantics:

        PC 0x000:
            beq x0, x0, +508
                -> 0x1fc

        PC 0x1fc:
            beq x0, x0, +8

            architectural target = 0x204
            physical target = 0x004

        PC 0x004:
            addi x6, x0, 7

    This isolates physical redirect masking from JAL/JALR link behavior.
    """
    image = {
        0x000: beq(0, 0, 508),

        0x004: addi(6, 0, 7),
        0x008: nop(),
        0x00C: nop(),
        0x010: nop(),

        0x1FC: beq(0, 0, 8),
    }

    events, writes = await run_sparse_image(
        dut,
        image=image,
        required_accepted=3,
        watched_registers=(6,),
    )

    assert tuple(
        event.pc
        for event in events
    ) == (
        0x000,
        0x1FC,
        0x004,
    )

    boundary_branch = events[1]
    successor = events[2]

    assert (
        successor.instruction_index
        == boundary_branch.instruction_index + 1
    )

    assert writes[6] == 7

    model, steps = replay_golden(
        events
    )

    assert steps[1].next_pc == 0x004
    assert model.read_register(5) == 0
    assert model.read_register(6) == 7

    dut._log.info(
        "PC_LINK_WRAP_BRANCH=PASS "
        "pc=0x1fc "
        "physical_target=0x004 "
        "link_register_unchanged=1"
    )
