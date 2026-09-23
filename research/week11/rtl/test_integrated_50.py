import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

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
from research.week11.integrated_sequence import (
    WEEK11_INTEGRATED_INSTRUCTION_COUNT,
    build_week11_integrated_sequence,
)


N_CYCLES = int(os.getenv("N_CYCLES", "90"))


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
async def test_integrated_50_timing_correlation(dut):
    words = build_week11_integrated_sequence()

    assert len(words) == WEEK11_INTEGRATED_INSTRUCTION_COUNT
    assert WEEK11_INTEGRATED_INSTRUCTION_COUNT == 50

    schedule = build_timing_schedule_v1(
        build_program(words),
        max_instructions=50,
    )

    assert schedule.instruction_count == 50

    expected_by_id = {
        item.instruction_id: item
        for item in schedule.expectations
    }

    dut.clk.value = 0

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_active_high(dut)

    adapter = ExecutionEventAdapter()
    retire_monitor = RetireMonitor()

    observed_accept_ids = []
    observed_retire_ids = []

    observed_stall_cycles = 0
    observed_flush_cycles = 0

    for cycle in range(1, N_CYCLES + 1):
        # ----------------------------------------------------------
        # FALLING EDGE
        # ----------------------------------------------------------
        await FallingEdge(dut.clk)
        await ReadOnly()

        d_tag = retire_monitor.d_tag

        if d_tag is not None:
            d_instr = signal_int(
                dut.probe_d_instr,
                "probe_d_instr",
            )

            assert d_instr == d_tag.instruction, (
                f"cycle={cycle}: D-stage identity mismatch for "
                f"instruction_id={d_tag.instruction_id}: "
                f"expected={d_tag.instruction:#010x}, "
                f"observed={d_instr:#010x}"
            )

        retired = retire_monitor.observe_falling_edge(
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
                f"instruction_id={retired.instruction_id}: "
                f"retire cycle mismatch: "
                f"expected={expected.retire_cycle}, "
                f"observed={retired.cycle}"
            )

            observed_retire_ids.append(
                retired.instruction_id
            )

        # ----------------------------------------------------------
        # PRE-RISING-EDGE
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
            observed_stall_cycles += 1

        if flush:
            observed_flush_cycles += 1

        pending = adapter.observe_pre_edge(
            PreEdgeSnapshot(
                cycle=cycle,
                reset=reset,
                stall=stall,
                flush_redirect=flush,
                pc=signal_int(
                    dut.probe_a_pc,
                    "probe_a_pc",
                ),
                instruction=signal_int(
                    dut.probe_a_instr,
                    "probe_a_instr",
                ),
            )
        )

        # ----------------------------------------------------------
        # RISING EDGE
        # ----------------------------------------------------------
        await RisingEdge(dut.clk)
        await ReadOnly()

        if reset:
            retire_monitor.reset()
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

            instruction_id = event.instruction_index

            assert instruction_id in expected_by_id, (
                f"unexpected accepted instruction_id="
                f"{instruction_id}"
            )

            expected = expected_by_id[instruction_id]

            assert event.pc == expected.pc, (
                f"instruction_id={instruction_id}: "
                f"PC mismatch: expected={expected.pc:#x}, "
                f"observed={event.pc:#x}"
            )

            assert event.instruction == expected.instruction, (
                f"instruction_id={instruction_id}: "
                "instruction mismatch"
            )

            assert event.cycle == expected.accept_cycle, (
                f"instruction_id={instruction_id}: "
                f"accept cycle mismatch: "
                f"expected={expected.accept_cycle}, "
                f"observed={event.cycle}"
            )

            assert (
                event.stall_cycles_before_accept
                == expected.stall_cycles_before_accept
            ), (
                f"instruction_id={instruction_id}: "
                f"stall mismatch: "
                f"expected="
                f"{expected.stall_cycles_before_accept}, "
                f"observed="
                f"{event.stall_cycles_before_accept}"
            )

            assert event.forward_a == expected.forward_a, (
                f"instruction_id={instruction_id}: "
                f"forward_a mismatch: "
                f"expected={expected.forward_a:02b}, "
                f"observed={event.forward_a:02b}"
            )

            assert event.forward_b == expected.forward_b, (
                f"instruction_id={instruction_id}: "
                f"forward_b mismatch: "
                f"expected={expected.forward_b:02b}, "
                f"observed={event.forward_b:02b}"
            )

            observed_accept_ids.append(instruction_id)

            accepted_tag = RetireTag.from_execution_event(
                event
            )

        retire_monitor.advance_pipeline(accepted_tag)

    expected_ids = list(range(1, 51))

    assert observed_accept_ids == expected_ids, (
        "accepted instruction stream mismatch: "
        f"expected={expected_ids}, "
        f"observed={observed_accept_ids}"
    )

    assert observed_retire_ids == expected_ids, (
        "retired instruction stream mismatch: "
        f"expected={expected_ids}, "
        f"observed={observed_retire_ids}"
    )

    assert retire_monitor.retired_count == 50

    assert retire_monitor.stage_instruction_ids == (
        None,
        None,
        None,
    )

    assert (
        observed_stall_cycles
        == schedule.total_stall_cycles
    ), (
        "aggregate stall mismatch: "
        f"expected={schedule.total_stall_cycles}, "
        f"observed={observed_stall_cycles}"
    )

    # This Gate-T11 sequence is deliberately straight-line.
    assert observed_flush_cycles == 0

    dut._log.info(
        "WEEK11_INTEGRATED_50 "
        f"accepted={len(observed_accept_ids)} "
        f"retired={len(observed_retire_ids)} "
        f"expected_stalls={schedule.total_stall_cycles} "
        f"observed_stalls={observed_stall_cycles} "
        f"flush_cycles={observed_flush_cycles}"
    )
