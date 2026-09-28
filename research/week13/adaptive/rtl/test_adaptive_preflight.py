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

from research.week5.impl.commit_scoreboard import (
    StoreObservation,
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
)
from research.week9.coverage_promotion import (
    promote_l1_attribution,
)
from research.week9.validated_attribution import (
    attribute_l1_hit,
)

from research.week10.adaptive.campaign_runner import (
    IMEM_WORD_CAPACITY,
)
from research.week10.adaptive.intra_epoch_feeder import (
    plan_next_capacity_safe_entry,
    refill_threshold_words,
)
from research.week10.adaptive.production_campaign import (
    ProductionCampaignConfig,
    build_production_adaptive_stack,
)
from research.week10.adaptive.wrap_aware_architectural_model import (
    WrapAwareRV32ArchitecturalModel,
)
from research.week10.adaptive.wrap_aware_timing_oracle import (
    WrapAwareMutableTimingOracleV1,
)

# Reuse the already-qualified Week-10 physical patch / pause / resume
# implementation rather than creating another IMEM-control protocol.
from research.week10.rtl.test_adaptive_campaign import (
    patch_stream_entries,
    reset_active_high,
    resume_clock_from_high_to_falling,
)

from research.week13.adaptive.stream_identity import (
    peek_expected_accepted_identity,
)
from research.week13.campaign.cut_driver import (
    CampaignCutDriver,
    CampaignInfrastructureError,
)
from research.week13.campaign.invariant_ledger import (
    CampaignInvariantLedger,
)
from research.week13.campaign.snapshot_adapter import (
    CAMPAIGN_MAX_IN_FLIGHT_DEPTH,
    build_campaign_lifecycle_snapshot,
)


CLOCK_NS = 10

ROOT_SEED = 13001
EPSILON = 0.05
ALPHA = 0.1
Q_FLOOR = 0.05
NOMINAL_BATCH = 500

ACCEPTED_BUDGET = 1000
CHECKPOINT_INTERVAL = 1000

MAX_CYCLES = (
    ACCEPTED_BUDGET * 20
    + 4096
)


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


def signal_int(
    signal,
    name: str,
) -> int:
    try:
        return int(signal.value)
    except (TypeError, ValueError) as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z: "
            f"{signal.value}"
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
            f"expected exactly one {name!r} check, "
            f"got {len(checks)}"
        )

    return (
        checks[0].expected
        == checks[0].observed
    )


@cocotb.test()
async def test_adaptive_common_cut_preflight_1000(
    dut,
):
    """
    Week-13 Adaptive-CGS common-lifecycle preflight.

    This is NOT an official pilot observation.

    Qualifies:
      - frozen production Adaptive generator/runtime;
      - read-only planned-stream prevalidation;
      - full functional/performance checker stack;
      - L1/L2 Intent + Validated;
      - common CampaignCutDriver lifecycle;
      - bounded IMEM streaming/refill;
      - multi-epoch adaptive continuity;
      - exact N=1000 accepted hard cap.
    """

    config = ProductionCampaignConfig(
        seed=ROOT_SEED,
        epsilon=EPSILON,
        alpha=ALPHA,
        q_floor=Q_FLOOR,
        nominal_batch=NOMINAL_BATCH,
        instruction_budget=ACCEPTED_BUDGET,
        checkpoint_interval=CHECKPOINT_INTERVAL,
    )

    assert config.seed == ROOT_SEED
    assert config.epsilon == EPSILON
    assert config.alpha == ALPHA
    assert config.q_floor == Q_FLOOR
    assert config.nominal_batch == NOMINAL_BATCH
    assert config.instruction_budget == ACCEPTED_BUDGET
    assert config.checkpoint_interval == CHECKPOINT_INTERVAL

    # ----------------------------------------------------------
    # Verification interface.
    # ----------------------------------------------------------
    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    await Timer(
        1,
        units="ns",
    )

    # ----------------------------------------------------------
    # Frozen Adaptive production stack.
    # ----------------------------------------------------------
    adaptive_checkpoints = []

    def adaptive_checkpoint_sink(record):
        adaptive_checkpoints.append(record)

    stack = build_production_adaptive_stack(
        config=config,
        checkpoint_sink=(
            adaptive_checkpoint_sink
        ),
    )

    l2_coverage = stack.l2_coverage
    coverage = stack.coverage

    coordinator = stack.coordinator
    planner = stack.planner
    window = stack.window

    checkpoint_bridge = (
        stack.checkpoint_bridge
    )

    # Public path only.
    l2_live = coordinator.live_coordinator

    assert (
        l2_live.checker
        is coordinator.live_coordinator.checker
    )

    # ----------------------------------------------------------
    # Begin epoch 0.
    # ----------------------------------------------------------
    current_start = planner.begin_epoch()

    current_epoch_index = (
        current_start.decision.epoch_index
    )

    assert current_epoch_index == 0

    checkpoint_bridge.begin_epoch(
        current_epoch_index
    )

    current_boundary = (
        planner.active_boundary_delimiter
    )

    assert current_boundary is not None
    assert current_boundary.epoch_index == 0

    accepted_before_epoch = (
        window.accepted_count
    )

    # Initial EBD_0.
    (
        initial_fragment,
        initial_words,
    ) = await patch_stream_entries(
        dut,
        entries=(current_boundary,),
        window=window,
        timing_oracle=None,
    )

    assert initial_words == 1

    timing_oracle = (
        WrapAwareMutableTimingOracleV1(
            initial_fragment
        )
    )

    assert (
        timing_oracle.resident_word_count
        == window.used_words
    )

    current_planned_executed = None

    async def fill_available_capacity():
        """
        Frozen production bounded filler.

        Ordinary complete epochs preplan and patch EBD_{t+1}.
        The final budget-crossing epoch must never create an EBD
        whose architectural instruction index exceeds Nmax.

        Returns the exact planned executed count if planning
        became complete during this refill, otherwise None.
        """
        final_planned = None

        while planner.active:
            entry = (
                plan_next_capacity_safe_entry(
                    planner,
                    free_words=window.free_words,
                    preseed_next_boundary=True,
                    max_executed_instruction_index=(
                        ACCEPTED_BUDGET
                    ),
                )
            )

            if entry is None:
                final_epoch_has_no_legal_next_ebd = (
                    planner.epoch_plan_complete
                    and (
                        planner
                        .next_executed_instruction_index
                        > ACCEPTED_BUDGET
                    )
                )

                if final_epoch_has_no_legal_next_ebd:
                    final_planned = (
                        planner
                        .planned_epoch_executed_instructions
                    )

                    assert (
                        final_planned
                        >= config.nominal_batch
                    )

                    planner.close_planning_epoch()

                    assert not planner.active

                break

            await patch_stream_entries(
                dut,
                entries=(entry,),
                window=window,
                timing_oracle=timing_oracle,
            )

            if (
                entry.stream_entry_key[0]
                == "EBD"
            ):
                assert (
                    entry
                    .first_executed_instruction_index
                    <= ACCEPTED_BUDGET
                )

            pending_boundary = (
                planner
                .pending_boundary_delimiter
            )

            if (
                planner.epoch_plan_complete
                and pending_boundary is not None
                and (
                    entry.stream_entry_key
                    == pending_boundary.stream_entry_key
                )
            ):
                final_planned = (
                    planner
                    .planned_epoch_executed_instructions
                )

                assert (
                    final_planned
                    >= config.nominal_batch
                )

                planner.close_planning_epoch()

                assert not planner.active

                break

        return final_planned

    closed_count = (
        await fill_available_capacity()
    )

    if closed_count is not None:
        current_planned_executed = (
            closed_count
        )

    # ----------------------------------------------------------
    # Common Week-13 checker stack.
    # ----------------------------------------------------------
    adapter = ExecutionEventAdapter()
    retire_monitor = RetireMonitor()

    architectural_model = (
        WrapAwareRV32ArchitecturalModel()
    )

    functional = (
        StreamingFunctionalScoreboard()
    )

    performance = (
        StreamingPerformanceMonitor()
    )

    l1_coverage = L1CoverageCollector()

    l1_control = (
        L1ControlRealizationChecker()
    )

    l1_validated = (
        L1ValidatedCoverageCollector()
    )

    ledger = CampaignInvariantLedger(
        hard_cap=ACCEPTED_BUDGET,
        max_in_flight_depth=(
            CAMPAIGN_MAX_IN_FLIGHT_DEPTH
        ),
    )

    cut_driver = CampaignCutDriver(
        hard_cap=ACCEPTED_BUDGET,
        coverage=coverage,
        ledger=ledger,
    )

    events_by_index = {}
    pending_next_pc = None

    final_snapshot = None
    cut_cycle = None

    released_entry_count = 0
    refill_pause_count = 0
    epoch_completion_count = 0

    stall_cycle_count = 0
    flush_cycle_count = 0

    max_resident_words = (
        window.used_words
    )

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

        coordinator.record_architectural_result(
            instruction_id=instruction_id,
            kind=kind,
            passed=passed,
            cycle=cycle,
            wall_ns=observation_wall_ns,
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

    cycle = 0
    pre_edge_ready = False

    while True:
        if cycle >= MAX_CYCLES:
            clock_task.kill()

            raise AssertionError(
                "Adaptive Week13 preflight "
                "exceeded cycle budget"
            )

        if not pre_edge_ready:
            await FallingEdge(
                dut.clk
            )

            await ReadOnly()
        else:
            pre_edge_ready = False

        cycle += 1

        cut_driver.note_clock_edge(
            cycle=cycle,
            edge="falling",
        )

        # ======================================================
        # FALLING: store + retire.
        # ======================================================
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

            assert functional_result.passed
            assert performance_result.passed

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
            stall_cycle_count += 1

        if flush:
            flush_cycle_count += 1

        pending = adapter.observe_pre_edge(
            PreEdgeSnapshot(
                cycle=cycle,
                reset=bool(
                    signal_int(
                        dut.reset,
                        "reset",
                    )
                ),
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

        # ======================================================
        # RISING.
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
        released_for_event = None

        if pending is None:
            retire_monitor.advance_pipeline(
                None
            )
            continue

        assert (
            adapter.instruction_count
            < ACCEPTED_BUDGET
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

        # ======================================================
        # READ-ONLY PLANNED-STREAM PREVALIDATION.
        # ======================================================
        expected_identity = (
            peek_expected_accepted_identity(
                window
            )
        )

        if (
            event.instruction_index
            != expected_identity
            .instruction_index
            or event.pc
            != expected_identity.pc
            or event.instruction
            != expected_identity.instruction
        ):
            clock_task.kill()

            raise AssertionError(
                "VALID_DUT_FAILURE_TERMINAL: "
                f"id={event.instruction_index}, "
                f"expected_id="
                f"{expected_identity.instruction_index}, "
                f"pc=0x{event.pc:03x}/"
                f"0x{expected_identity.pc:03x}, "
                f"instr=0x{event.instruction:08x}/"
                f"0x{expected_identity.instruction:08x}"
            )

        logical_owner = (
            timing_oracle
            .logical_owner_for_pc(
                event.pc
            )
        )

        if (
            logical_owner
            != expected_identity
            .logical_word_index
        ):
            raise CampaignInfrastructureError(
                "adaptive runtime/timing ownership "
                "mismatch"
            )

        # ======================================================
        # TIMING / ARCHITECTURE EXPECTATIONS.
        # ======================================================
        expectation = (
            timing_oracle.observe_accept(
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

            coordinator.record_successor_pc(
                predecessor_instruction_id=(
                    predecessor_id
                ),
                expected_next_pc=(
                    predecessor_next_pc
                ),
                successor=event,
                cycle=cycle,
                wall_ns=accept_wall_ns,
            )

        architectural_step = (
            architectural_model.step(
                event
            )
        )

        if not architectural_step.pc_match:
            raise CampaignInfrastructureError(
                "prevalidated adaptive stream "
                "and architectural model disagree"
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

        # ======================================================
        # AUTHORITATIVE COVERAGE OBSERVERS.
        # ======================================================
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
                        hit
                        .consumer_instruction_index
                    ),
                    accepted_prefix=(
                        event.instruction_index
                    ),
                )

                coverage.record_l1_intent(
                    hit.bin_id,
                    instruction_id=(
                        hit
                        .consumer_instruction_index
                    ),
                    cycle=cycle,
                    wall_ns=accept_wall_ns,
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
                        hit
                        .consumer_instruction_index
                    ),
                    accepted_prefix=(
                        event.instruction_index
                    ),
                )

                producer = events_by_index[
                    hit.producer_instruction_index
                ]

                outcomes = (
                    coordinator.register_l2_hit(
                        hit,
                        producer=producer,
                        consumer=event,
                        expectation=expectation,
                        cycle=cycle,
                        wall_ns=accept_wall_ns,
                    )
                )

                assert all(
                    outcome.control_passed
                    for outcome in outcomes
                )

        # ======================================================
        # METHOD-SPECIFIC POST-CUT RUNTIME RELEASE.
        # ======================================================
        def after_post_instruction_cut():
            nonlocal released_for_event
            nonlocal released_entry_count

            released_for_event = (
                window
                .finalize_accepted_event(
                    event
                )
            )

            l1_validated.prune(
                latest_instruction_index=(
                    event.instruction_index
                )
            )

            if released_for_event is None:
                return

            released_entry_count += 1

            released_block = (
                released_for_event.block
            )

            timing_oracle.release_logical_words(
                first_logical_word_index=(
                    released_block
                    .logical_word_start
                ),
                word_count=(
                    released_block
                    .image_word_count
                ),
            )

            if (
                timing_oracle
                .resident_word_count
                != window.used_words
            ):
                raise CampaignInfrastructureError(
                    "adaptive runtime/timing "
                    "release mismatch"
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
                    functional=functional,
                    performance=performance,
                    l1_validated=(
                        l1_validated
                    ),
                    l2_validated=(
                        coordinator
                        .live_coordinator
                        .checker
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
                after_post_instruction_cut=(
                    after_post_instruction_cut
                ),
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

        # Evidence history is no longer needed after this
        # event's L1/L2 observers have completed.
        stale_event_id = (
            event.instruction_index - 3
        )

        if stale_event_id > 0:
            events_by_index.pop(
                stale_event_id,
                None,
            )

        # ======================================================
        # EXACT CUT — PRIORITY OVER REFILL / EPOCH TRANSITION.
        # ======================================================
        if decision.exact_cut:
            cut_cycle = cycle

            clock_task.kill()

            assert clock_task.done()

            assert (
                signal_int(
                    dut.clk,
                    "clk",
                )
                == 1
            )

            await Timer(
                1,
                units="ns",
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

            if (
                window.pending_block_count
                > 0
            ):
                discarded = (
                    window
                    .discard_unexecuted_suffix(
                        last_executed_instruction_index=(
                            ACCEPTED_BUDGET
                        )
                    )
                )

                timing_oracle.release_logical_words(
                    first_logical_word_index=(
                        discarded
                        .first_logical_word_index
                    ),
                    word_count=(
                        discarded
                        .reclaimed_resident_word_count
                    ),
                )

            assert (
                window.accepted_count
                == ACCEPTED_BUDGET
            )

            assert (
                coverage.executed_instructions
                == ACCEPTED_BUDGET
            )

            assert (
                window.pending_block_count
                == 0
            )

            assert window.used_words == 0

            assert (
                timing_oracle
                .resident_word_count
                == 0
            )

            assert (
                coordinator
                .pending_attribution_witness_count
                == 0
            )

            planner.terminate_campaign_planning()

            assert planner.campaign_terminated
            assert not planner.active

            actual_final_epoch = (
                window.accepted_count
                - accepted_before_epoch
            )

            assert actual_final_epoch > 0

            coordinator.finish_epoch(
                actual_executed_instructions=(
                    actual_final_epoch
                )
            )

            checkpoint_bridge.finish_epoch(
                current_epoch_index
            )

            epoch_completion_count += 1

            break

        # ======================================================
        # ORDINARY EPOCH COMPLETION.
        # ======================================================
        accepted_this_epoch = (
            window.accepted_count
            - accepted_before_epoch
        )

        if (
            current_planned_executed
            is not None
            and accepted_this_epoch
            == current_planned_executed
        ):
            coordinator.finish_epoch(
                actual_executed_instructions=(
                    accepted_this_epoch
                )
            )

            checkpoint_bridge.finish_epoch(
                current_epoch_index
            )

            epoch_completion_count += 1

            pending_boundary = (
                planner
                .pending_boundary_delimiter
            )

            assert (
                pending_boundary
                is not None
            )

            # Freeze HIGH before activating/patching
            # the next adaptive epoch.
            clock_task.kill()

            assert clock_task.done()

            await Timer(
                1,
                units="ns",
            )

            current_start = (
                planner.begin_epoch()
            )

            current_epoch_index = (
                current_start
                .decision
                .epoch_index
            )

            assert (
                current_epoch_index
                == epoch_completion_count
            )

            checkpoint_bridge.begin_epoch(
                current_epoch_index
            )

            current_boundary = (
                planner
                .active_boundary_delimiter
            )

            assert (
                current_boundary
                is not None
            )

            assert (
                current_boundary
                .stream_entry_key
                == pending_boundary
                .stream_entry_key
            )

            accepted_before_epoch = (
                window.accepted_count
            )

            current_planned_executed = None

            closed_count = (
                await fill_available_capacity()
            )

            if closed_count is not None:
                current_planned_executed = (
                    closed_count
                )

            max_resident_words = max(
                max_resident_words,
                window.used_words,
            )

            clock_task = (
                await
                resume_clock_from_high_to_falling(
                    dut,
                    clock,
                )
            )

            pre_edge_ready = True
            continue

        # ======================================================
        # BOUNDED INTRA-EPOCH REFILL.
        # ======================================================
        if (
            released_for_event is not None
            and planner.active
            and (
                window.free_words
                >= refill_threshold_words(
                    preseed_next_boundary=True
                )
            )
        ):
            clock_task.kill()

            assert clock_task.done()

            await Timer(
                1,
                units="ns",
            )

            closed_count = (
                await fill_available_capacity()
            )

            refill_pause_count += 1

            if closed_count is not None:
                if (
                    current_planned_executed
                    is not None
                ):
                    raise CampaignInfrastructureError(
                        "adaptive epoch planning "
                        "closed more than once"
                    )

                current_planned_executed = (
                    closed_count
                )

            max_resident_words = max(
                max_resident_words,
                window.used_words,
            )

            assert (
                max_resident_words
                <= IMEM_WORD_CAPACITY
            )

            clock_task = (
                await
                resume_clock_from_high_to_falling(
                    dut,
                    clock,
                )
            )

            pre_edge_ready = True

    # ==========================================================
    # FINAL PREFLIGHT OBLIGATIONS.
    # ==========================================================
    assert final_snapshot is not None
    assert cut_cycle is not None

    assert (
        adapter.instruction_count
        == ACCEPTED_BUDGET
    )

    assert (
        window.accepted_count
        == ACCEPTED_BUDGET
    )

    assert (
        cut_driver.accepted_count
        == ACCEPTED_BUDGET
    )

    assert (
        cut_driver.coverage_observed_count
        == ACCEPTED_BUDGET
    )

    assert (
        coverage.executed_instructions
        == ACCEPTED_BUDGET
    )

    assert (
        max_resident_words
        <= IMEM_WORD_CAPACITY
    )

    assert released_entry_count > 0
    assert refill_pause_count > 0
    assert epoch_completion_count >= 2

    in_flight = (
        final_snapshot.accepted
        - final_snapshot.retired_checked
    )

    assert (
        0
        <= in_flight
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

    assert functional.failed_count == 0
    assert performance.failed_count == 0

    assert (
        performance.total_excess_cycles
        == 0
    )

    assert (
        coordinator
        .pending_attribution_witness_count
        == 0
    )

    l1_intent_count = sum(
        state.intent_seen
        for state
        in coverage.l1_state.values()
    )

    l1_validated_count = sum(
        state.validated_seen
        for state
        in coverage.l1_state.values()
    )

    l2_intent_count = sum(
        state.intent_seen
        for state
        in coverage.l2_state.values()
    )

    l2_validated_count = sum(
        state.validated_seen
        for state
        in coverage.l2_state.values()
    )

    dut._log.info(
        "W13_ADAPTIVE_PREFLIGHT=PASS "
        f"seed={ROOT_SEED} "
        f"epsilon={EPSILON:.2f} "
        f"alpha={ALPHA:.1f} "
        f"batch={NOMINAL_BATCH} "
        f"accepted={ACCEPTED_BUDGET} "
        f"retired="
        f"{final_snapshot.retired_checked} "
        f"in_flight={in_flight} "
        f"cycles={cycle} "
        f"stalls={stall_cycle_count} "
        f"flushes={flush_cycle_count} "
        f"epochs={epoch_completion_count} "
        f"refills={refill_pause_count} "
        f"max_resident_words="
        f"{max_resident_words} "
        f"l1_intent={l1_intent_count} "
        f"l1_validated={l1_validated_count} "
        f"l2_intent={l2_intent_count} "
        f"l2_validated={l2_validated_count}"
    )
