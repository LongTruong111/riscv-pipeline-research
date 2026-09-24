import time

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week5.impl.coverage_model import (
    L2CoverageCollector,
)
from research.week5.impl.l1_coverage import (
    L1CoverageCollector,
)
from research.week5.impl.realization_checker import (
    L1ControlRealizationChecker,
)
from research.week5.impl.validated_coverage import (
    L1ValidatedCoverageCollector,
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
from research.week9.coverage_collector import (
    CoverageCollector,
)
from research.week9.coverage_promotion import (
    promote_l1_attribution,
)
from research.week9.validated_attribution import (
    attribute_l1_hit,
)
from research.week10.adaptive.post_instruction_cut import (
    complete_post_instruction_cut,
)
from research.week10.l2_live_coordinator import (
    L2LiveCoordinator,
)
from research.week12.telemetry.first_failure import (
    FirstFailureRecorder,
)


TARGET = GOLDEN_PROGRAM_INSTRUCTION_COUNT
MAX_CYCLES = 120


_WRITEBACK_CHECK_NAMES = frozenset({
    "write_enable",
    "write_rd",
    "write_data",
    "unexpected_architectural_write",
})

_STORE_CHECK_NAMES = frozenset({
    "unexpected_store",
    "store_enable",
    "store_address_in_dut_range",
    "store_address",
    "store_data",
})


def functional_group_pass(result, names):
    checks = tuple(
        check
        for check in result.checks
        if check.name in names
    )

    if not checks:
        raise AssertionError(
            "missing functional check group: "
            f"instruction_id={result.instruction_id}"
        )

    return all(
        check.expected == check.observed
        for check in checks
    )


def functional_named_pass(result, name):
    checks = tuple(
        check
        for check in result.checks
        if check.name == name
    )

    if len(checks) != 1:
        raise AssertionError(
            f"expected exactly one {name!r} check, "
            f"got {len(checks)}"
        )

    return checks[0].expected == checks[0].observed


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
    first_failure = FirstFailureRecorder()

    l1_coverage = L1CoverageCollector()
    l2_coverage = L2CoverageCollector()

    l1_control = L1ControlRealizationChecker()
    l1_validated = L1ValidatedCoverageCollector()

    checkpoint_count = 0

    def checkpoint_sink(_checkpoint):
        nonlocal checkpoint_count
        checkpoint_count += 1

    coverage = CoverageCollector(
        checkpoint_interval=1000,
        retain_checkpoints=False,
        checkpoint_sink=checkpoint_sink,
    )

    l2_live = L2LiveCoordinator(
        l2_coverage=l2_coverage,
        coverage=coverage,
    )

    accepted_count = 0
    retired_count = 0
    observed_stall_cycles = 0
    observed_flush_cycles = 0

    coverage_observed_count = 0

    events_by_index = {}
    pending_next_pc = None

    # Exact-cap terminal evidence:
    # L2 hits whose consumer is instruction 58 cannot obtain a real
    # accepted successor and therefore remain authoritatively pending.
    terminal_l2_hit_count = 0

    measurement_start_ns = time.perf_counter_ns()

    def coverage_wall_ns():
        return time.perf_counter_ns() - measurement_start_ns

    def promote_l1_outcomes(
        outcomes,
        *,
        cycle,
        wall_ns,
    ):
        # This is the authoritative promotion path used by the
        # Week-9 LiveCoverageCoordinator. Week-7/Week-8 diagnostic
        # evidence is deliberately not required for Validated state.
        for outcome in outcomes:
            partial = attribute_l1_hit(
                bin_id=outcome.bin_id,
                instruction_id=(
                    outcome.consumer_instruction_index
                ),
                validation=outcome,
            )

            promote_l1_attribution(
                coverage,
                partial,
                resolution_cycle=cycle,
                wall_ns=wall_ns,
            )

    def record_architectural_result(
        *,
        instruction_id,
        kind,
        passed,
        cycle,
        wall_ns,
    ):
        l1_outcomes = (
            l1_validated.record_architectural_result(
                instruction_index=instruction_id,
                kind=kind,
                passed=passed,
            )
        )

        promote_l1_outcomes(
            l1_outcomes,
            cycle=cycle,
            wall_ns=wall_ns,
        )

        l2_live.record_architectural_result(
            instruction_id=instruction_id,
            kind=kind,
            passed=passed,
            cycle=cycle,
            wall_ns=wall_ns,
        )

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

            retirement_wall_ns = coverage_wall_ns()

            writeback_passed = functional_group_pass(
                functional_result,
                _WRITEBACK_CHECK_NAMES,
            )

            store_passed = functional_group_pass(
                functional_result,
                _STORE_CHECK_NAMES,
            )

            x0_passed = functional_named_pass(
                functional_result,
                "architectural_x0",
            )

            for kind, passed in (
                ("writeback", writeback_passed),
                ("store", store_passed),
                ("x0", x0_passed),
            ):
                record_architectural_result(
                    instruction_id=retired.instruction_id,
                    kind=kind,
                    passed=passed,
                    cycle=cycle,
                    wall_ns=retirement_wall_ns,
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

            accept_wall_ns = coverage_wall_ns()

            if pending_next_pc is not None:
                (
                    predecessor_id,
                    predecessor_next_pc,
                ) = pending_next_pc

                l2_live.record_successor_pc(
                    predecessor_instruction_id=predecessor_id,
                    expected_next_pc=predecessor_next_pc,
                    successor=event,
                    cycle=cycle,
                    wall_ns=accept_wall_ns,
                )

            architectural_step = architectural_model.step(
                event
            )

            assert architectural_step.pc_match, (
                "architectural PC mismatch: "
                f"instruction_id={event.instruction_index}"
            )

            record_architectural_result(
                instruction_id=event.instruction_index,
                kind="pc",
                passed=architectural_step.pc_match,
                cycle=cycle,
                wall_ns=accept_wall_ns,
            )

            pending_next_pc = (
                event.instruction_index,
                architectural_step.next_pc,
            )

            functional.register_expected(
                ExpectedRetire.from_architectural_step(
                    architectural_step
                )
            )

            def observe_coverage_for_event():
                nonlocal terminal_l2_hit_count

                events_by_index[
                    event.instruction_index
                ] = event

                # ----------------------------------------------
                # L1 Intent + frozen control + authoritative
                # Validated promotion.
                # ----------------------------------------------
                l1_hits = l1_coverage.observe(event)

                for hit in l1_hits:
                    coverage.record_l1_intent(
                        hit.bin_id,
                        instruction_id=(
                            hit.consumer_instruction_index
                        ),
                        cycle=cycle,
                        wall_ns=accept_wall_ns,
                    )

                    control = l1_control.check(
                        hit,
                        event,
                        events_by_index,
                    )

                    outcomes = l1_validated.register_hit(
                        hit,
                        control_passed=control.passed,
                    )

                    promote_l1_outcomes(
                        outcomes,
                        cycle=cycle,
                        wall_ns=accept_wall_ns,
                    )

                    assert control.passed, (
                        "L1 control realization failure: "
                        f"bin={hit.bin_id}, "
                        f"instruction_id="
                        f"{event.instruction_index}, "
                        f"failed_checks="
                        f"{control.failed_checks}"
                    )

                # ----------------------------------------------
                # L2 Intent + authoritative realization.
                # ----------------------------------------------
                l2_hits = l2_coverage.observe(event)

                if event.instruction_index == TARGET:
                    terminal_l2_hit_count = len(l2_hits)

                for hit in l2_hits:
                    producer_event = events_by_index[
                        hit.producer_instruction_index
                    ]

                    outcomes = l2_live.register_hit(
                        hit,
                        producer=producer_event,
                        consumer=event,
                        expectation=expectation,
                        cycle=cycle,
                        wall_ns=accept_wall_ns,
                    )

                    assert all(
                        outcome.control_passed
                        for outcome in outcomes
                    ), (
                        "L2 control realization failure: "
                        f"instruction_id="
                        f"{event.instruction_index}"
                    )

            coverage_observed_count = (
                complete_post_instruction_cut(
                    observed_count=(
                        coverage_observed_count
                    ),
                    instruction_index=(
                        event.instruction_index
                    ),
                    cycle=cycle,
                    coverage=coverage,
                    observe_coverage=(
                        observe_coverage_for_event
                    ),
                )
            )

            # L1 may require a d3 producer. After processing N,
            # N-3 can be discarded safely.
            stale_event_id = (
                event.instruction_index - 3
            )

            if stale_event_id > 0:
                events_by_index.pop(
                    stale_event_id,
                    None,
                )

            l1_validated.prune(
                latest_instruction_index=(
                    event.instruction_index
                )
            )

            l2_live.prune(
                latest_instruction_id=(
                    event.instruction_index
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

    # Golden canonical run must contain no captured failure evidence.
    assert first_failure.empty
    assert first_failure.first_failure is None
    assert first_failure.first_control_failure is None
    assert first_failure.first_functional_failure is None
    assert first_failure.first_performance_failure is None

    # ----------------------------------------------------------
    # Frozen coverage validity.
    # ----------------------------------------------------------
    assert coverage.executed_instructions == TARGET
    assert coverage_observed_count == TARGET

    # Golden-58 is below the frozen 1000-accepted checkpoint
    # interval. Zero checkpoints is therefore the expected result.
    assert checkpoint_count == 0
    assert coverage.checkpoints == []

    l1_intent_count = sum(
        state.intent_seen
        for state in coverage.l1_state.values()
    )

    l1_validated_count = sum(
        state.validated_seen
        for state in coverage.l1_state.values()
    )

    l2_intent_count = sum(
        state.intent_seen
        for state in coverage.l2_state.values()
    )

    l2_validated_count = sum(
        state.validated_seen
        for state in coverage.l2_state.values()
    )

    # Integration must be active; an empty collector is not a valid
    # coverage smoke result.
    assert l1_intent_count > 0
    assert l2_intent_count > 0

    # Validated is always a subset of Intent.
    assert all(
        (not state.validated_seen)
        or state.intent_seen
        for state in coverage.l1_state.values()
    )

    assert all(
        (not state.validated_seen)
        or state.intent_seen
        for state in coverage.l2_state.values()
    )

    assert l1_validated_count <= l1_intent_count
    assert l2_validated_count <= l2_intent_count

    # All L1 architectural requirements are resolvable by retirement;
    # no terminal-successor requirement exists in L1.
    assert l1_validated.pending_hits == 0
    assert l1_validated.rejected_hits == 0

    # Golden instruction 58 is LW->ADDI dependent and intentionally
    # ends at exact accepted boundary. Its L2 next_pc requirement
    # cannot be fabricated. Runtime must prove exactly that terminal
    # hit set remains pending, and nothing else.
    assert terminal_l2_hit_count > 0
    assert (
        l2_live.pending_hit_count
        == terminal_l2_hit_count
    )
    assert l2_live.rejected_hit_count == 0

    # Bounded retained state.
    assert len(events_by_index) <= 3
    assert l1_validated.architectural_cache_entries <= 5
    assert l2_live.architectural_cache_entries <= 6

    assert observed_flush_cycles == 0

    dut._log.info(
        "WEEK12_GOLDEN_E2E "
        f"accepted={accepted_count} "
        f"retired={retired_count} "
        f"stalls={observed_stall_cycles} "
        f"flushes={observed_flush_cycles} "
        f"functional_failed={functional.failed_count} "
        f"performance_failed={performance.failed_count} "
        f"excess_cycles={performance.total_excess_cycles} "
        f"first_failure={first_failure.first_failure} "
        f"coverage_executed={coverage.executed_instructions} "
        f"l1_intent={l1_intent_count} "
        f"l1_validated={l1_validated_count} "
        f"l2_intent={l2_intent_count} "
        f"l2_validated={l2_validated_count} "
        f"l2_terminal_pending="
        f"{l2_live.pending_hit_count} "
        f"checkpoints={checkpoint_count}"
    )
