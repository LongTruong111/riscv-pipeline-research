import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from research.week5.impl.coverage_model import L2CoverageCollector
from research.week5.impl.l1_coverage import L1CoverageCollector
from research.week5.impl.realization_checker import (
    L1ControlRealizationChecker,
)
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)


N_CYCLES = int(os.getenv("N_CYCLES", "120"))

EXPECT_STALL = os.getenv("EXPECT_STALL", "0") == "1"
EXPECT_FLUSH = os.getenv("EXPECT_FLUSH", "0") == "1"
EXPECT_ACCEPTED = int(os.getenv("EXPECT_ACCEPTED", "0"))
EXPECT_L1_BIN = os.getenv("EXPECT_L1_BIN", "").strip()

def signal_int(signal, name):
    """
    Convert a settled DUT signal to int.

    Raise a useful assertion if the signal contains unresolved X/Z bits.
    """
    try:
        return int(signal.value)
    except ValueError as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z value: {signal.value}"
        ) from exc


async def reset_active_high(dut, cycles=3):
    """
    Frozen DUT reset convention:

        reset = 1 -> asserted
        reset = 0 -> released

    Reset is released at FallingEdge so it is stable before the next
    active RisingEdge.
    """
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

    This test validates the execution-stream foundation only. It does not
    attempt L1 or L2 closure.

    Checked properties include:

    - stalled IF/ID instructions do not immediately create ExecutionEvents;
    - flushed IF/ID instructions do not create ExecutionEvents;
    - accepted instructions increment executed-program-order index once;
    - accepted A-stage PC/instruction match the following B-stage state;
    - forwarding selectors are sampled after RisingEdge + ReadOnly;
    - the L2 collector accepts the reconstructed contiguous event stream.
    """

    dut.clk.value = 0

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_active_high(dut)

    adapter = ExecutionEventAdapter()
    coverage = L2CoverageCollector()
    l1_coverage = L1CoverageCollector()
    control_checker = L1ControlRealizationChecker()

    events_by_index = {}

    control_checks = 0
    control_passes = 0
    control_failures = 0
    control_failed_bins = set()
    accepted_events = 0
    accepted_after_stall = 0

    stall_cycles = 0
    flush_cycles = 0
    unsupported_cycles = 0

    for cycle in range(1, N_CYCLES + 1):
        # --------------------------------------------------------------
        # PRE-EDGE SNAPSHOT
        #
        # Frozen timing contract:
        #
        #   FallingEdge(clk)
        #   -> ReadOnly()
        #
        # Observe IF/ID state and control intent before the next active
        # pipeline edge.
        # --------------------------------------------------------------
        await FallingEdge(dut.clk)
        await ReadOnly()

        reset = bool(
            signal_int(
                dut.reset,
                "reset",
            )
        )

        stall = bool(
            signal_int(
                dut.probe_stall,
                "probe_stall",
            )
        )

        flush = bool(
            signal_int(
                dut.probe_flush,
                "probe_flush",
            )
        )

        a_pc = signal_int(
            dut.probe_a_pc,
            "probe_a_pc",
        )

        a_instr = signal_int(
            dut.probe_a_instr,
            "probe_a_instr",
        )

        if stall:
            stall_cycles += 1

        if flush:
            flush_cycles += 1

        before_count = adapter.instruction_count

        pending = adapter.observe_pre_edge(
            PreEdgeSnapshot(
                cycle=cycle,
                reset=reset,
                stall=stall,
                flush_redirect=flush,
                pc=a_pc,
                instruction=a_instr,
            )
        )

        # A stalled or flushed IF/ID instruction must not be admitted into
        # the executed instruction stream on this edge.
        if stall or flush:
            assert pending is None, (
                f"cycle={cycle}: stall/flush incorrectly admitted "
                f"instruction {a_instr:#010x}"
            )

        # --------------------------------------------------------------
        # POST-EDGE SETTLED OBSERVATION
        #
        # Frozen timing contract:
        #
        #   RisingEdge(clk)
        #   -> ReadOnly()
        #
        # At this point sequential pipeline state is settled.
        # --------------------------------------------------------------
        await RisingEdge(dut.clk)
        await ReadOnly()

        # Frozen Datapath injects a functional ID/EX bubble when reset,
        # Reg_Stall, or PcSel is active.
        #
        # B.Curr_Instr cannot be used as a valid bit because the RTL retains
        # this debug instruction field even when its functional controls are
        # cleared.
        if stall or flush:
            b_control_nonzero = signal_int(
                dut.probe_b_control_nonzero,
                "probe_b_control_nonzero",
            )

            assert b_control_nonzero == 0, (
                f"cycle={cycle}: expected functional ID/EX bubble after "
                f"stall/flush, but B controls are non-zero"
            )

        # No instruction was accepted on this cycle.
        if pending is None:
            assert adapter.instruction_count == before_count, (
                f"cycle={cycle}: instruction_count changed without "
                f"an accepted instruction"
            )

            if (
                not reset
                and not stall
                and not flush
                and a_instr != 0
            ):
                unsupported_cycles += 1

            continue

        # --------------------------------------------------------------
        # ACCEPTED INSTRUCTION VALIDATION
        #
        # The instruction observed in A before the edge must now be present
        # in B after the edge.
        # --------------------------------------------------------------
        b_pc = signal_int(
            dut.probe_b_pc,
            "probe_b_pc",
        )

        b_instr = signal_int(
            dut.probe_b_instr,
            "probe_b_instr",
        )

        assert b_pc == pending.pc, (
            f"cycle={cycle}: ID/EX PC mismatch: "
            f"expected {pending.pc:#05x}, "
            f"got {b_pc:#05x}"
        )

        assert b_instr == pending.instruction, (
            f"cycle={cycle}: ID/EX instruction mismatch: "
            f"expected {pending.instruction:#010x}, "
            f"got {b_instr:#010x}"
        )

        # Forwarding signals are meaningful for the instruction now
        # resident in ID/EX and are sampled only after settled ReadOnly.
        fwd_a = signal_int(
            dut.probe_fwd_a,
            "probe_fwd_a",
        )

        fwd_b = signal_int(
            dut.probe_fwd_b,
            "probe_fwd_b",
        )

        event = adapter.finalize_post_edge(
            pending,
            forward_a=fwd_a,
            forward_b=fwd_b,
        )

        if event.stall_cycles_before_accept > 0:
            accepted_after_stall += 1

        accepted_events += 1

        # Executed-program-order index must be contiguous and independent
        # of raw cycle count.
        assert event.instruction_index == accepted_events, (
            f"cycle={cycle}: expected instruction_index "
            f"{accepted_events}, got {event.instruction_index}"
        )

        assert event.pc == b_pc
        assert event.instruction == b_instr

        assert event.forward_a == fwd_a
        assert event.forward_b == fwd_b

        # Feeding every event into L2 also validates that the reconstructed
        # stream remains contiguous in executed-program order.
        # Preserve every executed event so realization checking can resolve
        # producer indices carried by L1Hit.
        events_by_index[event.instruction_index] = event

        coverage.observe(event)

        l1_hits = l1_coverage.observe(event)

        # --------------------------------------------------------------
        # CONTROL REALIZATION DIAGNOSTICS
        #
        # IMPORTANT:
        # This does not alter Intent Coverage and does not fail the test.
        # A control mismatch is diagnostic evidence for the later
        # Validated-Coverage layer.
        # --------------------------------------------------------------
        for l1_hit in l1_hits:
            result = control_checker.check(
                l1_hit,
                event,
                events_by_index,
            )

            control_checks += 1

            if result.passed:
                control_passes += 1
                continue

            control_failures += 1
            control_failed_bins.add(result.bin_id)

            failed_text = ",".join(
                (
                    f"{check.name}:"
                    f"expected={check.expected},"
                    f"observed={check.observed}"
                )
                for check in result.failed_checks
            )

            dut._log.warning(
                "CONTROL_REALIZATION_FAIL "
                f"bin={result.bin_id} "
                f"consumer_index="
                f"{result.consumer_instruction_index} "
                f"checks={failed_text}"
            )

    # ------------------------------------------------------------------
    # FINAL INVARIANTS
    # ------------------------------------------------------------------
    assert accepted_events > 0, (
        "Live DUT produced no accepted ExecutionEvent objects"
    )

    assert adapter.instruction_count == accepted_events
    if EXPECT_ACCEPTED > 0:
        assert accepted_events == EXPECT_ACCEPTED, (
            f"Expected {EXPECT_ACCEPTED} accepted instructions, "
            f"got {accepted_events}"
        )
    assert 0 <= coverage.intent_bins <= 62
    assert 0 <= l1_coverage.intent_bins <= 20

    if EXPECT_L1_BIN:
        assert EXPECT_L1_BIN in l1_coverage.intent_seen, (
            f"Unknown expected L1 bin: {EXPECT_L1_BIN}"
        )

        assert l1_coverage.intent_seen[EXPECT_L1_BIN], (
            f"Expected L1 bin {EXPECT_L1_BIN} was not hit"
        )

    assert control_checks == control_passes + control_failures

    dut._log.info(
        "EXECUTION_STREAM_SMOKE "
        f"cycles={N_CYCLES} "
        f"accepted={accepted_events} "
        f"accepted_after_stall={accepted_after_stall} "
        f"stall_cycles={stall_cycles} "
        f"flush_cycles={flush_cycles} "
        f"unsupported_cycles={unsupported_cycles} "
        f"l1_intent_bins={l1_coverage.intent_bins} "
        f"l1_seen="
        f"{','.join(bin_id for bin_id, seen in l1_coverage.intent_seen.items() if seen)} "
        f"l2_intent_bins={coverage.intent_bins} "
        f"control_checks={control_checks} "
        f"control_passes={control_passes} "
        f"control_failures={control_failures} "
        f"control_failed_bins="
        f"{','.join(sorted(control_failed_bins)) or 'none'}"
    )
    # ------------------------------------------------------------------
    # DIRECTED STALL REQUIREMENT
    # ------------------------------------------------------------------
    if EXPECT_STALL:
        assert stall_cycles > 0, (
            "Directed stall workload did not assert Reg_Stall"
        )

        assert accepted_after_stall > 0, (
            "A stalled IF/ID instruction was never subsequently accepted"
        )

    elif stall_cycles == 0:
        dut._log.warning(
            "No stall cycle occurred in the current instruction.hex; "
            "stall admission logic was not dynamically exercised."
        )

    # ------------------------------------------------------------------
    # DIRECTED FLUSH REQUIREMENT
    # ------------------------------------------------------------------
    if EXPECT_FLUSH:
        assert flush_cycles > 0, (
            "Directed flush workload did not assert PcSel"
        )

    elif flush_cycles == 0:
        dut._log.warning(
            "No redirect/flush occurred in the current instruction.hex; "
            "flush admission logic was not dynamically exercised."
        )
