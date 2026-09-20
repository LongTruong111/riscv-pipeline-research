import os
import time

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week5.impl.commit_scoreboard import (
    CommitScoreboard,
    StoreObservation,
    WritebackObservation,
)
from research.week5.impl.coverage_model import (
    L2CoverageCollector,
)
from research.week5.impl.directed_cases import (
    DIRECTED_CASES,
)
from research.week5.impl.l1_coverage import (
    L1CoverageCollector,
)
from research.week5.impl.realization_checker import (
    L1ControlRealizationChecker,
)
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week5.impl.validated_coverage import (
    L1ValidatedCoverageCollector,
)

from research.week7.hazard_attribution import (
    TimingObservation,
    correlate_hazard,
)
from research.week7.retire_monitor import (
    RetireMonitor,
    RetireTag,
)
from research.week7.timing_oracle_v1 import (
    build_timing_schedule_v1,
)

from research.week8.performance_monitor import (
    PerformanceMonitor,
)

from research.week9.coverage_collector import (
    CoverageCollector,
)
from research.week9.live_coverage_coordinator import (
    LiveCoverageCoordinator,
)
from research.week9.validated_attribution import (
    ValidationStatus,
)


N_CYCLES = int(os.getenv("N_CYCLES", "60"))
CASE_ID = os.getenv("CASE", "").strip()

ALL_CASES = frozenset(DIRECTED_CASES)

FROZEN_UNVALIDATED_BINS = frozenset(
    {
        "H11",
        "H13",
        "H18",
        "H19",
        "H20",
    }
)

# Diagnostic classifications are asserted only where already
# independently established by the Week-8/Week-9 smoke evidence.
EXPECTED_DIAGNOSTIC_STATUS = {
    "T01": ValidationStatus.REALIZED_CORRECTLY,
    "T11": ValidationStatus.FUNCTIONAL_MISMATCH,
    "T19": ValidationStatus.TIMING_MISMATCH,
    "T20": ValidationStatus.TIMING_MISMATCH,
}

def signal_int(signal, name):
    try:
        return int(signal.value)
    except ValueError as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z value: "
            f"{signal.value}"
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
async def test_week9_live_smoke(dut):
    assert CASE_ID in ALL_CASES, (
        f"CASE must be one of "
        f"{sorted(ALL_CASES)}, got {CASE_ID!r}"
    )
    case = DIRECTED_CASES[CASE_ID]

    timing_schedule = build_timing_schedule_v1(
        build_program(case.words)
    )

    assert (
        timing_schedule.instruction_count
        == case.expected_accepted
    )

    expected_by_id = {
        expectation.instruction_id: expectation
        for expectation in timing_schedule.expectations
    }

    dut.clk.value = 0

    clock = Clock(
        dut.clk,
        10,
        units="ns",
    )

    cocotb.start_soon(clock.start())

    await reset_active_high(dut)

    run_start_ns = time.perf_counter_ns()

    def wall_ns():
        return time.perf_counter_ns() - run_start_ns

    adapter = ExecutionEventAdapter()

    l1_coverage = L1CoverageCollector()
    l2_coverage = L2CoverageCollector()

    control_checker = L1ControlRealizationChecker()

    architectural_model = RV32ArchitecturalModel()
    commit_scoreboard = CommitScoreboard()

    validated_coverage = L1ValidatedCoverageCollector()

    retire_monitor = RetireMonitor()

    performance = PerformanceMonitor(
        timing_schedule.expectations
    )

    week9_coverage = CoverageCollector(
        retain_checkpoints=False,
    )

    coordinator = LiveCoverageCoordinator(
        coverage=week9_coverage,
    )

    # Only unresolved/in-flight state is retained.
    events_by_index = {}
    steps_by_index = {}

    timing_observations = {}
    hits_by_consumer = {}

    accepted_count = 0
    retired_count = 0
    attribution_count = 0

    target_status_counts = {
        status: 0
        for status in ValidationStatus
    }

    def handle_attribution_records(records):
        nonlocal attribution_count

        for record in records:
            attribution_count += 1

            if record.intent_bin == case.target_bin:
                target_status_counts[
                    record.status
                ] += 1

            dut._log.info(
                "WEEK9_ATTRIBUTION "
                f"case={CASE_ID} "
                f"bin={record.intent_bin} "
                f"instruction_id="
                f"{record.instruction_id} "
                f"validated={int(record.validated)} "
                f"status={record.status.value} "
                f"control_pass="
                f"{record.control_pass} "
                f"architectural_pass="
                f"{record.functional_pass} "
                f"performance_pass="
                f"{record.performance_pass} "
                f"delta="
                f"{record.timing_delta_cycles}"
            )

    def record_validation_outcomes(
        outcomes,
        *,
        cycle,
    ):
        for outcome in outcomes:
            records = coordinator.record_validation(
                outcome,
                resolution_cycle=cycle,
                wall_ns=wall_ns(),
            )

            handle_attribution_records(records)

    def record_architectural_result(
        result,
        *,
        cycle,
    ):
        outcomes = (
            validated_coverage
            .record_architectural_result(
                instruction_index=(
                    result.instruction_index
                ),
                kind=result.kind,
                passed=result.passed,
            )
        )

        record_validation_outcomes(
            outcomes,
            cycle=cycle,
        )

    for cycle in range(1, N_CYCLES + 1):
        # ----------------------------------------------------------
        # FALLING EDGE
        #
        # D: logical retire + writeback/x0
        # C: physical store
        # A: pre-edge admission observation
        # ----------------------------------------------------------
        await FallingEdge(dut.clk)
        await ReadOnly()

        d_tag = retire_monitor.d_tag
        c_tag = retire_monitor.c_tag

        if d_tag is not None:
            instruction_id = d_tag.instruction_id

            step = steps_by_index[
                instruction_id
            ]

            d_instr = signal_int(
                dut.probe_d_instr,
                "probe_d_instr",
            )

            assert (
                d_instr == d_tag.instruction
            ), (
                f"{CASE_ID}: "
                f"cycle={cycle}: "
                f"D identity mismatch for "
                f"instruction_id={instruction_id}"
            )

            wb_result = (
                commit_scoreboard.check_writeback(
                    step,
                    WritebackObservation(
                        instruction_index=(
                            instruction_id
                        ),
                        write_enable=bool(
                            signal_int(
                                dut.reg_write_sig,
                                "reg_write_sig",
                            )
                        ),
                        rd=signal_int(
                            dut.reg_num,
                            "reg_num",
                        ),
                        data=signal_int(
                            dut.reg_data,
                            "reg_data",
                        ),
                        instruction=d_instr,
                    ),
                )
            )

            record_architectural_result(
                wb_result,
                cycle=cycle,
            )

            x0_result = (
                commit_scoreboard.check_x0(
                    instruction_index=(
                        instruction_id
                    ),
                    observed_value=signal_int(
                        dut.probe_x0,
                        "probe_x0",
                    ),
                )
            )

            record_architectural_result(
                x0_result,
                cycle=cycle,
            )

            # No longer needed after D architectural evidence.
            steps_by_index.pop(
                instruction_id,
                None,
            )

        if c_tag is not None:
            instruction_id = c_tag.instruction_id

            step = steps_by_index[
                instruction_id
            ]

            c_instr = signal_int(
                dut.probe_c_instr,
                "probe_c_instr",
            )

            assert (
                c_instr == c_tag.instruction
            ), (
                f"{CASE_ID}: "
                f"cycle={cycle}: "
                f"C identity mismatch for "
                f"instruction_id={instruction_id}"
            )

            store_result = (
                commit_scoreboard.check_store(
                    step,
                    StoreObservation(
                        instruction_index=(
                            instruction_id
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
                    ),
                )
            )

            record_architectural_result(
                store_result,
                cycle=cycle,
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
            instruction_id = retired.instruction_id
            retired_count += 1

            performance_result = (
                performance.observe_retire(
                    retired
                )
            )

            observation = (
                timing_observations.pop(
                    instruction_id
                )
            )

            hits = hits_by_consumer.pop(
                instruction_id,
                (),
            )

            # Performance evidence belongs to the consumer and can be
            # shared by all L1 hits emitted for that consumer.
            if hits:
                handle_attribution_records(
                    coordinator.record_performance(
                        performance_result
                    )
                )

                for hit in hits:
                    hazard = correlate_hazard(
                        hit,
                        expected_by_id[
                            instruction_id
                        ],
                        observation,
                        retired,
                    )

                    handle_attribution_records(
                        coordinator.record_hazard(
                            hazard
                        )
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
        #
        # Accepted instruction becomes verification-side B tag.
        # Forwarding selectors sampled after ReadOnly.
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

            instruction_id = (
                event.instruction_index
            )

            accepted_count += 1

            assert (
                instruction_id
                == accepted_count
            )

            assert instruction_id in expected_by_id

            expected = expected_by_id[
                instruction_id
            ]

            assert event.pc == expected.pc
            assert (
                event.instruction
                == expected.instruction
            )

            week9_coverage.record_instruction(
                instruction_id=instruction_id,
                cycle=cycle,
            )

            timing_observations[
                instruction_id
            ] = (
                TimingObservation
                .from_execution_event(event)
            )

            # Independent architectural model.
            architectural_step = (
                architectural_model.step(event)
            )

            steps_by_index[
                instruction_id
            ] = architectural_step

            pc_result = (
                commit_scoreboard.check_pc(
                    architectural_step
                )
            )

            record_architectural_result(
                pc_result,
                cycle=cycle,
            )

            # Preserve only recent history required by frozen L1
            # control attribution.
            events_by_index[
                instruction_id
            ] = event

            # ------------------------------------------------------
            # L2 Intent only.
            # No L2 Validated promotion is invented here.
            # ------------------------------------------------------
            l2_hits = l2_coverage.observe(
                event
            )

            for hit in l2_hits:
                week9_coverage.record_l2_intent(
                    f"d{hit.distance}",
                    hit.register,
                    instruction_id=(
                        hit.consumer_instruction_index
                    ),
                    cycle=cycle,
                    wall_ns=wall_ns(),
                )

            # ------------------------------------------------------
            # L1 Intent + frozen authoritative validation.
            # ------------------------------------------------------
            l1_hits = l1_coverage.observe(
                event
            )

            if l1_hits:
                hits_by_consumer[
                    instruction_id
                ] = l1_hits

            for hit in l1_hits:
                coordinator.register_l1_intent(
                    hit,
                    cycle=cycle,
                    wall_ns=wall_ns(),
                )

                control = (
                    control_checker.check(
                        hit,
                        event,
                        events_by_index,
                    )
                )

                outcomes = (
                    validated_coverage.register_hit(
                        hit,
                        control_passed=(
                            control.passed
                        ),
                    )
                )

                record_validation_outcomes(
                    outcomes,
                    cycle=cycle,
                )

            # Frozen dependency scope requires only recent event
            # history through d3.
            stale_event_index = (
                instruction_id - 4
            )

            if stale_event_index > 0:
                events_by_index.pop(
                    stale_event_index,
                    None,
                )

            validated_coverage.prune(
                latest_instruction_index=(
                    instruction_id
                )
            )

            accepted_tag = (
                RetireTag.from_execution_event(
                    event
                )
            )

        retire_monitor.advance_pipeline(
            accepted_tag
        )

    # --------------------------------------------------------------
    # FINAL INVARIANTS
    # --------------------------------------------------------------
    assert (
        accepted_count
        == case.expected_accepted
    )

    assert retired_count == accepted_count

    assert (
        week9_coverage.executed_instructions
        == accepted_count
    )

    assert performance.complete

    assert timing_observations == {}
    assert hits_by_consumer == {}

    assert coordinator.pending_hit_count == 0

    assert (
        coordinator.retained_performance_count
        == 0
    )

    target_state = (
        week9_coverage.l1_state[
            case.target_bin
        ]
    )

    assert target_state.intent_seen is True

    expected_validated = (
        case.target_bin
        not in FROZEN_UNVALIDATED_BINS
    )
    
    assert (
        target_state.validated_seen
        is expected_validated
    ), (
        f"{CASE_ID}/{case.target_bin}: "
        f"expected target_validated="
        f"{int(expected_validated)}, got "
        f"{int(target_state.validated_seen)}"
    )
    
    expected_status = (
        EXPECTED_DIAGNOSTIC_STATUS.get(
            CASE_ID
        )
    )
    
    if expected_status is not None:
        assert (
            target_status_counts[
                expected_status
            ]
            >= 1
        ), (
            f"{CASE_ID}/{case.target_bin}: "
            f"expected diagnostic status "
            f"{expected_status.value}"
        )

    # Week-9 has not invented an L2 RealizationValid checker.
    assert all(
        not state.validated_seen
        for state
        in week9_coverage.l2_state.values()
    )

    l1_intent_count = sum(
        state.intent_seen
        for state
        in week9_coverage.l1_state.values()
    )

    l1_validated_count = sum(
        state.validated_seen
        for state
        in week9_coverage.l1_state.values()
    )

    l2_intent_count = sum(
        state.intent_seen
        for state
        in week9_coverage.l2_state.values()
    )

    target_status_text = (
        expected_status.value
        if expected_status is not None
        else "OBSERVED_ONLY"
    )
    
    dut._log.info(
        "WEEK9_LIVE_SMOKE "
        f"case={CASE_ID} "
        f"target={case.target_bin} "
        f"accepted={accepted_count} "
        f"retired={retired_count} "
        f"attributions={attribution_count} "
        f"l1_intent={l1_intent_count} "
        f"l1_validated={l1_validated_count} "
        f"l2_intent={l2_intent_count} "
        f"target_validated="
        f"{int(target_state.validated_seen)} "
        f"target_status={target_status_text} "
        f"pending="
        f"{coordinator.pending_hit_count}"
    )
