from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path

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
from research.week13.pure_random.campaign_seed import (
    derive_campaign_seeds,
)
from research.week13.pure_random.pilot_diagnostics import (
    build_m1_plan_diagnostics,
)
from research.week13.pure_random.runtime_stream import (
    PureRandomRuntimeWindow,
    PureRandomStreamExecutionMismatch,
    build_runtime_entries,
    physical_pc_for_logical_word,
)
from research.week13.pure_random.stream_planner import (
    generate_pure_random_plan,
)


CLOCK_NS = 10

REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[4]
)

DUT_REVISION = (
    "595ed75dcf8544c4f7ab3f16966df34ba1c11ee7"
)

PROTOCOL_REVISION = (
    "fa906a3f8c6630c6e41d9321d79b2c408d04adc5"
)

PILOT_SCHEMA_VERSION = "w15.m1-final.telemetry.v1"

STOCHASTIC_ADDENDUM_VERSION = (
    "w13.stochastic-generator.v1.1"
)

GENERATOR_SOURCE_PATHS = (
    "research/week13/pure_random/campaign_seed.py",
    "research/week13/pure_random/family_sampler.py",
    "research/week13/pure_random/operand_realizer.py",
    "research/week13/pure_random/control_realizer.py",
    "research/week13/pure_random/stream_planner.py",
)



def generator_source_revision() -> str:
    """
    Content-address the frozen M1 stochastic generator.

    Telemetry-only helpers and the RTL pilot harness are deliberately
    excluded. Therefore a reporting repair cannot change this revision
    unless generator semantics/source actually changes.
    """
    digest = hashlib.sha256()

    for relative_path in GENERATOR_SOURCE_PATHS:
        source = REPO_ROOT / relative_path

        if not source.is_file():
            raise AssertionError(
                "missing M1 generator source: "
                f"{relative_path}"
            )

        digest.update(
            relative_path.encode("utf-8")
        )
        digest.update(b"\0")
        digest.update(source.read_bytes())
        digest.update(b"\0")

    return (
        "sha256:"
        + digest.hexdigest()
    )


def collect_runtime_environment() -> dict:
    """
    Collect minimum reproducibility metadata required by M1 telemetry.
    """
    simulator_name = getattr(
        cocotb,
        "SIM_NAME",
        os.environ.get(
            "SIM",
            "unknown",
        ),
    )

    simulator_version = getattr(
        cocotb,
        "SIM_VERSION",
        None,
    )

    if (
        not simulator_version
        and "verilator"
        in str(simulator_name).lower()
    ):
        result = subprocess.run(
            [
                "verilator",
                "--version",
            ],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        simulator_version = (
            result.stdout.strip()
        )

    if not simulator_version:
        simulator_version = "unknown"

    return {
        "python_version": (
            platform.python_version()
        ),
        "cocotb_version": getattr(
            cocotb,
            "__version__",
            "unknown",
        ),
        "simulator_name": (
            str(simulator_name)
        ),
        "simulator_version": (
            str(simulator_version)
        ),
        "timestamp_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }


def first_checker_failure(
    *,
    first_functional_failure,
    first_performance_failure,
    functional_failure_diagnostics,
    performance_failure_diagnostics,
):
    """
    Return the earliest attributable checker failure.

    Functional wins only on an exact instruction-ID tie so ordering is
    deterministic.
    """
    candidates = []

    if first_functional_failure is not None:
        detail = next(
            (
                item
                for item
                in functional_failure_diagnostics
                if (
                    item["instruction_id"]
                    == first_functional_failure
                )
            ),
            {
                "instruction_id": (
                    first_functional_failure
                )
            },
        )

        candidates.append({
            "kind": "functional",
            "instruction_id": (
                first_functional_failure
            ),
            "detail": detail,
        })

    if first_performance_failure is not None:
        detail = next(
            (
                item
                for item
                in performance_failure_diagnostics
                if (
                    item["instruction_id"]
                    == first_performance_failure
                )
            ),
            {
                "instruction_id": (
                    first_performance_failure
                )
            },
        )

        candidates.append({
            "kind": "performance",
            "instruction_id": (
                first_performance_failure
            ),
            "detail": detail,
        })

    if not candidates:
        return None

    priority = {
        "functional": 0,
        "performance": 1,
    }

    return min(
        candidates,
        key=lambda item: (
            item["instruction_id"],
            priority[item["kind"]],
        ),
    )



def first_failure_with_terminal(
    *,
    terminal_instruction_id,
    terminal_detail,
    first_functional_failure,
    first_performance_failure,
    functional_failure_diagnostics,
    performance_failure_diagnostics,
):
    """
    Return the earliest failure across attributable checker failures
    and the terminal accepted-stream divergence.
    """
    checker_failure = first_checker_failure(
        first_functional_failure=(
            first_functional_failure
        ),
        first_performance_failure=(
            first_performance_failure
        ),
        functional_failure_diagnostics=(
            functional_failure_diagnostics
        ),
        performance_failure_diagnostics=(
            performance_failure_diagnostics
        ),
    )

    terminal_failure = {
        "kind": "terminal_execution_divergence",
        "instruction_id": (
            terminal_instruction_id
        ),
        "detail": terminal_detail,
    }

    if checker_failure is None:
        return terminal_failure

    if (
        checker_failure["instruction_id"]
        <= terminal_instruction_id
    ):
        return checker_failure

    return terminal_failure


def git_text(
    *args: str,
) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    return result.stdout.strip()


def validate_pilot_provenance() -> str:
    head = git_text(
        "rev-parse",
        "HEAD",
    )

    dirty = git_text(
        "status",
        "--porcelain",
    )

    if dirty:
        raise AssertionError(
            "official Week15 M1 final execution "
            "requires a clean git tree"
        )

    t15 = git_text(
        "rev-parse",
        "GATE_T15_COMPLETE^{commit}",
    )

    if t15 != FINAL_CONFIG.gate_t15_head:
        raise AssertionError(
            "GATE_T15_COMPLETE identity mismatch"
        )

    design_delta = git_text(
        "diff",
        f"{FINAL_CONFIG.gate_t15_head}..{head}",
        "--",
        "design",
    )

    if design_delta:
        raise AssertionError(
            "design/ changed after Gate T15"
        )

    return head


from research.week15.final_campaign.runtime_config import (
    load_final_runtime_config,
)

FINAL_CONFIG = load_final_runtime_config(
    "M1"
)

PILOT_SEEDS = frozenset({
    FINAL_CONFIG.root_seed,
})

ROOT_SEED = FINAL_CONFIG.root_seed
ACCEPTED_BUDGET = FINAL_CONFIG.accepted_budget
CHECKPOINT_INTERVAL = FINAL_CONFIG.checkpoint_interval

REFILL_THRESHOLD_WORDS = 4

MAX_CYCLES = (
    ACCEPTED_BUDGET
    * 16
    + 4096
)


def read_proc_status_kib(
    field: str,
) -> int:
    with open(
        "/proc/self/status",
        "r",
        encoding="ascii",
    ) as handle:
        for line in handle:
            if line.startswith(
                f"{field}:"
            ):
                parts = line.split()

                if (
                    len(parts) < 2
                    or parts[1].isdigit()
                    is False
                ):
                    raise RuntimeError(
                        f"malformed {field}: "
                        f"{line!r}"
                    )

                value = int(parts[1])

                if value < 0:
                    raise RuntimeError(
                        f"{field} cannot be negative"
                    )

                return value

    raise RuntimeError(
        f"{field} not found in "
        "/proc/self/status"
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
async def test_m1_pilot_exact_cut_10000(
    dut,
):
    harness_revision = (
        validate_pilot_provenance()
    )

    result_dir = FINAL_CONFIG.result_dir

    result_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_path = FINAL_CONFIG.result_path

    if result_path.exists():
        raise AssertionError(
            "refusing to overwrite existing "
            f"M1 pilot result: {result_path}"
        )

    # ==========================================================
    # OFFICIAL FULL-SYSTEM MEASUREMENT WINDOW
    #
    # Frozen Week-13 protocol:
    # start immediately before stochastic plan generation.
    # ==========================================================
    # Static provenance is intentionally collected outside the
    # authoritative performance window. It may inspect source
    # files or query the simulator executable, neither of which
    # is campaign execution work.
    generator_revision = (
        generator_source_revision()
    )

    runtime_environment = (
        collect_runtime_environment()
    )

    measurement_start_ns = (
        time.perf_counter_ns()
    )

    peak_rss_start_kib = (
        read_proc_status_kib(
            "VmHWM"
        )
    )

    # ==========================================================
    # STOCHASTIC PILOT PLAN
    # ==========================================================
    plan = generate_pure_random_plan(
        ROOT_SEED,
        ACCEPTED_BUDGET,
    )

    plan_diagnostics = (
        build_m1_plan_diagnostics(
            plan
        )
    )

    campaign_seeds = (
        derive_campaign_seeds(
            ROOT_SEED
        )
    )

    assert (
        campaign_seeds.root_seed
        == ROOT_SEED
    )

    entries = build_runtime_entries(
        plan
    )

    total_image_words = sum(
        entry.image_word_count
        for entry in entries
    )

    families = Counter(
        block.realized.family.value
        for block in plan.blocks
    )

    assert (
        plan.accepted_instruction_count
        == ACCEPTED_BUDGET
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

    expected_accepted_families = tuple(
        entry.planned.realized.family.value
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

    expected_last_generation = (
        accepted_logical_words[-1]
        // IMEM_WORD_CAPACITY
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

    def wall_ns() -> int:
        return (
            time.perf_counter_ns()
            - measurement_start_ns
        )

    def write_terminal_telemetry(
        *,
        event,
        expected_pc: int,
        expected_word: int,
        reason: str,
    ) -> None:
        # The divergent event was physically accepted by the DUT
        # and therefore exists in the adapter stream, but it has
        # deliberately NOT entered the authoritative attributable
        # checker/coverage prefix.
        observed_accepted = (
            adapter.instruction_count
        )

        attributable_accepted = (
            coverage.executed_instructions
        )

        assert (
            observed_accepted
            == event.instruction_index
        )

        assert (
            attributable_accepted
            == event.instruction_index - 1
        )

        assert (
            window.accepted_count
            == attributable_accepted
        )

        assert (
            functional.expected_count
            == attributable_accepted
        )

        assert (
            performance.expected_count
            == attributable_accepted
        )

        retired_checked = (
            retire_monitor.retired_count
        )

        assert (
            functional.checked_count
            == retired_checked
        )

        assert (
            performance.checked_count
            == retired_checked
        )

        attributable_in_flight = (
            attributable_accepted
            - retired_checked
        )

        assert (
            functional.pending_expected_count
            == attributable_in_flight
        )

        assert (
            performance.pending_count
            == attributable_in_flight
        )

        l1_registered_hits = sum(
            l1_validated
            .validation_attempt_count
            .values()
        )

        l1_validated_hits = sum(
            l1_validated
            .validated_hit_count
            .values()
        )

        l1_rejected_hits = sum(
            l1_validated
            .rejected_hit_count
            .values()
        )

        l2_registered_hits = (
            l2_live.checker.attempt_count
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

        max_intent_consumer_id = (
            cut_driver.max_intent_consumer_id
        )

        if max_intent_consumer_id:
            assert (
                max_intent_consumer_id
                <= attributable_accepted
            )

        checkpoint_trajectory = [
            {
                "accepted": (
                    checkpoint
                    .executed_instructions
                ),
                "cycle": checkpoint.cycle,
                "l1_intent": (
                    checkpoint
                    .l1_intent_count
                ),
                "l1_validated": (
                    checkpoint
                    .l1_validated_count
                ),
                "l2_intent": (
                    checkpoint
                    .l2_intent_count
                ),
                "l2_validated": (
                    checkpoint
                    .l2_validated_count
                ),
            }
            for checkpoint in checkpoints
        ]

        # Final diagnostic measurement snapshot.
        # Terminal prefixes are NOT eligible for the official
        # fixed-N performance quantities.
        terminal_peak_rss_kib = (
            read_proc_status_kib(
                "VmHWM"
            )
        )

        terminal_wall_ns = wall_ns()

        terminal_record = {
            "schema_version": (
                PILOT_SCHEMA_VERSION
            ),
            "method": "M1-PR",
            "phase": FINAL_CONFIG.phase,
            "seed": ROOT_SEED,

            "rng": {
                "root_seed": campaign_seeds.root_seed,
                "family_seed": campaign_seeds.family_seed,
                "operand_seed": campaign_seeds.operand_seed,
            },

            "generator_revision": generator_revision,
            "generator_revision_kind": "sha256-source-bundle",
            "stochastic_addendum_version": STOCHASTIC_ADDENDUM_VERSION,
            "stochastic_addendum_revision": PROTOCOL_REVISION,
            "runtime_environment": runtime_environment,

            "generator_diagnostics": {
                "scope": "full_generated_plan",
                "payload_family_draw_counts": dict(
                    plan_diagnostics.family_counts
                ),
                "branch_subtype_counts": dict(
                    plan_diagnostics.branch_subtype_counts
                ),
                "branch_taken_count": (
                    plan_diagnostics.branch_taken_count
                ),
                "branch_not_taken_count": (
                    plan_diagnostics.branch_not_taken_count
                ),
                "structural_nop_accepted_count": (
                    plan_diagnostics.structural_nop_accepted_count
                ),
                "lw_ea_histogram": dict(
                    plan_diagnostics.lw_ea_histogram
                ),
                "sw_ea_histogram": dict(
                    plan_diagnostics.sw_ea_histogram
                ),
                "memory_viable_base_set_size_histogram": dict(
                    plan_diagnostics.memory_viable_base_set_size_histogram
                ),
                "accepted_base_register_histogram": dict(
                    plan_diagnostics.accepted_base_register_histogram
                ),
            },
            "accepted_budget": (
                ACCEPTED_BUDGET
            ),

            "provenance": {
                "dut_revision": (
                    DUT_REVISION
                ),
                "harness_revision": (
                    harness_revision
                ),
                "protocol_revision": (
                    PROTOCOL_REVISION
                ),
                "git_dirty": False,
            },

            "status": (
                "VALID_DUT_FAILURE_TERMINAL"
            ),

            "terminal_divergence_status": "OBSERVED",

            "post_cut_clock_edges": None,

            "checker_mismatch_count": (
                functional.failed_count
                + performance.failed_count
            ),

            "checker_mismatch_breakdown": {
                "functional_failed_instructions": (
                    functional.failed_count
                ),
                "performance_failed_instructions": (
                    performance.failed_count
                ),
            },

            "first_failure": (
                first_failure_with_terminal(
                    terminal_instruction_id=(
                        event.instruction_index
                    ),
                    terminal_detail={
                        "cycle": cycle,
                        "reason": reason,
                        "expected_pc": expected_pc,
                        "observed_pc": event.pc,
                        "expected_instruction": (
                            expected_word
                        ),
                        "observed_instruction": (
                            event.instruction
                        ),
                    },
                    first_functional_failure=(
                        first_functional_failure
                    ),
                    first_performance_failure=(
                        first_performance_failure
                    ),
                    functional_failure_diagnostics=(
                        functional_failure_diagnostics
                    ),
                    performance_failure_diagnostics=(
                        performance_failure_diagnostics
                    ),
                )
            ),

            "fixed_budget_complete": False,

            "eligibility": {
                "fixed_budget_metrics": False,
                "auc": False,
                "throughput": False,
                "ordinary_fixed_n_inference": False,
            },

            "terminal_divergence": {
                "instruction_id": (
                    event.instruction_index
                ),
                "cycle": cycle,
                "reason": reason,
                "expected_pc": expected_pc,
                "observed_pc": event.pc,
                "expected_instruction": (
                    expected_word
                ),
                "observed_instruction": (
                    event.instruction
                ),
            },

            "lifecycle": {
                "observed_accepted_at_divergence": (
                    observed_accepted
                ),
                "attributable_accepted_prefix": (
                    attributable_accepted
                ),
                "retired_checked": (
                    retired_checked
                ),
                "in_flight_attributable": (
                    attributable_in_flight
                ),
                "functional_pending": (
                    functional
                    .pending_expected_count
                ),
                "performance_pending": (
                    performance.pending_count
                ),
            },

            "execution": {
                "cycles_to_divergence": cycle,
                "stall_cycles": (
                    stall_cycle_count
                ),
                "flush_cycles": (
                    flush_cycle_count
                ),
                "refill_pauses": (
                    refill_pause_count
                ),
                "released_entries": (
                    released_entry_count
                ),
                "patched_words": (
                    patched_word_count
                ),
                "patch_reuses": (
                    patch_reuse_count
                ),
                "max_resident_words": (
                    max_resident_words
                ),
            },

            "functional": {
                "denominator": (
                    retired_checked
                ),
                "checked": (
                    functional.checked_count
                ),
                "passed": (
                    functional.passed_count
                ),
                "failed": (
                    functional.failed_count
                ),
                "pending": (
                    functional
                    .pending_expected_count
                ),
                "first_failure": (
                    first_functional_failure
                ),
            },

            "performance": {
                "denominator": (
                    retired_checked
                ),
                "checked": (
                    performance.checked_count
                ),
                "passed": (
                    performance.passed_count
                ),
                "failed": (
                    performance.failed_count
                ),
                "pending": (
                    performance.pending_count
                ),
                "total_excess_cycles": (
                    performance
                    .total_excess_cycles
                ),
                "max_excess_cycles": (
                    performance
                    .max_excess_cycles
                ),
                "first_failure": (
                    first_performance_failure
                ),
                "first_accept_timing_divergence": (
                    first_accept_timing_divergence
                ),
            },

            "coverage": {
                # The divergent accepted event is intentionally
                # outside this attributable coverage prefix.
                "denominator": (
                    attributable_accepted
                ),
                "l1_intent": (
                    l1_intent_count
                ),
                "l1_validated": (
                    l1_validated_count
                ),
                "l2_intent": (
                    l2_intent_count
                ),
                "l2_validated": (
                    l2_validated_count
                ),

                "l1_registered_hits": (
                    l1_registered_hits
                ),
                "l1_validated_hits": (
                    l1_validated_hits
                ),
                "l1_rejected_hits": (
                    l1_rejected_hits
                ),
                "l1_pending_hits": (
                    l1_validated.pending_hits
                ),

                "l2_registered_hits": (
                    l2_registered_hits
                ),
                "l2_validated_hits": (
                    l2_live
                    .validated_hit_count
                ),
                "l2_rejected_hits": (
                    l2_live
                    .rejected_hit_count
                ),
                "l2_pending_hits": (
                    l2_live
                    .pending_hit_count
                ),

                "max_intent_consumer_id": (
                    max_intent_consumer_id
                ),
                "mid_run_hit_prune_count": 0,
                "checkpoint_count": (
                    len(checkpoints)
                ),
                "checkpoints": (
                    checkpoint_trajectory
                ),
            },

            "generator": {
                "plan_hash": plan.plan_hash,
                "block_count": (
                    len(plan.blocks)
                ),
                "image_words": (
                    total_image_words
                ),
                "final_expected_pc": (
                    plan.final_expected_pc
                ),
                "partial_final_block": (
                    plan.blocks[-1].is_partial
                ),
                "family_counts": dict(
                    sorted(
                        families.items()
                    )
                ),
            },

            "benchmark": {
                # Diagnostic only. A terminal prefix is explicitly
                # excluded from fixed-budget throughput/AUC.
                "wall_ns_diagnostic": (
                    terminal_wall_ns
                ),
                "accepted_per_s": None,
                "cycles_per_s": None,
                "peak_rss_kib_diagnostic": (
                    terminal_peak_rss_kib
                ),
                "peak_rss_start_kib": (
                    peak_rss_start_kib
                ),
            },
        }

        result_path.write_text(
            json.dumps(
                terminal_record,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
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
                    "family": (
                        expected_accepted_families[
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
                    "W13_M1_FUNCTIONAL_FAILURE "
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
                        "W13_M1_PERFORMANCE_FAILURE "
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

            terminal_reason = (
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

            write_terminal_telemetry(
                event=event,
                expected_pc=expected_pc,
                expected_word=expected_word,
                reason=terminal_reason,
            )

            dut._log.error(
                "W15_M1_FINAL_RESULT "
                "status="
                "VALID_DUT_FAILURE_TERMINAL "
                f"seed={ROOT_SEED} "
                f"observed_accepted="
                f"{event.instruction_index} "
                f"attributable_prefix="
                f"{event.instruction_index - 1} "
                f"telemetry={result_path}"
            )

            raise AssertionError(
                terminal_reason
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
                "W13_M1_ACCEPT_TIMING_DIVERGENCE "
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
                    "prevalidated M1 event "
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

            # Exact-N may terminate in either legal shape:
            #
            #   1. partial final block:
            #      the accepted budget lands inside the block, so one
            #      resident suffix remains and must be discarded;
            #
            #   2. complete final block:
            #      the Nth accepted instruction completes the block, so
            #      finalize_accepted_event() has already released it and
            #      no resident suffix remains.
            if final_plan_block.is_partial:
                assert (
                    window.pending_entry_count
                    == 1
                )

                discarded = (
                    window
                    .discard_unexecuted_suffix()
                )

                assert (
                    discarded
                    .accepted_count_at_termination
                    == ACCEPTED_BUDGET
                )

                assert (
                    discarded
                    .head_accepted_instruction_count
                    == len(
                        final_plan_block
                        .accepted_word_indices
                    )
                )

                assert (
                    len(discarded.entries)
                    == 1
                )

                timing_oracle.release_logical_words(
                    first_logical_word_index=(
                        discarded.entries[0]
                        .logical_word_start
                    ),
                    word_count=(
                        discarded
                        .reclaimed_resident_word_count
                    ),
                )

            else:
                assert (
                    window.pending_entry_count
                    == 0
                )

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
                == total_image_words
            )

            assert (
                timing_oracle
                .next_append_logical_word_index
                == total_image_words
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
    # FINAL PILOT OBLIGATIONS
    # ==========================================================
    peak_rss_kib = (
        read_proc_status_kib(
            "VmHWM"
        )
    )

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
        == total_image_words
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
                expected_last_generation
                + 1
            )
        )
    )

    assert (
        max_executed_logical_word
        // IMEM_WORD_CAPACITY
        == expected_last_generation
    )

    expected_checkpoint_ids = list(
        range(
            CHECKPOINT_INTERVAL,
            ACCEPTED_BUDGET + 1,
            CHECKPOINT_INTERVAL,
        )
    )

    assert [
        checkpoint.executed_instructions
        for checkpoint in checkpoints
    ] == expected_checkpoint_ids

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

    # Attributable nonterminal checker failures remain valid DUT
    # observations and therefore run through the exact accepted budget.
    if functional.failed_count != 0:
        dut._log.error(
            "W13_M1_FUNCTIONAL_FAILURE_SUMMARY "
            f"count={functional.failed_count} "
            f"diagnostics="
            f"{functional_failure_diagnostics}"
        )

    if (
        functional.failed_count > 0
        or performance.failed_count > 0
    ):
        run_status = (
            "VALID_DUT_FAILURE_NONTERMINAL"
        )
    else:
        run_status = "COMPLETED"

    final_checkpoint = checkpoints[-1]

    elapsed_seconds = (
        elapsed_ns
        / 1_000_000_000
    )

    accepted_per_second = (
        ACCEPTED_BUDGET
        / elapsed_seconds
    )

    cycles_per_second = (
        cycle
        / elapsed_seconds
    )

    l1_registered_hits = sum(
        l1_validated
        .validation_attempt_count
        .values()
    )

    l1_validated_hits = sum(
        l1_validated
        .validated_hit_count
        .values()
    )

    l1_rejected_hits = sum(
        l1_validated
        .rejected_hit_count
        .values()
    )

    l2_registered_hits = (
        l2_live.checker.attempt_count
    )

    max_intent_consumer_id = (
        final_snapshot.max_intent_consumer_id
    )

    checkpoint_trajectory = [
        {
            "accepted": (
                checkpoint
                .executed_instructions
            ),
            "cycle": checkpoint.cycle,
            "l1_intent": (
                checkpoint
                .l1_intent_count
            ),
            "l1_validated": (
                checkpoint
                .l1_validated_count
            ),
            "l2_intent": (
                checkpoint
                .l2_intent_count
            ),
            "l2_validated": (
                checkpoint
                .l2_validated_count
            ),
        }
        for checkpoint in checkpoints
    ]

    telemetry_record = {
        "schema_version": (
            PILOT_SCHEMA_VERSION
        ),
        "method": "M1-PR",
        "phase": FINAL_CONFIG.phase,
        "seed": ROOT_SEED,

        "rng": {
            "root_seed": campaign_seeds.root_seed,
            "family_seed": campaign_seeds.family_seed,
            "operand_seed": campaign_seeds.operand_seed,
        },

        "generator_revision": generator_revision,
        "generator_revision_kind": "sha256-source-bundle",
        "stochastic_addendum_version": STOCHASTIC_ADDENDUM_VERSION,
        "stochastic_addendum_revision": PROTOCOL_REVISION,
        "runtime_environment": runtime_environment,

        "generator_diagnostics": {
            "scope": "full_generated_plan",
            "payload_family_draw_counts": dict(
                plan_diagnostics.family_counts
            ),
            "branch_subtype_counts": dict(
                plan_diagnostics.branch_subtype_counts
            ),
            "branch_taken_count": (
                plan_diagnostics.branch_taken_count
            ),
            "branch_not_taken_count": (
                plan_diagnostics.branch_not_taken_count
            ),
            "structural_nop_accepted_count": (
                plan_diagnostics.structural_nop_accepted_count
            ),
            "lw_ea_histogram": dict(
                plan_diagnostics.lw_ea_histogram
            ),
            "sw_ea_histogram": dict(
                plan_diagnostics.sw_ea_histogram
            ),
            "memory_viable_base_set_size_histogram": dict(
                plan_diagnostics.memory_viable_base_set_size_histogram
            ),
            "accepted_base_register_histogram": dict(
                plan_diagnostics.accepted_base_register_histogram
            ),
        },
        "accepted_budget": (
            ACCEPTED_BUDGET
        ),

        "provenance": {
            "dut_revision": DUT_REVISION,
            "harness_revision": (
                harness_revision
            ),
            "protocol_revision": (
                PROTOCOL_REVISION
            ),
            "git_dirty": False,
        },

        "status": run_status,

        "terminal_divergence_status": "NOT_OBSERVED",

        "post_cut_clock_edges": 0,

        "checker_mismatch_count": (
            functional.failed_count
            + performance.failed_count
        ),

        "checker_mismatch_breakdown": {
            "functional_failed_instructions": (
                functional.failed_count
            ),
            "performance_failed_instructions": (
                performance.failed_count
            ),
        },

        "first_failure": (
            first_checker_failure(
                first_functional_failure=(
                    first_functional_failure
                ),
                first_performance_failure=(
                    first_performance_failure
                ),
                functional_failure_diagnostics=(
                    functional_failure_diagnostics
                ),
                performance_failure_diagnostics=(
                    performance_failure_diagnostics
                ),
            )
        ),

        "fixed_budget_complete": True,

        "eligibility": {
            "fixed_budget_metrics": True,
            "auc": True,
            "throughput": True,
            "ordinary_fixed_n_inference": True,
        },

        "lifecycle": {
            "accepted": (
                final_snapshot.accepted
            ),
            "retired_checked": (
                final_snapshot
                .retired_checked
            ),
            "in_flight_at_cut": (
                in_flight
            ),
            "functional_pending": (
                final_snapshot
                .functional_pending
            ),
            "performance_pending": (
                final_snapshot
                .performance_pending
            ),
        },

        "execution": {
            "cycles": cycle,
            "stall_cycles": (
                stall_cycle_count
            ),
            "flush_cycles": (
                flush_cycle_count
            ),
            "cut_cycle": cut_cycle,
            "kill_cycle": cut_cycle,
            "refill_pauses": (
                refill_pause_count
            ),
            "released_entries": (
                released_entry_count
            ),
            "patched_words": (
                patched_word_count
            ),
            "patch_reuses": (
                patch_reuse_count
            ),
            "max_resident_words": (
                max_resident_words
            ),
        },

        "functional": {
            "denominator": (
                final_snapshot
                .retired_checked
            ),
            "checked": (
                functional.checked_count
            ),
            "passed": (
                functional.passed_count
            ),
            "failed": (
                functional.failed_count
            ),
            "pending": (
                functional
                .pending_expected_count
            ),
            "first_failure": (
                first_functional_failure
            ),
        },

        "performance": {
            "denominator": (
                final_snapshot
                .retired_checked
            ),
            "checked": (
                performance.checked_count
            ),
            "passed": (
                performance.passed_count
            ),
            "failed": (
                performance.failed_count
            ),
            "pending": (
                performance.pending_count
            ),
            "total_excess_cycles": (
                performance
                .total_excess_cycles
            ),
            "max_excess_cycles": (
                performance
                .max_excess_cycles
            ),
            "first_failure": (
                first_performance_failure
            ),
            "first_accept_timing_divergence": (
                first_accept_timing_divergence
            ),
        },

        "coverage": {
            "denominator": (
                ACCEPTED_BUDGET
            ),

            "l1_intent": (
                final_checkpoint
                .l1_intent_count
            ),
            "l1_validated": (
                final_checkpoint
                .l1_validated_count
            ),
            "l2_intent": (
                final_checkpoint
                .l2_intent_count
            ),
            "l2_validated": (
                final_checkpoint
                .l2_validated_count
            ),

            "l1_registered_hits": (
                l1_registered_hits
            ),
            "l1_validated_hits": (
                l1_validated_hits
            ),
            "l1_rejected_hits": (
                l1_rejected_hits
            ),
            "l1_pending_hits": (
                l1_validated.pending_hits
            ),

            "l2_registered_hits": (
                l2_registered_hits
            ),
            "l2_validated_hits": (
                l2_live
                .validated_hit_count
            ),
            "l2_rejected_hits": (
                l2_live
                .rejected_hit_count
            ),
            "l2_pending_hits": (
                l2_live
                .pending_hit_count
            ),

            "max_intent_consumer_id": (
                max_intent_consumer_id
            ),
            "mid_run_hit_prune_count": 0,
            "checkpoint_count": (
                len(checkpoints)
            ),
            "checkpoints": (
                checkpoint_trajectory
            ),
        },

        "generator": {
            "plan_hash": plan.plan_hash,
            "block_count": (
                len(plan.blocks)
            ),
            "image_words": (
                total_image_words
            ),
            "final_expected_pc": (
                plan.final_expected_pc
            ),
            "partial_final_block": (
                plan.blocks[-1].is_partial
            ),
            "family_counts": dict(
                sorted(
                    families.items()
                )
            ),
        },

        "benchmark": {
            "wall_ns": elapsed_ns,
            "accepted_per_s": (
                accepted_per_second
            ),
            "cycles_per_s": (
                cycles_per_second
            ),
            "peak_rss_kib": (
                peak_rss_kib
            ),
            "peak_rss_start_kib": (
                peak_rss_start_kib
            ),
        },
    }

    result_path.write_text(
        json.dumps(
            telemetry_record,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    dut._log.info(
        "W15_M1_FINAL_RESULT "
        f"status={run_status} "
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
        f"accepted_per_s="
        f"{accepted_per_second:.2f} "
        f"cycles_per_s="
        f"{cycles_per_second:.2f} "
        f"peak_rss_kib="
        f"{peak_rss_kib} "
        f"peak_rss_start_kib="
        f"{peak_rss_start_kib} "
        f"checkpoints="
        f"{len(checkpoints)} "
        f"plan_hash={plan.plan_hash} "
        f"telemetry={result_path}"
    )
