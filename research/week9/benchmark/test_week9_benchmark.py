import os
import time

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import (
    FallingEdge,
    ReadOnly,
    RisingEdge,
)

from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week5.impl.commit_scoreboard import (
    StoreObservation,
)
from research.week5.impl.coverage_model import (
    L2CoverageCollector,
)
from research.week5.impl.l1_coverage import (
    L1CoverageCollector,
)
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week6.expected_retire import (
    ExpectedRetire,
)
from research.week7.retire_monitor import (
    RetireMonitor,
    RetireTag,
)
from research.week9.benchmark.metrics import (
    BenchmarkSample,
    BenchmarkTracker,
    read_current_rss_kib,
)
from research.week9.benchmark.streaming_functional import (
    StreamingFunctionalScoreboard,
)
from research.week9.benchmark.streaming_timing import (
    StreamingPerformanceMonitor,
    StreamingTimingOracleV1,
)
from research.week9.coverage_collector import (
    CoverageCollector,
)


BENCH_CYCLES = int(
    os.getenv("BENCH_CYCLES", "10000")
)


BENCH_PROGRAM_WORDS = (
    0x00000093,  # ADDI x1, x0, 0
    0x00100113,  # ADDI x2, x0, 1
    0x002101B3,  # ADD  x3, x2, x2
    0x0030A023,  # SW   x3, 0(x1)
    0x0000A203,  # LW   x4, 0(x1)
    0x002202B3,  # ADD  x5, x4, x2
    0x00328333,  # ADD  x6, x5, x3
    0xFEDFF3EF,  # JAL  x7, -20 -> PC 0x08
)


BENCH_PROGRAM = {
    index * 4: instruction
    for index, instruction
    in enumerate(BENCH_PROGRAM_WORDS)
}


def signal_int(signal, name):
    try:
        return int(signal.value)
    except ValueError as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z value: "
            f"{signal.value}"
        ) from exc


async def reset_active_high(
    dut,
    cycles=3,
):
    dut.reset.value = 1

    for _ in range(cycles):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()

@cocotb.test()
async def test_week9_streaming_benchmark(dut):
    if BENCH_CYCLES < 10:
        raise ValueError(
            "BENCH_CYCLES must be at least 10"
        )

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

    architectural_model = (
        RV32ArchitecturalModel()
    )

    timing_oracle = (
        StreamingTimingOracleV1(
            BENCH_PROGRAM
        )
    )

    performance = (
        StreamingPerformanceMonitor()
    )

    functional = (
        StreamingFunctionalScoreboard()
    )

    l1_coverage = L1CoverageCollector()
    l2_coverage = L2CoverageCollector()

    checkpoint_count = 0

    def checkpoint_sink(_checkpoint):
        nonlocal checkpoint_count
        checkpoint_count += 1

    week9_coverage = CoverageCollector(
        checkpoint_interval=1000,
        retain_checkpoints=False,
        checkpoint_sink=checkpoint_sink,
    )

    tracker = BenchmarkTracker()

    accepted_count = 0
    retired_count = 0

    functional_failures = 0
    performance_failures = 0

    measurement_start_ns = (
        time.perf_counter_ns()
    )

    tracker.record_start(
        BenchmarkSample(
            cycle=0,
            executed_instructions=0,
            wall_ns=measurement_start_ns,
            rss_kib=read_current_rss_kib(),
            pending_hits=0,
            retained_performance=0,
            timing_observations=0,
            architectural_steps=0,
            recent_events=0,
        )
    )

    midpoint_cycle = BENCH_CYCLES // 2

    for cycle in range(
        1,
        BENCH_CYCLES + 1,
    ):
        # ------------------------------------------------------
        # FALLING EDGE
        # ------------------------------------------------------
        await FallingEdge(dut.clk)
        await ReadOnly()

        c_tag = retire_monitor.c_tag
        if c_tag is not None:
            c_instr = signal_int(
                dut.probe_c_instr,
                "probe_c_instr",
            )

            assert (
                c_instr
                == c_tag.instruction
            ), (
                "C-stage instruction identity "
                "mismatch: "
                f"id={c_tag.instruction_id}"
            )

            functional.observe_store_stage(
                StoreObservation(
                    instruction_index=(
                        c_tag.instruction_id
                    ),
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

        retired = (
            retire_monitor.observe_falling_edge(
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
        )

        if retired is not None:
            retired_count += 1

            functional_result = (
                functional.observe_retire(
                    retired,
                    observed_x0=signal_int(
                        dut.probe_x0,
                        "probe_x0",
                    ),
                )
            )

            if not functional_result.passed:
                functional_failures += 1

            performance_result = (
                performance.observe_retire(
                    retired
                )
            )

            if not performance_result.passed:
                performance_failures += 1

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

        # ------------------------------------------------------
        # RISING EDGE
        # ------------------------------------------------------
        await RisingEdge(dut.clk)
        await ReadOnly()

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
            assert (
                b_instr
                == pending.instruction
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

            accepted_count += 1

            assert (
                event.instruction_index
                == accepted_count
            )

            expectation = (
                timing_oracle.observe_accept(
                    event
                )
            )

            performance.register_expectation(
                expectation
            )

            architectural_step = (
                architectural_model.step(
                    event
                )
            )

            assert architectural_step.pc_match

            functional.register_expected(
                ExpectedRetire
                .from_architectural_step(
                    architectural_step
                )
            )

            week9_coverage.record_instruction(
                instruction_id=(
                    event.instruction_index
                ),
                cycle=cycle,
            )

            for hit in l1_coverage.observe(
                event
            ):
                week9_coverage.record_l1_intent(
                    hit.bin_id,
                    instruction_id=(
                        hit
                        .consumer_instruction_index
                    ),
                    cycle=cycle,
                    wall_ns=(
                        time.perf_counter_ns()
                        - measurement_start_ns
                    ),
                )

            for hit in l2_coverage.observe(
                event
            ):
                week9_coverage.record_l2_intent(
                    f"d{hit.distance}",
                    hit.register,
                    instruction_id=(
                        hit
                        .consumer_instruction_index
                    ),
                    cycle=cycle,
                    wall_ns=(
                        time.perf_counter_ns()
                        - measurement_start_ns
                    ),
                )

            accepted_tag = (
                RetireTag.from_execution_event(
                    event
                )
            )

        retire_monitor.advance_pipeline(
            accepted_tag
        )

        # Scalar/bounded-state tracking only.
        state_sample = BenchmarkSample(
            cycle=cycle,
            executed_instructions=(
                week9_coverage
                .executed_instructions
            ),
            wall_ns=time.perf_counter_ns(),
            # RSS is sampled only at start/mid/end.
            # Intermediate value is unused by maxima.
            rss_kib=0,
            pending_hits=0,
            retained_performance=(
                performance.pending_count
            ),
            timing_observations=(
                performance.pending_count
            ),
            architectural_steps=(
                functional
                .pending_expected_count
            ),
            recent_events=0,
        )

        tracker.observe_state(
            state_sample
        )

        if cycle == midpoint_cycle:
            tracker.record_mid(
                BenchmarkSample(
                    cycle=cycle,
                    executed_instructions=(
                        week9_coverage
                        .executed_instructions
                    ),
                    wall_ns=(
                        time.perf_counter_ns()
                    ),
                    rss_kib=(
                        read_current_rss_kib()
                    ),
                    pending_hits=0,
                    retained_performance=(
                        performance.pending_count
                    ),
                    timing_observations=(
                        performance.pending_count
                    ),
                    architectural_steps=(
                        functional
                        .pending_expected_count
                    ),
                    recent_events=0,
                )
            )

    tracker.record_end(
        BenchmarkSample(
            cycle=BENCH_CYCLES,
            executed_instructions=(
                week9_coverage
                .executed_instructions
            ),
            wall_ns=time.perf_counter_ns(),
            rss_kib=read_current_rss_kib(),
            pending_hits=0,
            retained_performance=(
                performance.pending_count
            ),
            timing_observations=(
                performance.pending_count
            ),
            architectural_steps=(
                functional
                .pending_expected_count
            ),
            recent_events=0,
        )
    )

    summary = tracker.summary()

    # ----------------------------------------------------------
    # Bounded-state invariants
    # ----------------------------------------------------------
    assert accepted_count > 0
    assert retired_count > 0

    assert (
        week9_coverage.executed_instructions
        == accepted_count
    )

    assert (
        performance.expected_count
        == accepted_count
    )

    assert (
        functional.expected_count
        == accepted_count
    )

    assert (
        performance.checked_count
        == retired_count
    )

    assert (
        functional.checked_count
        == retired_count
    )

    assert (
        performance.pending_count
        == accepted_count
        - retired_count
    )

    assert (
        functional.pending_expected_count
        == accepted_count
        - retired_count
    )

    assert performance.pending_count <= 3
    assert (
        functional.pending_expected_count
        <= 3
    )

    assert (
        functional.pending_store_count
        <= 1
    )

    assert (
        summary.max_retained_performance
        <= 3
    )

    assert (
        summary.max_architectural_steps
        <= 3
    )

    assert functional_failures == 0
    assert performance_failures == 0

    # Checkpoints are streamed, never retained.
    assert week9_coverage.checkpoints == []

    expected_checkpoint_count = (
        accepted_count // 1000
    )

    assert (
        checkpoint_count
        == expected_checkpoint_count
    )

    # Long-run program uses exactly one word of data memory.
    # Sparse byte-addressed golden memory may therefore contain
    # at most four entries.
    assert (
        len(architectural_model._memory)
        <= 4
    )

    assert (
        len(timing_oracle._model._memory)
        <= 4
    )

    l1_intent_count = sum(
        state.intent_seen
        for state
        in week9_coverage.l1_state.values()
    )

    l2_intent_count = sum(
        state.intent_seen
        for state
        in week9_coverage.l2_state.values()
    )

    estimated_100k_cycles_seconds = (
        100_000
        / summary.cycles_per_second
    )

    dut._log.info(
        "WEEK9_BENCHMARK_RESULT "
        f"cycles={summary.cycles} "
        f"instructions="
        f"{summary.executed_instructions} "
        f"wall_s={summary.wall_seconds:.6f} "
        f"cycles_per_s="
        f"{summary.cycles_per_second:.3f} "
        f"instructions_per_s="
        f"{summary.instructions_per_second:.3f} "
        f"first_half_cps="
        f"{summary.first_half_cycles_per_second:.3f} "
        f"second_half_cps="
        f"{summary.second_half_cycles_per_second:.3f} "
        f"throughput_degradation_pct="
        f"{summary.throughput_degradation_pct:.3f} "
        f"rss_start_kib={summary.rss_start_kib} "
        f"rss_mid_kib={summary.rss_mid_kib} "
        f"rss_end_kib={summary.rss_end_kib} "
        f"rss_mid_delta_kib="
        f"{summary.rss_mid_delta_kib} "
        f"rss_end_delta_kib="
        f"{summary.rss_end_delta_kib} "
        f"max_perf_pending="
        f"{summary.max_retained_performance} "
        f"max_functional_pending="
        f"{summary.max_architectural_steps} "
        f"functional_failures="
        f"{functional_failures} "
        f"performance_failures="
        f"{performance_failures} "
        f"l1_intent={l1_intent_count} "
        f"l2_intent={l2_intent_count} "
        f"checkpoints={checkpoint_count} "
        f"slowdown_vs_t5_minimal_pct="
        f"{summary.slowdown_vs_t5_minimal_pct:.3f} "
        f"slowdown_vs_t5_monitor_pct="
        f"{summary.slowdown_vs_t5_monitor_pct:.3f} "
        f"est_100k_cycles_s="
        f"{estimated_100k_cycles_seconds:.3f} "
        f"est_100k_instr_s="
        f"{summary.estimated_100k_instruction_seconds:.3f}"
    )
