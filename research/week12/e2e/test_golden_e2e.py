import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week5.impl.commit_scoreboard import (
    StoreObservation,
)
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week6.expected_retire import (
    ExpectedRetire,
)
from research.week6.golden_program import (
    GOLDEN_PROGRAM_INSTRUCTION_COUNT,
    build_golden_program,
)
from research.week7.retire_monitor import (
    RetireMonitor,
    RetireTag,
)
from research.week9.benchmark.streaming_functional import (
    StreamingFunctionalScoreboard,
)
from research.week9.benchmark.streaming_timing import (
    StreamingPerformanceMonitor,
    StreamingTimingOracleV1,
)


TARGET = GOLDEN_PROGRAM_INSTRUCTION_COUNT
MAX_CYCLES = 120


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


@cocotb.test()
async def test_golden_58_core_e2e(dut):
    words = tuple(build_golden_program())

    assert len(words) == TARGET == 58

    program = {
        index * 4: instruction
        for index, instruction in enumerate(words)
    }

    dut.clk.value = 0

    clock = Clock(
        dut.clk,
        10,
        units="ns",
    )
    cocotb.start_soon(clock.start())

    await reset_active_high(dut)

    adapter = ExecutionEventAdapter()
    retire_monitor = RetireMonitor()

    architectural_model = RV32ArchitecturalModel()

    timing_oracle = StreamingTimingOracleV1(
        program
    )
    performance = StreamingPerformanceMonitor()
    functional = StreamingFunctionalScoreboard()

    accepted_count = 0
    retired_count = 0
    observed_stall_cycles = 0
    observed_flush_cycles = 0

    completed_cycle = 0

    for cycle in range(1, MAX_CYCLES + 1):
        completed_cycle = cycle

        # ----------------------------------------------------------
        # FALLING EDGE: C-stage + retirement + pre-edge admission
        # ----------------------------------------------------------
        await FallingEdge(dut.clk)
        await ReadOnly()

        c_tag = retire_monitor.c_tag

        if c_tag is not None:
            c_instr = signal_int(
                dut.probe_c_instr,
                "probe_c_instr",
            )

            assert c_instr == c_tag.instruction, (
                "C-stage instruction identity mismatch: "
                f"id={c_tag.instruction_id}"
            )

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
                    instruction=c_instr,
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
            retired_count += 1

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

            assert functional_result.passed, (
                "functional failure: "
                f"instruction_id={retired.instruction_id}"
            )

            assert performance_result.passed, (
                "performance failure: "
                f"instruction_id={retired.instruction_id}, "
                f"delta={performance_result.delta_cycles}"
            )

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
        # RISING EDGE: finalize accepted instruction
        # ----------------------------------------------------------
        await RisingEdge(dut.clk)
        await ReadOnly()

        accepted_tag = None

        if pending is not None:
            if accepted_count >= TARGET:
                raise AssertionError(
                    "accepted instruction beyond Golden-58 boundary"
                )

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

            accepted_count += 1

            assert event.instruction_index == accepted_count

            expectation = timing_oracle.observe_accept(
                event
            )

            performance.register_expectation(
                expectation
            )

            architectural_step = architectural_model.step(
                event
            )

            assert architectural_step.pc_match, (
                "architectural PC mismatch: "
                f"instruction_id={event.instruction_index}"
            )

            functional.register_expected(
                ExpectedRetire.from_architectural_step(
                    architectural_step
                )
            )

            accepted_tag = RetireTag.from_execution_event(
                event
            )

        retire_monitor.advance_pipeline(
            accepted_tag
        )

        # Do not stop at the final accept. Drain through final retire.
        if retired_count == TARGET:
            break

    assert completed_cycle < MAX_CYCLES, (
        "Golden-58 did not fully retire before cycle limit"
    )

    assert accepted_count == TARGET
    assert adapter.instruction_count == TARGET
    assert retired_count == TARGET

    assert timing_oracle.generated_count == TARGET

    assert functional.expected_count == TARGET
    assert functional.checked_count == TARGET
    assert functional.failed_count == 0
    assert functional.pending_expected_count == 0
    assert functional.pending_store_count == 0
    assert functional.complete
    assert functional.overall_pass

    assert performance.expected_count == TARGET
    assert performance.checked_count == TARGET
    assert performance.failed_count == 0
    assert performance.pending_count == 0
    assert performance.total_excess_cycles == 0
    assert performance.complete
    assert performance.overall_pass

    assert observed_flush_cycles == 0

    dut._log.info(
        "WEEK12_GOLDEN_E2E "
        f"accepted={accepted_count} "
        f"retired={retired_count} "
        f"stalls={observed_stall_cycles} "
        f"flushes={observed_flush_cycles} "
        f"functional_failed={functional.failed_count} "
        f"performance_failed={performance.failed_count} "
        f"excess_cycles={performance.total_excess_cycles}"
    )
