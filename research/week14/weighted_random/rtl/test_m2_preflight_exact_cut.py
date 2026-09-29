from __future__ import annotations

import time
from collections import Counter

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
from research.week5.impl.coverage_model import (
    L2CoverageCollector,
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
from research.week9.coverage_collector import (
    CoverageCollector,
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
from research.week10.adaptive.wrap_aware_architectural_model import (
    WrapAwareRV32ArchitecturalModel,
)
from research.week10.adaptive.wrap_aware_timing_oracle import (
    WrapAwareMutableTimingOracleV1,
)
from research.week10.l2_live_coordinator import (
    L2LiveCoordinator,
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
from research.week13.pure_random.runtime_stream import (
    PureRandomRuntimeWindow,
    PureRandomStreamExecutionMismatch,
    physical_pc_for_logical_word,
)
from research.week14.weighted_random.runtime_adapter import (
    build_weighted_runtime_entries,
)
from research.week14.weighted_random.static_generator import (
    generate_weighted_random_plan,
)


CLOCK_NS = 10

ROOT_SEED = 14001
ACCEPTED_BUDGET = 1000
CHECKPOINT_INTERVAL = 1000

EXPECTED_PLAN_HASH = (
    "3b23d6e4887e305100542416c77f9399"
    "4b229c9f9dab91ac4c0ac9f86465d2c9"
)

EXPECTED_BLOCK_COUNT = 405
EXPECTED_IMAGE_WORDS = 1048
EXPECTED_LAST_GENERATION = 8

EXPECTED_ARMS = {
    "A0": 54,
    "A1": 42,
    "A2": 56,
    "A3": 42,
    "A4": 27,
    "A5": 60,
    "A6": 50,
    "A7": 24,
    "A8": 21,
    "A9": 29,
}

REFILL_THRESHOLD_WORDS = 4

MAX_CYCLES = (
    ACCEPTED_BUDGET
    * 16
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
    except ValueError as exc:
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
            f"instruction_id="
            f"{result.instruction_id}"
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
    if address % 4 != 0:
        raise ValueError(
            "IMEM patch address must be aligned"
        )

    if not 0 <= address <= 508:
        raise ValueError(
            "IMEM patch address outside "
            "9-bit executable window"
        )

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


async def resume_clock_from_high_to_falling(
    dut,
    clock,
):
    assert signal_int(
        dut.clk,
        "clk",
    ) == 1

    async def wait_for_falling():
        await FallingEdge(dut.clk)

    waiter = cocotb.start_soon(
        wait_for_falling()
    )

    await Timer(1, units="ns")

    clock_task = cocotb.start_soon(
        clock.start(
            start_high=False
        )
    )

    await waiter
    await ReadOnly()

    assert signal_int(
        dut.clk,
        "clk",
    ) == 0

    return clock_task


def resident_physical_owners(
    window: PureRandomRuntimeWindow,
) -> dict[int, int]:
    owners: dict[int, int] = {}

    for entry in window.pending_entries:
        for offset, physical_pc in enumerate(
            entry.physical_word_addresses
        ):
            logical_word = (
                entry.logical_word_start
                + offset
            )

            if physical_pc in owners:
                raise AssertionError(
                    "two live logical words alias "
                    "one physical IMEM slot"
                )

            owners[
                physical_pc
            ] = logical_word

    assert (
        len(owners)
        == window.used_words
    )

    return owners


def build_resident_fragment(
    entries,
) -> dict[int, int]:
    fragment: dict[int, int] = {}

    for entry in entries:
        for address, word in zip(
            entry.physical_word_addresses,
            entry.image_words,
            strict=True,
        ):
            if address in fragment:
                raise AssertionError(
                    "resident fragment contains "
                    "physical alias"
                )

            fragment[address] = word

    return fragment


@cocotb.test()
async def test_m2_preflight_exact_cut_1000(
    dut,
):
    # ==========================================================
    # FROZEN KNOWN-ANSWER PLAN
    # ==========================================================
    plan = generate_weighted_random_plan(
        ROOT_SEED,
        ACCEPTED_BUDGET,
    )

    entries = build_weighted_runtime_entries(
        plan
    )

    total_image_words = sum(
        entry.image_word_count
        for entry in entries
    )

    arms = Counter(
        block.arm_id.value
        for block in plan.blocks
    )

    assert (
        plan.accepted_instruction_count
        == ACCEPTED_BUDGET
    )

    assert (
        plan.plan_hash
        == EXPECTED_PLAN_HASH
    )

    assert (
        len(plan.blocks)
        == EXPECTED_BLOCK_COUNT
    )

    assert (
        total_image_words
        == EXPECTED_IMAGE_WORDS
    )

    # M2 N=1000 is frozen at a complete template boundary.
    # No synthetic final_expected_pc field is introduced:
    # exact accepted PC/word identity is checked by the
    # frozen runtime tracker for every accepted event.
    assert not plan.blocks[-1].is_partial

    assert (
        dict(sorted(arms.items()))
        == EXPECTED_ARMS
    )

    accepted_logical_words = tuple(
        entry.logical_word_start + offset
        for entry in entries
        for offset
        in entry.planned_accepted_word_offsets
    )

    expected_accepted_words = tuple(
        entry.image_words[offset]
        for entry in entries
        for offset
        in entry.planned_accepted_word_offsets
    )

    expected_accepted_pcs = tuple(
        physical_pc_for_logical_word(
            logical_word
        )
        for logical_word
        in accepted_logical_words
    )

    expected_accepted_arms = tuple(
        entry.planned.arm_id.value
        for entry in entries
        for _offset
        in entry.planned_accepted_word_offsets
    )

    expected_accepted_blocks = tuple(
        entry.block_index
        for entry in entries
        for _offset
        in entry.planned_accepted_word_offsets
    )

    assert (
        len(accepted_logical_words)
        == ACCEPTED_BUDGET
    )

    assert (
        len(expected_accepted_words)
        == ACCEPTED_BUDGET
    )

    assert (
        accepted_logical_words[-1]
        // IMEM_WORD_CAPACITY
        == EXPECTED_LAST_GENERATION
    )

    # ==========================================================
    # STATIC DUT INTERFACE
    # ==========================================================
    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    await Timer(1, units="ns")

    window = PureRandomRuntimeWindow()

    next_entry_index = 0

    patched_word_count = 0
    patch_reuse_count = 0

    patched_physical_slots: set[int] = set()

    max_resident_words = 0

    timing_oracle = None

    async def fill_available_capacity():
        nonlocal next_entry_index
        nonlocal patched_word_count
        nonlocal patch_reuse_count
        nonlocal max_resident_words
        nonlocal timing_oracle

        patched_entries_now = 0
        patched_words_now = 0

        while (
            next_entry_index
            < len(entries)
        ):
            entry = entries[
                next_entry_index
            ]

            if not window.can_commit(
                entry
            ):
                break

            runtime_owners = (
                resident_physical_owners(
                    window
                )
            )

            if timing_oracle is not None:
                assert (
                    timing_oracle
                    .next_append_logical_word_index
                    == entry.logical_word_start
                )

            for offset, physical_pc in enumerate(
                entry.physical_word_addresses
            ):
                logical_word = (
                    entry.logical_word_start
                    + offset
                )

                assert (
                    physical_pc
                    not in runtime_owners
                )

                assert (
                    physical_pc
                    == physical_pc_for_logical_word(
                        logical_word
                    )
                )

                if timing_oracle is not None:
                    assert (
                        timing_oracle
                        .logical_owner_for_pc(
                            physical_pc
                        )
                        is None
                    )

            # Physical image first.
            for physical_pc, word in zip(
                entry.physical_word_addresses,
                entry.image_words,
                strict=True,
            ):
                if (
                    physical_pc
                    in patched_physical_slots
                ):
                    patch_reuse_count += 1

                await patch_word(
                    dut,
                    address=physical_pc,
                    word=word,
                )

                patched_physical_slots.add(
                    physical_pc
                )

                patched_word_count += 1
                patched_words_now += 1

            # Runtime ownership follows complete physical patch.
            window.commit_patched_entry(
                entry
            )

            # Timing ownership follows successful runtime commit.
            if timing_oracle is not None:
                fragment = {
                    address: word
                    for address, word in zip(
                        entry.physical_word_addresses,
                        entry.image_words,
                        strict=True,
                    )
                }

                timing_oracle.append_program(
                    fragment,
                    first_logical_word_index=(
                        entry.logical_word_start
                    ),
                )

                assert (
                    timing_oracle
                    .resident_word_count
                    == window.used_words
                )

            next_entry_index += 1
            patched_entries_now += 1

            max_resident_words = max(
                max_resident_words,
                window.used_words,
            )

            assert (
                window.used_words
                <= IMEM_WORD_CAPACITY
            )

        return (
            patched_entries_now,
            patched_words_now,
        )

    # ==========================================================
    # INITIAL GREEDY FILL — CLOCK STOPPED
    # ==========================================================
    (
        initial_entries,
        initial_words,
    ) = await fill_available_capacity()

    assert initial_entries > 0
    assert initial_words > 0

    assert (
        next_entry_index
        < len(entries)
    )

    initial_fragment = (
        build_resident_fragment(
            window.pending_entries
        )
    )

    timing_oracle = (
        WrapAwareMutableTimingOracleV1(
            initial_fragment
        )
    )

    assert (
        timing_oracle.resident_word_count
        == window.used_words
    )

    assert (
        timing_oracle
        .next_append_logical_word_index
        == window.used_words
    )

    # ==========================================================
    # COMMON CHECKER / COVERAGE STACK
    # ==========================================================
    adapter = ExecutionEventAdapter()
    retire_monitor = RetireMonitor()

    architectural_model = (
        WrapAwareRV32ArchitecturalModel()
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
        checkpoint_interval=(
            CHECKPOINT_INTERVAL
        ),
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

    cycle = 0

    stall_cycle_count = 0
    flush_cycle_count = 0

    refill_pause_count = 0
    released_entry_count = 0

    observed_generations: set[int] = set()
    max_executed_logical_word = -1

    first_functional_failure = None
    first_performance_failure = None
    first_accept_timing_divergence = None

    functional_failure_diagnostics = []
    performance_failure_diagnostics = []

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
            instruction_id=instruction_id,
            kind=kind,
            passed=passed,
            cycle=cycle,
            wall_ns=observation_wall_ns,
        )

    # ==========================================================
    # ONE CLOCK OWNER
    # ==========================================================
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

    assert signal_int(
        dut.reset,
        "reset",
    ) == 0

    pre_edge_ready = False

    final_snapshot = None
    cut_cycle = None

    while True:
        if cycle >= MAX_CYCLES:
            clock_task.kill()

            raise AssertionError(
                "M1 preflight exceeded bounded "
                "cycle budget"
            )

        # ======================================================
        # FALLING EDGE
        # ======================================================
        if pre_edge_ready:
            pre_edge_ready = False
        else:
            await FallingEdge(
                dut.clk
            )

            await ReadOnly()

        cycle += 1

        cut_driver.note_clock_edge(
            cycle=cycle,
            edge="falling",
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
            stall_cycle_count += 1

        if flush:
            flush_cycle_count += 1

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

            if not functional_result.passed:
                failed_id = (
                    retired.instruction_id
                )

                mismatches = tuple(
                    (
                        check.name,
                        check.expected,
                        check.observed,
                    )
                    for check
                    in functional_result.checks
                    if (
                        check.expected
                        != check.observed
                    )
                )

                diagnostic = {
                    "instruction_id": failed_id,
                    "block": (
                        expected_accepted_blocks[
                            failed_id - 1
                        ]
                    ),
                    "arm": (
                        expected_accepted_arms[
                            failed_id - 1
                        ]
                    ),
                    "pc": (
                        expected_accepted_pcs[
                            failed_id - 1
                        ]
                    ),
                    "word": (
                        expected_accepted_words[
                            failed_id - 1
                        ]
                    ),
                    "retire_regwrite": (
                        retired.regwrite
                    ),
                    "retire_rd": retired.rd,
                    "retire_wdata": (
                        retired.wdata
                    ),
                    "mismatches": mismatches,
                }

                if (
                    len(
                        functional_failure_diagnostics
                    )
                    < 8
                ):
                    functional_failure_diagnostics.append(
                        diagnostic
                    )

                dut._log.error(
                    "W14_M2_FUNCTIONAL_FAILURE "
                    f"{diagnostic}"
                )

                if (
                    first_functional_failure
                    is None
                ):
                    first_functional_failure = (
                        failed_id
                    )

            if not performance_result.passed:
                timing_diagnostic = {
                    "instruction_id": (
                        retired.instruction_id
                    ),
                    "expected_retire": (
                        performance_result
                        .expected_retire_cycle
                    ),
                    "observed_retire": (
                        performance_result
                        .observed_retire_cycle
                    ),
                    "delta": (
                        performance_result
                        .delta_cycles
                    ),
                }

                if (
                    len(
                        performance_failure_diagnostics
                    )
                    < 8
                ):
                    performance_failure_diagnostics.append(
                        timing_diagnostic
                    )

                    dut._log.error(
                        "W14_M2_PERFORMANCE_FAILURE "
                        f"{timing_diagnostic}"
                    )

                if (
                    first_performance_failure
                    is None
                ):
                    first_performance_failure = (
                        retired.instruction_id
                    )

        pending = (
            adapter.observe_pre_edge(
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
            <= ACCEPTED_BUDGET
        )

        # ------------------------------------------------------
        # TERMINAL STREAM-IDENTITY CONTRACT
        #
        # Validate before any timing / architectural / coverage
        # observer so an unattributable event never contaminates
        # fixed-stream evidence.
        # ------------------------------------------------------
        plan_offset = (
            event.instruction_index
            - 1
        )

        expected_pc = (
            expected_accepted_pcs[
                plan_offset
            ]
        )

        expected_word = (
            expected_accepted_words[
                plan_offset
            ]
        )

        if (
            event.pc != expected_pc
            or event.instruction
            != expected_word
        ):
            clock_task.kill()

            await Timer(
                1,
                units="ns",
            )

            raise AssertionError(
                "VALID_DUT_FAILURE_TERMINAL: "
                f"instruction_index="
                f"{event.instruction_index}, "
                f"expected_pc="
                f"0x{expected_pc:03x}, "
                f"observed_pc="
                f"0x{event.pc:03x}, "
                f"expected_word="
                f"0x{expected_word:08x}, "
                f"observed_word="
                f"0x{event.instruction:08x}"
            )

        logical_word = (
            accepted_logical_words[
                plan_offset
            ]
        )

        logical_owner = (
            timing_oracle
            .logical_owner_for_pc(
                event.pc
            )
        )

        if logical_owner != logical_word:
            clock_task.kill()

            raise CampaignInfrastructureError(
                "runtime/timing ownership "
                "corruption: "
                f"instruction="
                f"{event.instruction_index}, "
                f"expected_logical="
                f"{logical_word}, "
                f"timing_owner="
                f"{logical_owner}"
            )

        generation = (
            logical_word
            // IMEM_WORD_CAPACITY
        )

        observed_generations.add(
            generation
        )

        max_executed_logical_word = max(
            max_executed_logical_word,
            logical_word,
        )

        expectation = (
            timing_oracle
            .observe_accept(
                event
            )
        )

        accept_delta = (
            event.cycle
            - expectation.accept_cycle
        )

        if (
            accept_delta != 0
            and first_accept_timing_divergence
            is None
        ):
            first_accept_timing_divergence = {
                "instruction_id": (
                    event.instruction_index
                ),
                "mnemonic": (
                    expectation.mnemonic
                ),
                "word": (
                    event.instruction
                ),
                "expected_accept_cycle": (
                    expectation.accept_cycle
                ),
                "observed_accept_cycle": (
                    event.cycle
                ),
                "delta": accept_delta,
                "expected_stalls": (
                    expectation
                    .stall_cycles_before_accept
                ),
                "observed_stalls": (
                    event
                    .stall_cycles_before_accept
                ),
            }

            dut._log.error(
                "W14_M2_ACCEPT_TIMING_DIVERGENCE "
                f"{first_accept_timing_divergence}"
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
                wall_ns=accept_wall_ns,
            )

        architectural_step = (
            architectural_model.step(
                event
            )
        )

        if not architectural_step.pc_match:
            clock_task.kill()

            raise CampaignInfrastructureError(
                "frozen M1 plan and "
                "architectural model disagree: "
                f"instruction="
                f"{event.instruction_index}"
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

                l2_live.register_hit(
                    hit,
                    producer=producer_event,
                    consumer=event,
                    expectation=expectation,
                    cycle=cycle,
                    wall_ns=accept_wall_ns,
                )

        completed = None

        def after_post_instruction_cut():
            nonlocal completed
            nonlocal released_entry_count

            try:
                completed = (
                    window
                    .finalize_accepted_event(
                        event
                    )
                )
            except (
                PureRandomStreamExecutionMismatch
            ) as exc:
                raise CampaignInfrastructureError(
                    "prevalidated M2 event "
                    "failed runtime tracker: "
                    f"{exc}"
                ) from exc

            if (
                window.accepted_count
                != event.instruction_index
            ):
                raise CampaignInfrastructureError(
                    "runtime accepted count "
                    "does not match event"
                )

            if completed is not None:
                released_entry_count += 1

                released_entry = (
                    completed.entry
                )

                timing_oracle.release_logical_words(
                    first_logical_word_index=(
                        released_entry
                        .logical_word_start
                    ),
                    word_count=(
                        released_entry
                        .image_word_count
                    ),
                )

                if (
                    timing_oracle
                    .resident_word_count
                    != window.used_words
                ):
                    raise CampaignInfrastructureError(
                        "runtime/timing release "
                        "occupancy mismatch"
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
                after_post_instruction_cut=(
                    after_post_instruction_cut
                ),
            )
        )

        retire_monitor.advance_pipeline(
            RetireTag
            .from_execution_event(
                event
            )
        )

        # ======================================================
        # EXACT-N TERMINATION — NO REFILL HAS PRIORITY
        # ======================================================
        if decision.exact_cut:
            cut_cycle = cycle

            clock_task.kill()

            assert clock_task.done()

            assert signal_int(
                dut.clk,
                "clk",
            ) == 1

            await Timer(
                1,
                units="ns",
            )

            assert signal_int(
                dut.clk,
                "clk",
            ) == 1

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

            assert (
                next_entry_index
                == len(entries)
            )

            final_plan_block = (
                plan.blocks[-1]
            )

            assert not final_plan_block.is_partial

            assert (
                len(
                    final_plan_block
                    .accepted_word_indices
                )
                == final_plan_block
                .full_expected_instruction_count
            )

            # M2 seed=14001/N=1000 terminates exactly
            # at the end of the final template. The
            # post-instruction runtime hook must therefore
            # have completed and released that final entry.
            assert (
                window.pending_entry_count
                == 0
            )

            assert window.used_words == 0

            assert (
                timing_oracle
                .resident_word_count
                == 0
            )

            assert (
                timing_oracle
                .next_release_logical_word_index
                == EXPECTED_IMAGE_WORDS
            )

            assert (
                timing_oracle
                .next_append_logical_word_index
                == EXPECTED_IMAGE_WORDS
            )

            break

        # ======================================================
        # BOUNDED EVIDENCE PRUNING
        # ======================================================
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

        # ======================================================
        # CAPACITY-SAFE REFILL
        # ======================================================
        if (
            completed is not None
            and next_entry_index
            < len(entries)
            and window.free_words
            >= REFILL_THRESHOLD_WORDS
        ):
            clock_task.kill()

            assert clock_task.done()

            assert signal_int(
                dut.clk,
                "clk",
            ) == 1

            await Timer(
                1,
                units="ns",
            )

            (
                patched_entries_now,
                patched_words_now,
            ) = await fill_available_capacity()

            assert patched_entries_now > 0
            assert patched_words_now > 0

            refill_pause_count += 1

            assert (
                timing_oracle
                .resident_word_count
                == window.used_words
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
    # FINAL PREFLIGHT OBLIGATIONS
    # ==========================================================
    elapsed_ns = wall_ns()

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
        coverage.executed_instructions
        == ACCEPTED_BUDGET
    )

    assert (
        cut_driver.coverage_observed_count
        == ACCEPTED_BUDGET
    )

    assert (
        patched_word_count
        == EXPECTED_IMAGE_WORDS
    )

    assert refill_pause_count > 0
    assert patch_reuse_count > 0

    assert (
        max_resident_words
        <= IMEM_WORD_CAPACITY
    )

    assert (
        observed_generations
        == set(
            range(
                EXPECTED_LAST_GENERATION
                + 1
            )
        )
    )

    assert (
        max_executed_logical_word
        // IMEM_WORD_CAPACITY
        == EXPECTED_LAST_GENERATION
    )

    assert [
        checkpoint.executed_instructions
        for checkpoint in checkpoints
    ] == [
        ACCEPTED_BUDGET,
    ]

    assert (
        checkpoints[-1].cycle
        == cut_cycle
    )

    in_flight = (
        final_snapshot.accepted
        - final_snapshot.retired_checked
    )

    assert 1 <= in_flight <= (
        CAMPAIGN_MAX_IN_FLIGHT_DEPTH
    )

    assert (
        final_snapshot
        .functional_pending
        == in_flight
    )

    assert (
        final_snapshot
        .performance_pending
        == in_flight
    )

    # Nonterminal checker failures are allowed to run through N,
    # but this qualification gate requires the canonical Revision-B
    # preflight itself to remain clean.
    if functional.failed_count != 0:
        dut._log.error(
            "W14_M2_FUNCTIONAL_FAILURE_SUMMARY "
            f"count={functional.failed_count} "
            f"diagnostics="
            f"{functional_failure_diagnostics}"
        )

    assert functional.failed_count == 0, (
        "functional failures observed; "
        f"first={first_functional_failure}; "
        f"diagnostics="
        f"{functional_failure_diagnostics}"
    )

    assert performance.failed_count == 0, (
        "performance failures observed; "
        f"first={first_performance_failure}; "
        f"first_accept_divergence="
        f"{first_accept_timing_divergence}; "
        f"diagnostics="
        f"{performance_failure_diagnostics}"
    )

    final_checkpoint = checkpoints[-1]

    accepted_per_second = (
        ACCEPTED_BUDGET
        / (
            elapsed_ns
            / 1_000_000_000
        )
    )

    dut._log.info(
        "W14_M2_PREFLIGHT=PASS "
        f"seed={ROOT_SEED} "
        f"accepted={ACCEPTED_BUDGET} "
        f"retired="
        f"{final_snapshot.retired_checked} "
        f"in_flight={in_flight} "
        f"cycles={cycle} "
        f"stalls={stall_cycle_count} "
        f"flushes={flush_cycle_count} "
        f"released_entries="
        f"{released_entry_count} "
        f"refill_pauses="
        f"{refill_pause_count} "
        f"patched_words="
        f"{patched_word_count} "
        f"patch_reuses="
        f"{patch_reuse_count} "
        f"max_resident_words="
        f"{max_resident_words} "
        f"l1_intent="
        f"{final_checkpoint.l1_intent_count} "
        f"l1_validated="
        f"{final_checkpoint.l1_validated_count} "
        f"l2_intent="
        f"{final_checkpoint.l2_intent_count} "
        f"l2_validated="
        f"{final_checkpoint.l2_validated_count} "
        f"wall_ns={elapsed_ns} "
        f"diagnostic_accepted_per_s="
        f"{accepted_per_second:.2f} "
        f"plan_hash={plan.plan_hash}"
    )
