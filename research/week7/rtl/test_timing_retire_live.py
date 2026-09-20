import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from research.week5.impl.directed_cases import DIRECTED_CASES
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week7.retire_monitor import (
    RetireMonitor,
    RetireTag,
)
from research.week7.timing_oracle_v1 import (
    build_timing_schedule_v1,
)


N_CYCLES = int(os.getenv("N_CYCLES", "60"))
TIMING_CASE = os.getenv("TIMING_CASE", "").strip()


def signal_int(signal, name):
    try:
        return int(signal.value)
    except ValueError as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z value: {signal.value}"
        ) from exc


async def reset_active_high(dut, cycles=3):
    dut.reset.value = 1

    for _ in range(cycles):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


def build_program(words):
    return {
        index * 4: instruction
        for index, instruction in enumerate(words)
    }


@cocotb.test()
async def test_timing_retire_correlation(dut):
    """
    Compare independently generated Timing Oracle v1 expectations
    against the live DUT execution/retire stream.

    Oracle inputs:
        canonical instruction program only.

    Oracle MUST NOT consume:
        observed stall,
        observed forwarding,
        observed flush,
        observed retire cycle.
    """

    assert TIMING_CASE in DIRECTED_CASES, (
        f"unknown TIMING_CASE={TIMING_CASE!r}"
    )

    case = DIRECTED_CASES[TIMING_CASE]

    schedule = build_timing_schedule_v1(
        build_program(case.words)
    )

    expected_by_id = {
        item.instruction_id: item
        for item in schedule.expectations
    }

    assert schedule.instruction_count == case.expected_accepted, (
        f"{TIMING_CASE}: oracle executed count "
        f"{schedule.instruction_count} != canonical expected "
        f"{case.expected_accepted}"
    )

    dut.clk.value = 0

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_active_high(dut)

    adapter = ExecutionEventAdapter()
    monitor = RetireMonitor()

    observed_accept_ids = []
    observed_retire_ids = []

    stall_cycles = 0
    flush_cycles = 0
    unsupported_cycles = 0

    for cycle in range(1, N_CYCLES + 1):
        # ----------------------------------------------------------
        # FALLING EDGE
        #
        # Current D-stage instruction performs architectural
        # register-file commit on the frozen DUT.
        # ----------------------------------------------------------
        await FallingEdge(dut.clk)
        await ReadOnly()

        current_d_tag = monitor.d_tag

        if current_d_tag is not None:
            d_instr = signal_int(
                dut.probe_d_instr,
                "probe_d_instr",
            )

            assert d_instr == current_d_tag.instruction, (
                f"{TIMING_CASE}: cycle={cycle}: "
                f"D identity mismatch for "
                f"instruction_id="
                f"{current_d_tag.instruction_id}: "
                f"expected "
                f"{current_d_tag.instruction:#010x}, "
                f"observed {d_instr:#010x}"
            )

        retired = monitor.observe_falling_edge(
            cycle=cycle,
            regwrite=bool(
                signal_int(
                    dut.reg_write_sig,
                    "reg_write_sig",
                )
            ),
            rd=signal_int(
                dut.reg_num,
                "reg_num",
            ),
            wdata=signal_int(
                dut.reg_data,
                "reg_data",
            ),
        )

        if retired is not None:
            expected = expected_by_id[
                retired.instruction_id
            ]

            assert retired.cycle == expected.retire_cycle, (
                f"{TIMING_CASE}: "
                f"instruction_id={retired.instruction_id}: "
                f"retire cycle mismatch: "
                f"expected={expected.retire_cycle}, "
                f"observed={retired.cycle}"
            )

            observed_retire_ids.append(
                retired.instruction_id
            )

        # ----------------------------------------------------------
        # PRE-RISING-EDGE admission/control observation.
        # ----------------------------------------------------------
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

        if stall:
            stall_cycles += 1

        if flush:
            flush_cycles += 1

        a_pc = signal_int(
            dut.probe_a_pc,
            "probe_a_pc",
        )

        a_instr = signal_int(
            dut.probe_a_instr,
            "probe_a_instr",
        )

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

        if (
            pending is None
            and not reset
            and not stall
            and not flush
            and a_instr != 0
        ):
            unsupported_cycles += 1

        # ----------------------------------------------------------
        # RISING EDGE
        # ----------------------------------------------------------
        await RisingEdge(dut.clk)
        await ReadOnly()

        if reset:
            monitor.reset()
            continue

        accepted_tag = None

        if pending is not None:
            b_pc = signal_int(
                dut.probe_b_pc,
                "probe_b_pc",
            )

            b_instr = signal_int(
                dut.probe_b_instr,
                "probe_b_instr",
            )

            assert b_pc == pending.pc
            assert b_instr == pending.instruction

            event = adapter.finalize_post_edge(
                pending,
                forward_a=signal_int(
                    dut.probe_fwd_a,
                    "probe_fwd_a",
                ),
                forward_b=signal_int(
                    dut.probe_fwd_b,
                    "probe_fwd_b",
                ),
            )

            expected = expected_by_id[
                event.instruction_index
            ]

            # ------------------------------------------------------
            # Timing Oracle v1 -> live DUT correlation
            # ------------------------------------------------------
            assert event.pc == expected.pc, (
                f"{TIMING_CASE}: "
                f"instruction_id={event.instruction_index}: "
                f"PC mismatch: "
                f"expected={expected.pc:#x}, "
                f"observed={event.pc:#x}"
            )

            assert event.instruction == expected.instruction

            assert event.cycle == expected.accept_cycle, (
                f"{TIMING_CASE}: "
                f"instruction_id={event.instruction_index}: "
                f"accept cycle mismatch: "
                f"expected={expected.accept_cycle}, "
                f"observed={event.cycle}"
            )

            assert (
                event.stall_cycles_before_accept
                == expected.stall_cycles_before_accept
            ), (
                f"{TIMING_CASE}: "
                f"instruction_id={event.instruction_index}: "
                f"stall mismatch: "
                f"expected="
                f"{expected.stall_cycles_before_accept}, "
                f"observed="
                f"{event.stall_cycles_before_accept}"
            )

            assert event.forward_a == expected.forward_a, (
                f"{TIMING_CASE}: "
                f"instruction_id={event.instruction_index}: "
                f"forward_a mismatch: "
                f"expected={expected.forward_a:02b}, "
                f"observed={event.forward_a:02b}"
            )

            assert event.forward_b == expected.forward_b, (
                f"{TIMING_CASE}: "
                f"instruction_id={event.instruction_index}: "
                f"forward_b mismatch: "
                f"expected={expected.forward_b:02b}, "
                f"observed={event.forward_b:02b}"
            )

            observed_accept_ids.append(
                event.instruction_index
            )

            accepted_tag = RetireTag.from_execution_event(
                event
            )

        monitor.advance_pipeline(accepted_tag)

    # --------------------------------------------------------------
    # FINAL CORRELATION INVARIANTS
    # --------------------------------------------------------------
    expected_ids = list(
        range(1, schedule.instruction_count + 1)
    )

    assert unsupported_cycles == 0, (
        f"{TIMING_CASE}: unsupported cycles="
        f"{unsupported_cycles}"
    )

    assert observed_accept_ids == expected_ids, (
        f"{TIMING_CASE}: accepted IDs mismatch: "
        f"expected={expected_ids}, "
        f"observed={observed_accept_ids}"
    )

    assert observed_retire_ids == expected_ids, (
        f"{TIMING_CASE}: retired IDs mismatch: "
        f"expected={expected_ids}, "
        f"observed={observed_retire_ids}"
    )

    assert monitor.retired_count == schedule.instruction_count

    assert monitor.stage_instruction_ids == (
        None,
        None,
        None,
    )

    observed_stalls_from_events = sum(
        expected_by_id[instruction_id]
        .stall_cycles_before_accept
        for instruction_id in observed_accept_ids
    )

    assert observed_stalls_from_events == schedule.total_stall_cycles

    # DUT PcSel is a one-cycle redirect indication, whereas the
    # oracle models two acceptance bubbles caused by that redirect.
    expected_has_redirect = any(
        item.redirect
        for item in schedule.expectations
    )

    if expected_has_redirect:
        assert flush_cycles > 0, (
            f"{TIMING_CASE}: expected redirect but DUT "
            "never asserted flush/PcSel"
        )
    else:
        assert flush_cycles == 0, (
            f"{TIMING_CASE}: unexpected flush cycles="
            f"{flush_cycles}"
        )

    dut._log.info(
        "TIMING_RETIRE_CORRELATION "
        f"case={TIMING_CASE} "
        f"accepted={len(observed_accept_ids)} "
        f"retired={len(observed_retire_ids)} "
        f"oracle_stalls={schedule.total_stall_cycles} "
        f"dut_stall_cycles={stall_cycles} "
        f"oracle_redirect_bubbles="
        f"{schedule.total_redirect_bubbles} "
        f"dut_flush_cycles={flush_cycles} "
        f"drain_cycle={schedule.drain_cycle}"
    )
