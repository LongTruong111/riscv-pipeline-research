from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
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

from research.week10.adaptive.campaign_seed import (
    SEED_DOMAIN as ADAPTIVE_SEED_DOMAIN,
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

from research.week13.adaptive.pilot_metrics import (
    L2IntentCheckpoint,
    normalized_l2_intent_auc,
)

from research.week13.adaptive.pilot_contract import (
    ACCEPTED_BUDGET,
    ALPHA_CANDIDATES,
    BATCH_CANDIDATES,
    CHECKPOINT_INTERVAL,
    EPSILON_CANDIDATES,
    PILOT_SEEDS,
    Q_FLOOR,
)

from research.week13.adaptive.stream_identity import (
    peek_expected_accepted_identity,
)

from research.week15.reproducibility.runtime_config import (
    load_runtime_config,
)
from research.week15.reproducibility.runtime_trace import (
    ReproTraceSession,
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



REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)

DUT_REVISION = (
    "595ed75dcf8544c4f7ab3f16966df34ba1c11ee7"
)

PROTOCOL_REVISION = (
    "fa906a3f8c6630c6e41d9321d79b2c408d04adc5"
)

PILOT_SCHEMA_VERSION = (
    "w15.adaptive-repro.telemetry.v1"
)


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
            "official Adaptive pilot requires "
            "a clean git tree"
        )

    design_delta = git_text(
        "diff",
        f"{DUT_REVISION}..{head}",
        "--",
        "design",
    )

    if design_delta:
        raise AssertionError(
            "design/ changed after frozen "
            f"DUT revision {DUT_REVISION}"
        )

    subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            PROTOCOL_REVISION,
            head,
        ],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    return head



def git_blob_revision(
    head: str,
    relative_path: str,
) -> str:
    blob = git_text(
        "rev-parse",
        f"{head}:{relative_path}",
    )

    return f"git-blob:{blob}"


def adaptive_stack_tree_revision(
    head: str,
) -> str:
    tree = git_text(
        "rev-parse",
        f"{head}:research/week10/adaptive",
    )

    return f"git-tree:{tree}"


def collect_runtime_environment() -> dict:
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
                    or not parts[1].isdigit()
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


def write_json_atomic(
    path: Path,
    record: dict,
) -> None:
    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            record,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    os.replace(
        tmp,
        path,
    )


CLOCK_NS = 10

REPRO_CONFIG = load_runtime_config()

ROOT_SEED = REPRO_CONFIG.root_seed
ACCEPTED_BUDGET = REPRO_CONFIG.accepted_budget
REPETITION = REPRO_CONFIG.repetition

EPSILON = REPRO_CONFIG.epsilon
ALPHA = REPRO_CONFIG.alpha
Q_FLOOR = REPRO_CONFIG.q_floor
NOMINAL_BATCH = REPRO_CONFIG.nominal_batch
CHECKPOINT_INTERVAL = (
    REPRO_CONFIG.checkpoint_interval
)

RESULT_DIR = REPRO_CONFIG.result_dir
RESULT_PATH = REPRO_CONFIG.result_path
CONTRACT_SHA256 = (
    REPRO_CONFIG.contract_sha256
)
CONFIG_ID = REPRO_CONFIG.config_id

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



def first_checker_failure(
    *,
    first_functional_failure,
    first_performance_failure,
    functional_failure_diagnostics,
    performance_failure_diagnostics,
):
    """
    Return the earliest attributable checker failure.

    Functional wins on an exact instruction-ID tie so the
    ordering is deterministic.
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
    Return the earliest failure across attributable checker
    failures and terminal accepted-stream divergence.
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


@cocotb.test()
async def test_adaptive_reproducibility_exact_cut(
    dut,
):
    """
    Week-15 Adaptive-CGS reproducibility qualification harness.

    Runtime configuration is restricted to the frozen
    Week-13 adaptive-pilot hyperparameter grid.

    Qualifies:
      - frozen production Adaptive generator/runtime;
      - read-only planned-stream prevalidation;
      - full functional/performance checker stack;
      - L1/L2 Intent + Validated;
      - common CampaignCutDriver lifecycle;
      - bounded IMEM streaming/refill;
      - multi-epoch adaptive continuity;
      - exact N=10000 accepted hard cap.
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
    harness_revision = (
        validate_pilot_provenance()
    )

    adaptive_stack_revision = (
        adaptive_stack_tree_revision(
            harness_revision
        )
    )

    pilot_contract_revision = (
        git_blob_revision(
            harness_revision,
            "research/week13/adaptive/"
            "pilot_contract.py",
        )
    )

    pilot_metrics_revision = (
        git_blob_revision(
            harness_revision,
            "research/week13/adaptive/"
            "pilot_metrics.py",
        )
    )

    runtime_environment = (
        collect_runtime_environment()
    )

    RESULT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if RESULT_PATH.exists():
        raise AssertionError(
            "refusing to overwrite existing "
            f"Adaptive result: {RESULT_PATH}"
        )

    peak_rss_start_kib = (
        read_proc_status_kib(
            "VmHWM"
        )
    )

    adaptive_epochs = []
    adaptive_checkpoints = []
    adaptive_summaries = []

    repro_trace = ReproTraceSession()

    def adaptive_epoch_sink(record):
        adaptive_epochs.append(record)
        repro_trace.record_epoch(record)

    def adaptive_checkpoint_sink(record):
        adaptive_checkpoints.append(record)
        repro_trace.record_checkpoint(record)

    def adaptive_summary_sink(record):
        adaptive_summaries.append(record)

    # Authoritative Week-13 full-system measurement begins
    # before construction of the stochastic adaptive stack.
    # build_production_adaptive_stack() derives campaign RNGs
    # and constructs the decision/target/realization engines.
    measurement_start_ns = (
        time.perf_counter_ns()
    )

    def wall_ns() -> int:
        return (
            time.perf_counter_ns()
            - measurement_start_ns
        )

    stack = build_production_adaptive_stack(
        config=config,
        epoch_sink=adaptive_epoch_sink,
        checkpoint_sink=(
            adaptive_checkpoint_sink
        ),
        summary_sink=(
            adaptive_summary_sink
        ),
    )

    l2_coverage = stack.l2_coverage
    coverage = stack.coverage

    coordinator = stack.coordinator
    planner = stack.planner
    window = stack.window

    telemetry = stack.telemetry
    decision_engine = (
        stack.decision_engine
    )

    campaign_seeds = (
        stack.rngs.seeds
    )

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

    first_functional_failure = None
    first_performance_failure = None

    functional_failure_diagnostics = []
    performance_failure_diagnostics = []

    def write_terminal_telemetry(
        *,
        event,
        expected_identity,
        reason: str,
    ) -> None:
        # The divergent event is physically visible to the
        # adapter, but deliberately remains outside the
        # attributable Adaptive runtime/checker/coverage prefix.
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
            cut_driver.max_intent_consumer_id
        )

        if max_intent_consumer_id:
            assert (
                max_intent_consumer_id
                <= attributable_accepted
            )

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
            "method": "M3-Adaptive-CGS",
            "phase": "reproducibility_qualification",

            "seed": ROOT_SEED,

            "configuration": {
                "config_id": CONFIG_ID,
                "epsilon": EPSILON,
                "alpha": ALPHA,
                "q_floor": Q_FLOOR,
                "nominal_batch": (
                    NOMINAL_BATCH
                ),
                "accepted_budget": (
                    ACCEPTED_BUDGET
                ),
                "checkpoint_interval": (
                    CHECKPOINT_INTERVAL
                ),
            },

            "rng": {
                "seed_domain": (
                    ADAPTIVE_SEED_DOMAIN
                ),
                "root_seed": (
                    campaign_seeds.root_seed
                ),
                "decision_seed": (
                    campaign_seeds.decision_seed
                ),
                "target_seed": (
                    campaign_seeds.target_seed
                ),
                "realization_seed": (
                    campaign_seeds
                    .realization_seed
                ),
            },

            "provenance": {
                "dut_revision": DUT_REVISION,
                "harness_revision": (
                    harness_revision
                ),
                "protocol_revision": (
                    PROTOCOL_REVISION
                ),
                "adaptive_stack_revision": (
                    adaptive_stack_revision
                ),
                "pilot_contract_revision": (
                    pilot_contract_revision
                ),
                "pilot_metrics_revision": (
                    pilot_metrics_revision
                ),
                "git_dirty": False,
            },

            "runtime_environment": (
                runtime_environment
            ),

            "status": (
                "VALID_DUT_FAILURE_TERMINAL"
            ),

            "terminal_divergence_status": (
                "OBSERVED"
            ),

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
                        "expected_instruction_index": (
                            expected_identity
                            .instruction_index
                        ),
                        "observed_instruction_index": (
                            event.instruction_index
                        ),
                        "expected_pc": (
                            expected_identity.pc
                        ),
                        "observed_pc": event.pc,
                        "expected_instruction": (
                            expected_identity
                            .instruction
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
                "ordinary_fixed_n_inference": (
                    False
                ),
            },

            "terminal_divergence": {
                "instruction_id": (
                    event.instruction_index
                ),
                "cycle": cycle,
                "reason": reason,
                "expected_instruction_index": (
                    expected_identity
                    .instruction_index
                ),
                "observed_instruction_index": (
                    event.instruction_index
                ),
                "expected_pc": (
                    expected_identity.pc
                ),
                "observed_pc": event.pc,
                "expected_instruction": (
                    expected_identity
                    .instruction
                ),
                "observed_instruction": (
                    event.instruction
                ),
                "logical_word_index": (
                    expected_identity
                    .logical_word_index
                ),
                "stream_entry_key": list(
                    expected_identity
                    .stream_entry_key
                ),
                "entry_progress": (
                    expected_identity
                    .entry_progress
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
                "completed_epochs": (
                    epoch_completion_count
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
                "failure_diagnostics": (
                    functional_failure_diagnostics
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
                "failure_diagnostics": (
                    performance_failure_diagnostics
                ),
            },

            "coverage": {
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
                    l2_live.validated_hit_count
                ),
                "l2_rejected_hits": (
                    l2_live.rejected_hit_count
                ),
                "l2_pending_hits": (
                    l2_live.pending_hit_count
                ),

                "max_intent_consumer_id": (
                    max_intent_consumer_id
                ),
                "checkpoint_count": len(
                    adaptive_checkpoints
                ),
                "checkpoints": [
                    asdict(record)
                    for record
                    in adaptive_checkpoints
                ],
            },

            "adaptive": {
                # Do not fabricate completion of the
                # currently active partial epoch.
                "completed_epochs": (
                    telemetry.completed_epochs
                ),
                "closed_epoch_executed_instructions": (
                    telemetry
                    .closed_epoch_executed_instructions
                ),
                "active_epoch_index": (
                    checkpoint_bridge
                    .active_epoch_index
                ),
                "epoch_records": [
                    asdict(record)
                    for record
                    in adaptive_epochs
                ],
                "checkpoint_records": [
                    asdict(record)
                    for record
                    in adaptive_checkpoints
                ],
                "summary": None,
                "selection_metric": None,
            },

            "benchmark": {
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

        terminal_record[
            "reproducibility"
        ] = {
            "repetition": REPETITION,
            "contract_sha256": (
                CONTRACT_SHA256
            ),
            **repro_trace.snapshot(),
        }

        write_json_atomic(
            RESULT_PATH,
            terminal_record,
        )


    max_resident_words = (
        window.used_words
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
                "Adaptive Week13 pilot "
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
                    "W13_ADAPTIVE_FUNCTIONAL_FAILURE "
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
                    "W13_ADAPTIVE_PERFORMANCE_FAILURE "
                    f"{timing_diagnostic}"
                )

                if (
                    first_performance_failure
                    is None
                ):
                    first_performance_failure = (
                        retired.instruction_id
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

            assert clock_task.done()

            await Timer(
                1,
                units="ns",
            )

            terminal_reason = (
                "VALID_DUT_FAILURE_TERMINAL: "
                f"id={event.instruction_index}, "
                f"expected_id="
                f"{expected_identity.instruction_index}, "
                f"pc=0x{event.pc:03x}/"
                f"0x{expected_identity.pc:03x}, "
                f"instr=0x{event.instruction:08x}/"
                f"0x{expected_identity.instruction:08x}"
            )

            write_terminal_telemetry(
                event=event,
                expected_identity=(
                    expected_identity
                ),
                reason=terminal_reason,
            )

            dut._log.error(
                "W15_ADAPTIVE_REPRO_RESULT "
                "status="
                "VALID_DUT_FAILURE_TERMINAL "
                f"seed={ROOT_SEED} "
                f"config={CONFIG_ID} "
                f"observed_accepted="
                f"{event.instruction_index} "
                f"attributable_prefix="
                f"{event.instruction_index - 1} "
                f"telemetry={RESULT_PATH}"
            )

            raise AssertionError(
                terminal_reason
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
        # WEEK15 CANONICAL ACCEPTED-INSTRUCTION TRACE.
        #
        # event has already passed:
        #   (instruction_index, pc, instruction)
        # planned-stream identity validation and logical-owner
        # validation above.
        # ======================================================
        repro_trace.record_instruction_event(
            event
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

            final_completion = (
                coordinator.finish_epoch(
                    actual_executed_instructions=(
                        actual_final_epoch
                    )
                )
            )

            checkpoint_bridge.finish_epoch(
                current_epoch_index
            )

            telemetry.record_epoch(
                final_completion,
                decision_state=(
                    decision_engine
                ),
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
            completion = (
                coordinator.finish_epoch(
                    actual_executed_instructions=(
                        accepted_this_epoch
                    )
                )
            )

            checkpoint_bridge.finish_epoch(
                current_epoch_index
            )

            telemetry.record_epoch(
                completion,
                decision_state=(
                    decision_engine
                ),
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
    # FINAL PILOT OBLIGATIONS.
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

    assert (
        coordinator
        .pending_attribution_witness_count
        == 0
    )

    assert (
        telemetry
        .closed_epoch_executed_instructions
        == ACCEPTED_BUDGET
    )

    assert (
        telemetry.completed_epochs
        == epoch_completion_count
    )

    assert (
        decision_engine.epoch_index
        == epoch_completion_count
    )

    assert (
        len(adaptive_epochs)
        == epoch_completion_count
    )

    expected_checkpoint_ids = list(
        range(
            CHECKPOINT_INTERVAL,
            ACCEPTED_BUDGET + 1,
            CHECKPOINT_INTERVAL,
        )
    )

    assert [
        record.executed_instructions
        for record
        in adaptive_checkpoints
    ] == expected_checkpoint_ids

    assert (
        len(adaptive_checkpoints)
        == (
            ACCEPTED_BUDGET
            // CHECKPOINT_INTERVAL
        )
    )

    assert (
        adaptive_checkpoints[-1].cycle
        == cut_cycle
    )

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

    summary = telemetry.finalize(
        termination_reason=(
            "instruction_budget_reached"
        ),
        executed_instructions=(
            ACCEPTED_BUDGET
        ),
        final_l1_intent_count=(
            l1_intent_count
        ),
        final_l1_validated_count=(
            l1_validated_count
        ),
        final_l2_intent_count=(
            l2_intent_count
        ),
        final_l2_validated_count=(
            l2_validated_count
        ),
        decision_state=decision_engine,
    )

    assert len(adaptive_summaries) == 1
    assert adaptive_summaries[0] == summary

    # End authoritative full-system benchmark window only
    # after final adaptive telemetry has been finalized.
    peak_rss_kib = (
        read_proc_status_kib(
            "VmHWM"
        )
    )

    elapsed_ns = wall_ns()

    assert elapsed_ns > 0

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

    auc_points = tuple(
        L2IntentCheckpoint(
            accepted=(
                record.executed_instructions
            ),
            l2_intent_bins=(
                record.l2_intent_count
            ),
        )
        for record
        in adaptive_checkpoints
    )

    normalized_auc = (
        normalized_l2_intent_auc(
            auc_points,
            n_max=ACCEPTED_BUDGET,
            checkpoint_interval=CHECKPOINT_INTERVAL,
        )
    )

    final_checkpoint = (
        adaptive_checkpoints[-1]
    )

    assert (
        final_checkpoint.l1_intent_count
        == l1_intent_count
    )

    assert (
        final_checkpoint.l1_validated_count
        == l1_validated_count
    )

    assert (
        final_checkpoint.l2_intent_count
        == l2_intent_count
    )

    assert (
        final_checkpoint.l2_validated_count
        == l2_validated_count
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

    if (
        functional.failed_count > 0
        or performance.failed_count > 0
    ):
        run_status = (
            "VALID_DUT_FAILURE_NONTERMINAL"
        )
    else:
        run_status = "COMPLETED"

    if functional.failed_count:
        dut._log.error(
            "W13_ADAPTIVE_FUNCTIONAL_FAILURE_SUMMARY "
            f"count={functional.failed_count} "
            f"diagnostics="
            f"{functional_failure_diagnostics}"
        )

    if performance.failed_count:
        dut._log.error(
            "W13_ADAPTIVE_PERFORMANCE_FAILURE_SUMMARY "
            f"count={performance.failed_count} "
            f"diagnostics="
            f"{performance_failure_diagnostics}"
        )

    telemetry_record = {
        "schema_version": (
            PILOT_SCHEMA_VERSION
        ),
        "method": "M3-Adaptive-CGS",
        "phase": "reproducibility_qualification",

        "seed": ROOT_SEED,

        "configuration": {
            "config_id": CONFIG_ID,
            "epsilon": EPSILON,
            "alpha": ALPHA,
            "q_floor": Q_FLOOR,
            "nominal_batch": (
                NOMINAL_BATCH
            ),
            "accepted_budget": (
                ACCEPTED_BUDGET
            ),
            "checkpoint_interval": (
                CHECKPOINT_INTERVAL
            ),
        },

        "rng": {
            "seed_domain": (
                ADAPTIVE_SEED_DOMAIN
            ),
            "root_seed": (
                campaign_seeds.root_seed
            ),
            "decision_seed": (
                campaign_seeds.decision_seed
            ),
            "target_seed": (
                campaign_seeds.target_seed
            ),
            "realization_seed": (
                campaign_seeds
                .realization_seed
            ),
        },

        "provenance": {
            "dut_revision": DUT_REVISION,
            "harness_revision": (
                harness_revision
            ),
            "protocol_revision": (
                PROTOCOL_REVISION
            ),
            "adaptive_stack_revision": (
                adaptive_stack_revision
            ),
            "pilot_contract_revision": (
                pilot_contract_revision
            ),
            "pilot_metrics_revision": (
                pilot_metrics_revision
            ),
            "git_dirty": False,
        },

        "runtime_environment": (
            runtime_environment
        ),

        "status": run_status,

        "terminal_divergence_status": (
            "NOT_OBSERVED"
        ),

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
            "ordinary_fixed_n_inference": (
                True
            ),
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
            "completed_epochs": (
                epoch_completion_count
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
            "failure_diagnostics": (
                functional_failure_diagnostics
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
            "failure_diagnostics": (
                performance_failure_diagnostics
            ),
        },

        "coverage": {
            "denominator": (
                ACCEPTED_BUDGET
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
                l2_live.validated_hit_count
            ),
            "l2_rejected_hits": (
                l2_live.rejected_hit_count
            ),
            "l2_pending_hits": (
                l2_live.pending_hit_count
            ),

            "max_intent_consumer_id": (
                max_intent_consumer_id
            ),
            "checkpoint_count": len(
                adaptive_checkpoints
            ),
            "checkpoints": [
                asdict(record)
                for record
                in adaptive_checkpoints
            ],
        },

        "adaptive": {
            "completed_epochs": (
                epoch_completion_count
            ),
            "epoch_records": [
                asdict(record)
                for record
                in adaptive_epochs
            ],
            "checkpoint_records": [
                asdict(record)
                for record
                in adaptive_checkpoints
            ],
            "summary": asdict(summary),

            "selection_metric": {
                "normalized_l2_intent_auc": (
                    normalized_auc
                ),
                "l2_intent_bins_at_10000": (
                    final_checkpoint
                    .l2_intent_count
                ),
            },
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

    telemetry_record[
        "reproducibility"
    ] = {
        "repetition": REPETITION,
        "contract_sha256": (
            CONTRACT_SHA256
        ),
        **repro_trace.snapshot(),
    }

    write_json_atomic(
        RESULT_PATH,
        telemetry_record,
    )

    dut._log.info(
        "W15_ADAPTIVE_REPRO_RESULT "
        f"status={run_status} "
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
        f"l2_validated={l2_validated_count} "
        f"auc={normalized_auc:.9f} "
        f"wall_ns={elapsed_ns} "
        f"accepted_per_s="
        f"{accepted_per_second:.2f} "
        f"cycles_per_s="
        f"{cycles_per_second:.2f} "
        f"peak_rss_kib={peak_rss_kib} "
        f"checkpoints="
        f"{len(adaptive_checkpoints)} "
        f"telemetry={RESULT_PATH}"
    )
