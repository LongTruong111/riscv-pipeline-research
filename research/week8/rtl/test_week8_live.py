import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from research.week5.impl.commit_scoreboard import StoreObservation
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week5.impl.directed_cases import DIRECTED_CASES
from research.week6.expected_retire import build_expected_retire_log
from research.week7.retire_monitor import (
    RetireMonitor,
    RetireTag,
)
from research.week7.timing_oracle_v1 import (
    build_timing_schedule_v1,
)
from research.week8.cross_verdict import (
    CrossVerdictClass,
    combine_verdicts,
)
from research.week8.functional_scoreboard import (
    FunctionalScoreboard,
)
from research.week8.performance_monitor import (
    PerformanceMonitor,
)


N_CYCLES = 60


def signal_int(signal, name):
    try:
        return int(signal.value)
    except ValueError as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z: {signal.value}"
        ) from exc


async def reset_dut(dut):
    dut.reset.value = 1

    for _ in range(3):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


@cocotb.test()
async def test_week8_live_classification(dut):
    case_id = os.environ["CASE"]

    assert case_id in {"T01", "T19", "T20"}

    case = DIRECTED_CASES[case_id]

    program = {
        index * 4: word
        for index, word in enumerate(case.words)
    }

    timing_schedule = build_timing_schedule_v1(program)

    # Build functional expected log using the same executed-program-order
    # instruction identities predicted independently from the canonical
    # program.
    expected_events = []

    from research.week5.impl.execution_event import ExecutionEvent
    from research.week5.impl.isa_decode import decode_instruction

    for item in timing_schedule.expectations:
        decoded = decode_instruction(item.instruction)

        assert decoded is not None

        expected_events.append(
            ExecutionEvent(
                instruction_index=item.instruction_id,
                cycle=item.accept_cycle,
                pc=item.pc,
                instruction=item.instruction,
                rs1=decoded.rs1,
                rs2=decoded.rs2,
                rd=decoded.rd,
                uses_rs1=decoded.uses_rs1,
                uses_rs2=decoded.uses_rs2,
                writes_rd=decoded.writes_rd,
                producer_type=decoded.producer_type,
                consumer_type=decoded.consumer_type,
            )
        )

    expected_retires = build_expected_retire_log(
        expected_events
    )

    functional = FunctionalScoreboard(
        expected_retires
    )

    performance = PerformanceMonitor(
        timing_schedule.expectations
    )

    adapter = ExecutionEventAdapter()
    retire_monitor = RetireMonitor()

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    verdicts = []

    for cycle in range(1, N_CYCLES + 1):
        # ----------------------------------------------------------
        # FallingEdge: D logical retire + C physical store
        # ----------------------------------------------------------
        await FallingEdge(dut.clk)
        await ReadOnly()

        # C-stage identity belongs to verification-side monitor state.
        c_tag = retire_monitor.c_tag

        if c_tag is not None:
            functional.observe_store_stage(
                StoreObservation(
                    instruction_index=c_tag.instruction_id,
                    write_enable=bool(
                        signal_int(
                            dut.mem_wr,
                            "mem_wr",
                        )
                    ),
                    address=signal_int(
                        dut.mem_addr,
                        "mem_addr",
                    ),
                    data=signal_int(
                        dut.mem_wr_data,
                        "mem_wr_data",
                    ),
                    instruction=c_tag.instruction,
                )
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
            functional_result = functional.observe_retire(
                retired,
                observed_x0=signal_int(
                    dut.probe_x0,
                    "probe_x0",
                ),
            )

            performance_result = performance.observe_retire(
                retired
            )

            verdict = combine_verdicts(
                functional_result,
                performance_result,
            )

            verdicts.append(verdict)

            dut._log.info(
                "WEEK8_VERDICT "
                f"case={case_id} "
                f"instruction_id={verdict.instruction_id} "
                f"classification={verdict.classification.value} "
                f"functional_pass={int(verdict.functional_pass)} "
                f"performance_pass={int(verdict.performance_pass)} "
                f"delta={verdict.timing_delta_cycles} "
                f"functional_failed="
                f"{','.join(verdict.functional_failed_checks) or 'none'}"
            )

        # ----------------------------------------------------------
        # Pre-RisingEdge admission observation
        # ----------------------------------------------------------
        reset = bool(signal_int(dut.reset, "reset"))
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
        # RisingEdge: pipeline tag advance
        # ----------------------------------------------------------
        await RisingEdge(dut.clk)
        await ReadOnly()

        accepted_tag = None

        if pending is not None:
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

            accepted_tag = RetireTag.from_execution_event(
                event
            )

        retire_monitor.advance_pipeline(
            accepted_tag
        )

    assert functional.complete
    assert performance.complete

    classifications = tuple(
        verdict.classification
        for verdict in verdicts
    )

    if case_id == "T01":
        assert all(
            item == CrossVerdictClass.CORRECT_ON_TIME
            for item in classifications
        )

    elif case_id in {"T19", "T20"}:
        assert all(
            verdict.functional_pass
            for verdict in verdicts
        )

        assert any(
            not verdict.performance_pass
            for verdict in verdicts
        )

        assert any(
            verdict.classification
            == CrossVerdictClass.PERFORMANCE_ONLY_FAIL
            for verdict in verdicts
        )

    dut._log.info(
        "WEEK8_LIVE_SUMMARY "
        f"case={case_id} "
        f"instructions={len(verdicts)} "
        f"functional_failures={functional.failed_count} "
        f"performance_failures={performance.failed_count} "
        f"excess_cycles={performance.total_excess_cycles} "
        f"status=PASS"
    )
