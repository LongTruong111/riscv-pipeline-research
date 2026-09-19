import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from research.week5.impl.coverage_model import L2CoverageCollector
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)


N_CYCLES = int(os.getenv("N_CYCLES", "120"))


def signal_int(signal, name):
    """
    Convert a settled DUT signal to int with a useful failure message.
    """
    try:
        return int(signal.value)
    except ValueError as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z value: {signal.value}"
        ) from exc


async def reset_active_high(dut, cycles=3):
    """
    Frozen DUT reset convention.

    reset=1 asserted
    reset=0 released at FallingEdge
    """
    dut.clk.value = 0
    dut.reset.value = 1

    for _ in range(cycles):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


@cocotb.test()
async def test_live_execution_stream_reconstruction(dut):
    """
    Validate ExecutionEvent reconstruction against the frozen live RTL.

    This test does NOT attempt L1/L2 closure.

    It verifies the event-stream foundation on which later coverage and
    adaptive generation depend.
    """

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_active_high(dut)

    adapter = ExecutionEventAdapter()
    coverage = L2CoverageCollector()

    accepted_events = 0
    stall_cycles = 0
    flush_cycles = 0
    unsupported_cycles = 0

    for cycle in range(1, N_CYCLES + 1):

        # --------------------------------------------------------------
        # PRE-EDGE SNAPSHOT
        #
        # Frozen timing contract:
        # FallingEdge -> ReadOnly
        # --------------------------------------------------------------
        await FallingEdge(dut.clk)
        await ReadOnly()

        stall = bool(signal_int(dut.probe_stall, "probe_stall"))
        flush = bool(signal_int(dut.probe_flush, "probe_flush"))

        a_pc = signal_int(dut.probe_a_pc, "probe_a_pc")
        a_instr = signal_int(dut.probe_a_instr, "probe_a_instr")

        if stall:
            stall_cycles += 1

        if flush:
            flush_cycles += 1

        before_count = adapter.instruction_count

        pending = adapter.observe_pre_edge(
            PreEdgeSnapshot(
                cycle=cycle,
                reset=bool(signal_int(dut.reset, "reset")),
                stall=stall,
                flush_redirect=flush,
                pc=a_pc,
                instruction=a_instr,
            )
        )

        # Stall / flush must never directly create an executed instruction.
        if stall or flush:
            assert pending is None, (
                f"cycle={cycle}: stall/flush incorrectly admitted "
                f"instruction {a_instr:#010x}"
            )

        # --------------------------------------------------------------
        # POST-EDGE SETTLED OBSERVATION
        #
        # Frozen timing contract:
        # RisingEdge -> ReadOnly
        # --------------------------------------------------------------
        await RisingEdge(dut.clk)
        await ReadOnly()

        # RTL explicitly clears all functional B controls when injecting
        # reset/stall/flush bubbles.
        if stall or flush:
            b_control_nonzero = signal_int(
                dut.probe_b_control_nonzero,
                "probe_b_control_nonzero",
            )

            assert b_control_nonzero == 0, (
                f"cycle={cycle}: expected functional ID/EX bubble after "
                f"stall/flush, but B controls are non-zero"
            )

        if pending is None:
            assert adapter.instruction_count == before_count

            if not stall and not flush and a_instr != 0:
                unsupported_cycles += 1

            continue

        # A successfully admitted instruction must now be present in B.
        b_pc = signal_int(dut.probe_b_pc, "probe_b_pc")
        b_instr = signal_int(dut.probe_b_instr, "probe_b_instr")

        assert b_pc == pending.pc, (
            f"cycle={cycle}: ID/EX PC mismatch: "
            f"expected {pending.pc:#05x}, got {b_pc:#05x}"
        )

        assert b_instr == pending.instruction, (
            f"cycle={cycle}: ID/EX instruction mismatch: "
            f"expected {pending.instruction:#010x}, "
            f"got {b_instr:#010x}"
        )

        fwd_a = signal_int(dut.probe_fwd_a, "probe_fwd_a")
        fwd_b = signal_int(dut.probe_fwd_b, "probe_fwd_b")

        event = adapter.finalize_post_edge(
            pending,
            forward_a=fwd_a,
            forward_b=fwd_b,
        )

        accepted_events += 1

        # Instruction index is executed-program order, not cycle number.
        assert event.instruction_index == accepted_events

        assert event.pc == b_pc
        assert event.instruction == b_instr
        assert event.forward_a == fwd_a
        assert event.forward_b == fwd_b

        # This also verifies that the L2 collector accepts a contiguous
        # executed-program-order stream.
        coverage.observe(event)

    assert accepted_events > 0, (
        "Live DUT produced no accepted ExecutionEvent objects"
    )

    assert adapter.instruction_count == accepted_events

    assert 0 <= coverage.intent_bins <= 62

    dut._log.info(
        "EXECUTION_STREAM_SMOKE "
        f"cycles={N_CYCLES} "
        f"accepted={accepted_events} "
        f"stall_cycles={stall_cycles} "
        f"flush_cycles={flush_cycles} "
        f"unsupported_cycles={unsupported_cycles} "
        f"l2_intent_bins={coverage.intent_bins}"
    )

    if stall_cycles == 0:
        dut._log.warning(
            "No stall cycle occurred in the current instruction.hex; "
            "stall admission logic was not dynamically exercised."
        )

    if flush_cycles == 0:
        dut._log.warning(
            "No redirect/flush occurred in the current instruction.hex; "
            "flush admission logic was not dynamically exercised."
        )
