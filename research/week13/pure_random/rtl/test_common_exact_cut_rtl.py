from __future__ import annotations

import time

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import (
    FallingEdge,
    ReadOnly,
    RisingEdge,
    Timer,
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
from research.week5.impl.realization_checker import (
    L1ControlRealizationChecker,
)
from research.week5.impl.rv32_encode import (
    addi,
)
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week5.impl.validated_coverage import (
    L1ValidatedCoverageCollector,
)
from research.week6.expected_retire import (
    ExpectedRetire,
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
from research.week10.l2_live_coordinator import (
    L2LiveCoordinator,
)

from research.week13.campaign.cut_driver import (
    CampaignCutDriver,
)
from research.week13.campaign.invariant_ledger import (
    CampaignInvariantLedger,
)
from research.week13.campaign.snapshot_adapter import (
    CAMPAIGN_MAX_IN_FLIGHT_DEPTH,
    build_campaign_lifecycle_snapshot,
)


CLOCK_NS = 10
TARGET = 4
MAX_CYCLES = 32


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


def signal_int(signal, name: str) -> int:
    try:
        return int(signal.value)
    except ValueError as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z: {signal.value}"
        ) from exc


def functional_group_pass(
    result,
    names,
) -> bool:
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


def functional_named_pass(
    result,
    name: str,
) -> bool:
    checks = tuple(
        check
        for check in result.checks
        if check.name == name
    )

    if len(checks) != 1:
        raise AssertionError(
            f"expected one {name!r} check, "
            f"got {len(checks)}"
        )

    return (
        checks[0].expected
        == checks[0].observed
    )


async def patch_word(
    dut,
    *,
    address: int,
    word: int,
) -> None:
    assert address % 4 == 0
    assert 0 <= address <= 508

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = address
    dut.imem_patch_data.value = word

    await Timer(1, units="ns")

    dut.imem_patch_strobe.value = 1
    await Timer(1, units="ns")

    dut.imem_patch_strobe.value = 0
    await Timer(1, units="ns")


async def reset_active_high(
    dut,
    *,
    cycles: int = 3,
) -> None:
    dut.reset.value = 1

    for _ in range(cycles):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)

    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


@cocotb.test()
async def test_common_exact_cut_rtl_n4(
    dut,
):
    """
    Week-13 common exact-cut RTL qualification.

    Proves on the real DUT scheduler:

      - accepted denominator is exact N=4;
      - checkpoint #2 and final checkpoint #4 use the same path;
      - lifecycle conservation holds at every accepted cut;
      - final accepted event is not pipeline-drained;
      - adapter count remains exactly N;
      - clock is killed HIGH in the same cycle as final cut;
      - no instruction #5 is accepted despite a valid resident suffix.
    """

    # ----------------------------------------------------------
    # Deterministic straight-line image.
    #
    # Words 5 and 6 are deliberately valid resident suffix words.
    # They would execute if the clock were allowed to continue.
    # ----------------------------------------------------------
    words = (
        addi(1, 0, 1),
        addi(2, 0, 2),
        addi(3, 0, 3),
        addi(4, 0, 4),

        addi(5, 0, 5),
        addi(6, 0, 6),
    )

    program = {
        index * 4: word
        for index, word in enumerate(words)
    }

    # ----------------------------------------------------------
    # Verification interface initialization.
    # ----------------------------------------------------------
    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    await Timer(1, units="ns")

    for address, word in program.items():
        await patch_word(
            dut,
            address=address,
            word=word,
        )

    # ----------------------------------------------------------
    # Frozen checker/reference stack.
    # ----------------------------------------------------------
    adapter = ExecutionEventAdapter()
    retire_monitor = RetireMonitor()

    architectural_model = (
        RV32ArchitecturalModel()
    )

    timing_oracle = (
        StreamingTimingOracleV1(
            program
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

    l1_control = (
        L1ControlRealizationChecker()
    )

    l1_validated = (
        L1ValidatedCoverageCollector()
    )

    checkpoints = []

    def checkpoint_sink(checkpoint):
        checkpoints.append(
            checkpoint
        )

    coverage = CoverageCollector(
        checkpoint_interval=2,
        retain_checkpoints=False,
        checkpoint_sink=(
            checkpoint_sink
        ),
    )

    l2_live = L2LiveCoordinator(
        l2_coverage=l2_coverage,
        coverage=coverage,
    )

    ledger = CampaignInvariantLedger(
        hard_cap=TARGET,
        max_in_flight_depth=(
            CAMPAIGN_MAX_IN_FLIGHT_DEPTH
        ),
    )

    cut_driver = CampaignCutDriver(
        hard_cap=TARGET,
        coverage=coverage,
        ledger=ledger,
    )

    # ----------------------------------------------------------
    # Continuous bounded evidence.
    # ----------------------------------------------------------
    events_by_index = {}
    pending_next_pc = None

    measurement_start_ns = (
        time.perf_counter_ns()
    )

    def wall_ns() -> int:
        return (
            time.perf_counter_ns()
            - measurement_start_ns
        )

    def promote_l1_outcomes(
        outcomes,
        *,
        cycle: int,
        observation_wall_ns: int,
    ) -> None:
        for outcome in outcomes:
            partial = attribute_l1_hit(
                bin_id=outcome.bin_id,
                instruction_id=(
                    outcome
                    .consumer_instruction_index
                ),
                validation=outcome,
            )

            promote_l1_attribution(
                coverage,
                partial,
                resolution_cycle=cycle,
                wall_ns=(
                    observation_wall_ns
                ),
            )

    def record_architectural_result(
        *,
        instruction_id: int,
        kind: str,
        passed: bool,
        cycle: int,
        observation_wall_ns: int,
    ) -> None:
        l1_outcomes = (
            l1_validated
            .record_architectural_result(
                instruction_index=(
                    instruction_id
                ),
                kind=kind,
                passed=passed,
            )
        )

        promote_l1_outcomes(
            l1_outcomes,
            cycle=cycle,
            observation_wall_ns=(
                observation_wall_ns
            ),
        )

        l2_live.record_architectural_result(
            instruction_id=(
                instruction_id
            ),
            kind=kind,
            passed=passed,
            cycle=cycle,
            wall_ns=(
                observation_wall_ns
            ),
        )

    # ----------------------------------------------------------
    # Sole clock owner.
    # ----------------------------------------------------------
    clock = Clock(
        dut.clk,
        CLOCK_NS,
        units="ns",
    )

    clock_task = cocotb.start_soon(
        clock.start()
    )

    await reset_active_high(
        dut,
        cycles=3,
    )

    assert (
        signal_int(
            dut.reset,
            "reset",
        )
        == 0
    )

    cycle = 0
    final_snapshot = None
    cut_cycle = None

    # ----------------------------------------------------------
    # Exact-cut execution.
    # ----------------------------------------------------------
    while True:
        if cycle >= MAX_CYCLES:
            clock_task.kill()

            raise AssertionError(
                "tiny exact-cut RTL test "
                "exceeded cycle budget"
            )

        # ======================================================
        # FALLING EDGE
        # ======================================================
        await FallingEdge(
            dut.clk
        )

        await ReadOnly()

        cycle += 1

        cut_driver.note_clock_edge(
            cycle=cycle,
            edge="falling",
        )

        c_tag = retire_monitor.c_tag

        if c_tag is not None:
            c_instr = signal_int(
                dut.probe_c_instr,
                "probe_c_instr",
            )

            assert (
                c_instr
                == c_tag.instruction
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
            retire_monitor
            .observe_falling_edge(
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
            functional_result = (
                functional.observe_retire(
                    retired,
                    observed_x0=signal_int(
                        dut.probe_x0,
                        "probe_x0",
                    ),
                )
            )

            performance_result = (
                performance.observe_retire(
                    retired
                )
            )

            retire_wall_ns = wall_ns()

            for kind, passed in (
                (
                    "writeback",
                    functional_group_pass(
                        functional_result,
                        _WRITEBACK_CHECK_NAMES,
                    ),
                ),
                (
                    "store",
                    functional_group_pass(
                        functional_result,
                        _STORE_CHECK_NAMES,
                    ),
                ),
                (
                    "x0",
                    functional_named_pass(
                        functional_result,
                        "architectural_x0",
                    ),
                ),
            ):
                record_architectural_result(
                    instruction_id=(
                        retired.instruction_id
                    ),
                    kind=kind,
                    passed=passed,
                    cycle=cycle,
                    observation_wall_ns=(
                        retire_wall_ns
                    ),
                )

            assert (
                functional_result.passed
            )

            assert (
                performance_result.passed
            )

        pending = (
            adapter.observe_pre_edge(
                PreEdgeSnapshot(
                    cycle=cycle,
                    reset=bool(
                        signal_int(
                            dut.reset,
                            "reset",
                        )
                    ),
                    stall=bool(
                        signal_int(
                            dut.probe_stall,
                            "probe_stall",
                        )
                    ),
                    flush_redirect=bool(
                        signal_int(
                            dut.probe_flush,
                            "probe_flush",
                        )
                    ),
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
        )

        # ======================================================
        # RISING EDGE
        # ======================================================
        await RisingEdge(
            dut.clk
        )

        await ReadOnly()

        cut_driver.note_clock_edge(
            cycle=cycle,
            edge="rising",
        )

        accepted_tag = None

        if pending is not None:
            assert (
                adapter.instruction_count
                < TARGET
            )

            assert (
                signal_int(
                    dut.probe_b_pc,
                    "probe_b_pc",
                )
                == pending.pc
            )

            assert (
                signal_int(
                    dut.probe_b_instr,
                    "probe_b_instr",
                )
                == pending.instruction
            )

            event = (
                adapter.finalize_post_edge(
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
            )

            assert (
                event.instruction_index
                <= TARGET
            )

            expectation = (
                timing_oracle
                .observe_accept(
                    event
                )
            )

            performance.register_expectation(
                expectation
            )

            accept_wall_ns = wall_ns()

            if pending_next_pc is not None:
                (
                    predecessor_id,
                    predecessor_next_pc,
                ) = pending_next_pc

                l2_live.record_successor_pc(
                    predecessor_instruction_id=(
                        predecessor_id
                    ),
                    expected_next_pc=(
                        predecessor_next_pc
                    ),
                    successor=event,
                    cycle=cycle,
                    wall_ns=(
                        accept_wall_ns
                    ),
                )

            architectural_step = (
                architectural_model.step(
                    event
                )
            )

            assert (
                architectural_step.pc_match
            )

            record_architectural_result(
                instruction_id=(
                    event.instruction_index
                ),
                kind="pc",
                passed=True,
                cycle=cycle,
                observation_wall_ns=(
                    accept_wall_ns
                ),
            )

            pending_next_pc = (
                event.instruction_index,
                architectural_step.next_pc,
            )

            functional.register_expected(
                ExpectedRetire
                .from_architectural_step(
                    architectural_step
                )
            )

            def observe_coverage():
                events_by_index[
                    event.instruction_index
                ] = event

                l1_hits = (
                    l1_coverage.observe(
                        event
                    )
                )

                for hit in l1_hits:
                    cut_driver.note_intent_consumer(
                        consumer_instruction_id=(
                            hit.consumer_instruction_index
                        ),
                        accepted_prefix=(
                            event.instruction_index
                        ),
                    )

                    coverage.record_l1_intent(
                        hit.bin_id,
                        instruction_id=(
                            hit.consumer_instruction_index
                        ),
                        cycle=cycle,
                        wall_ns=(
                            accept_wall_ns
                        ),
                    )

                    control = (
                        l1_control.check(
                            hit,
                            event,
                            events_by_index,
                        )
                    )

                    outcomes = (
                        l1_validated
                        .register_hit(
                            hit,
                            control_passed=(
                                control.passed
                            ),
                        )
                    )

                    promote_l1_outcomes(
                        outcomes,
                        cycle=cycle,
                        observation_wall_ns=(
                            accept_wall_ns
                        ),
                    )

                    assert control.passed

                l2_hits = (
                    l2_coverage.observe(
                        event
                    )
                )

                for hit in l2_hits:
                    cut_driver.note_intent_consumer(
                        consumer_instruction_id=(
                            hit.consumer_instruction_index
                        ),
                        accepted_prefix=(
                            event.instruction_index
                        ),
                    )

                    producer_event = (
                        events_by_index[
                            hit.producer_instruction_index
                        ]
                    )

                    outcomes = (
                        l2_live.register_hit(
                            hit,
                            producer=(
                                producer_event
                            ),
                            consumer=event,
                            expectation=(
                                expectation
                            ),
                            cycle=cycle,
                            wall_ns=(
                                accept_wall_ns
                            ),
                        )
                    )

                    assert all(
                        outcome.control_passed
                        for outcome in outcomes
                    )

            def snapshot_factory(
                max_intent_consumer_id,
            ):
                return (
                    build_campaign_lifecycle_snapshot(
                        cycle=cycle,
                        accepted=(
                            event.instruction_index
                        ),
                        max_intent_consumer_id=(
                            max_intent_consumer_id
                        ),
                        retire_monitor=(
                            retire_monitor
                        ),
                        functional=(
                            functional
                        ),
                        performance=(
                            performance
                        ),
                        l1_validated=(
                            l1_validated
                        ),
                        l2_validated=(
                            l2_live.checker
                        ),
                    )
                )

            decision = (
                cut_driver
                .complete_accepted_event(
                    instruction_index=(
                        event.instruction_index
                    ),
                    cycle=cycle,
                    adapter_instruction_count=(
                        adapter.instruction_count
                    ),
                    observe_coverage=(
                        observe_coverage
                    ),
                    snapshot_factory=(
                        snapshot_factory
                    ),
                )
            )

            accepted_tag = (
                RetireTag
                .from_execution_event(
                    event
                )
            )

            # Verification-side B/C/D identity advances for the same
            # already-observed rising edge. This creates no DUT edge.
            retire_monitor.advance_pipeline(
                accepted_tag
            )

            if decision.exact_cut:
                cut_cycle = cycle

                assert (
                    event.instruction_index
                    == TARGET
                )

                # --------------------------------------------------
                # Exact kill: no release, refill, drain, or fifth
                # architectural edge is allowed.
                # --------------------------------------------------
                clock_task.kill()

                assert (
                    clock_task.done()
                )

                assert (
                    signal_int(
                        dut.clk,
                        "clk",
                    )
                    == 1
                )

                # Settling time only. No clock owner remains.
                await Timer(
                    2 * CLOCK_NS,
                    units="ns",
                )

                assert (
                    signal_int(
                        dut.clk,
                        "clk",
                    )
                    == 1
                )

                final_snapshot = (
                    cut_driver
                    .finalize_after_clock_stop(
                        adapter_instruction_count=(
                            adapter.instruction_count
                        ),
                        clock_task_done=(
                            clock_task.done()
                        ),
                        clock_is_high=True,
                    )
                )

                break

            stale_event_id = (
                event.instruction_index
                - 3
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

        else:
            # No accepted event at this rising edge, but the
            # verification-side pipeline still advances with a bubble.
            retire_monitor.advance_pipeline(
                None
            )

    # ==========================================================
    # FINAL EXACT-CUT PROOF OBLIGATIONS
    # ==========================================================
    assert final_snapshot is not None
    assert cut_cycle is not None

    assert (
        adapter.instruction_count
        == TARGET
    )

    assert (
        cut_driver.accepted_count
        == TARGET
    )

    assert (
        cut_driver.coverage_observed_count
        == TARGET
    )

    assert (
        coverage.executed_instructions
        == TARGET
    )

    # Valid resident instruction #5 must not become accepted.
    assert (
        adapter.instruction_count
        < len(words)
    )

    assert [
        checkpoint.executed_instructions
        for checkpoint in checkpoints
    ] == [
        2,
        4,
    ]

    assert (
        checkpoints[-1]
        .executed_instructions
        == TARGET
    )

    assert (
        checkpoints[-1].cycle
        == cut_cycle
    )

    assert (
        final_snapshot.accepted
        == TARGET
    )

    assert (
        final_snapshot.cycle
        == cut_cycle
    )

    in_flight = (
        final_snapshot.accepted
        - final_snapshot.retired_checked
    )

    assert in_flight > 0

    assert (
        in_flight
        <= CAMPAIGN_MAX_IN_FLIGHT_DEPTH
    )

    assert (
        final_snapshot.functional_pending
        == in_flight
    )

    assert (
        final_snapshot.performance_pending
        == in_flight
    )

    # Verification-side tag state must also represent a bounded,
    # undrained accepted tail.
    live_stage_ids = tuple(
        instruction_id
        for instruction_id
        in retire_monitor.stage_instruction_ids
        if instruction_id is not None
    )

    assert live_stage_ids

    assert TARGET in live_stage_ids

    assert (
        functional.failed_count
        == 0
    )

    assert (
        performance.failed_count
        == 0
    )

    dut._log.info(
        "W13_COMMON_EXACT_CUT=PASS "
        f"accepted={TARGET} "
        f"retired={final_snapshot.retired_checked} "
        f"in_flight={in_flight} "
        f"checkpoints="
        f"{[c.executed_instructions for c in checkpoints]} "
        f"cut_cycle={cut_cycle} "
        "clock_high=1 "
        "post_cut_edges=0"
    )
