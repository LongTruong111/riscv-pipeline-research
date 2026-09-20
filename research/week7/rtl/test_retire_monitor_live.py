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


N_CYCLES = int(os.getenv("N_CYCLES", "60"))
EXPECT_ACCEPTED = int(os.getenv("EXPECT_ACCEPTED", "0"))
EXPECT_STALL = os.getenv("EXPECT_STALL", "0") == "1"
EXPECT_FLUSH = os.getenv("EXPECT_FLUSH", "0") == "1"


def signal_int(signal, name):
    try:
        return int(signal.value)
    except ValueError as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z value: {signal.value}"
        ) from exc


async def reset_active_high(dut, cycles=3):
    """
    Match the frozen Week-5 reset convention.
    """

    dut.reset.value = 1

    for _ in range(cycles):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


@cocotb.test()
async def test_live_retire_monitor(dut):
    """
    Correlate accepted executed instructions with live RTL retirement.

    Contract:

        FallingEdge + ReadOnly
            -> observe current MEM/WB D-stage retirement

        RisingEdge + ReadOnly
            -> old C -> new D
            -> old B -> new C
            -> accepted A -> new B

    Required invariants:

        - every accepted instruction retires exactly once;
        - retire IDs remain contiguous and in order;
        - stall bubbles do not retire;
        - flushed instructions do not retire;
        - D-stage instruction identity agrees with the propagated tag;
        - logical retire latency from accepted B admission to observed
          D retirement is exactly three loop cycles.
    """

    dut.clk.value = 0

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_active_high(dut)

    adapter = ExecutionEventAdapter()
    monitor = RetireMonitor()

    events_by_index = {}
    retire_events = []

    stall_cycles = 0
    flush_cycles = 0
    unsupported_cycles = 0

    for cycle in range(1, N_CYCLES + 1):
        # ----------------------------------------------------------
        # FALLING EDGE: architectural retirement observation.
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
                f"cycle={cycle}: D-stage identity mismatch for "
                f"instruction_id={current_d_tag.instruction_id}: "
                f"expected {current_d_tag.instruction:#010x}, "
                f"got {d_instr:#010x}"
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
            source_event = events_by_index[
                retired.instruction_id
            ]

            # Accepted instruction enters B at RisingEdge of its
            # ExecutionEvent cycle. It subsequently traverses:
            #
            #     B -> C -> D -> FallingEdge retirement
            #
            # under the frozen downstream pipeline contract.
            assert retired.cycle == source_event.cycle + 3, (
                f"instruction_id={retired.instruction_id}: "
                f"expected retire cycle "
                f"{source_event.cycle + 3}, "
                f"got {retired.cycle}"
            )

            retire_events.append(retired)

        # ----------------------------------------------------------
        # PRE-RISING-EDGE admission snapshot.
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
        # RISING EDGE: DUT pipeline state advances.
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

            events_by_index[event.instruction_index] = event
            accepted_tag = RetireTag.from_execution_event(event)

        # This mirrors the same sequential movement as the frozen DUT:
        #
        #     old C -> new D
        #     old B -> new C
        #     accepted A -> new B
        monitor.advance_pipeline(accepted_tag)

    # --------------------------------------------------------------
    # FINAL RETIRE INVARIANTS
    # --------------------------------------------------------------
    accepted_count = adapter.instruction_count
    retired_count = monitor.retired_count

    assert unsupported_cycles == 0, (
        f"fixture contained {unsupported_cycles} unsupported "
        "non-bubble cycles"
    )

    assert accepted_count > 0, (
        "live RTL produced no accepted instructions"
    )

    if EXPECT_ACCEPTED > 0:
        assert accepted_count == EXPECT_ACCEPTED, (
            f"expected {EXPECT_ACCEPTED} accepted instructions, "
            f"got {accepted_count}"
        )

    assert retired_count == accepted_count, (
        f"accepted/retired mismatch: "
        f"accepted={accepted_count}, retired={retired_count}"
    )

    retired_ids = [
        event.instruction_id
        for event in retire_events
    ]

    assert retired_ids == list(
        range(1, accepted_count + 1)
    ), (
        f"non-contiguous retire stream: {retired_ids}"
    )

    # With a sufficiently drained fixture, no valid tag may remain.
    assert monitor.stage_instruction_ids == (
        None,
        None,
        None,
    ), (
        "pipeline did not fully drain: "
        f"{monitor.stage_instruction_ids}"
    )

    if EXPECT_STALL:
        assert stall_cycles > 0, (
            "directed stall fixture did not exercise Reg_Stall"
        )
    else:
        assert stall_cycles == 0, (
            f"unexpected stall cycles: {stall_cycles}"
        )

    if EXPECT_FLUSH:
        assert flush_cycles > 0, (
            "directed flush fixture did not exercise PcSel"
        )
    else:
        assert flush_cycles == 0, (
            f"unexpected flush cycles: {flush_cycles}"
        )

    dut._log.info(
        "RETIRE_MONITOR_SUMMARY "
        f"cycles={N_CYCLES} "
        f"accepted={accepted_count} "
        f"retired={retired_count} "
        f"retire_ids="
        f"{','.join(str(value) for value in retired_ids)} "
        f"retire_cycles="
        f"{','.join(str(event.cycle) for event in retire_events)} "
        f"stall_cycles={stall_cycles} "
        f"flush_cycles={flush_cycles} "
        f"unsupported_cycles={unsupported_cycles}"
    )
