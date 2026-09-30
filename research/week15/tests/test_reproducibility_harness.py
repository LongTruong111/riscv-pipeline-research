from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.week5.impl.execution_event import (
    ExecutionEvent,
)
from research.week10.adaptive.campaign_telemetry import (
    CampaignCheckpointRecord,
    EpochTelemetryRecord,
)
from research.week15.reproducibility.run_reproducibility import (
    compare_pair,
    qualification_plan,
)
from research.week15.reproducibility.runtime_config import (
    load_runtime_config,
)
from research.week15.reproducibility.runtime_trace import (
    ReproTraceSession,
)


ROOT = Path(__file__).resolve().parents[3]

CONTRACT = (
    ROOT
    / "research/week15/contracts/"
    "adaptive_cgs_freeze.yaml"
)

HARNESS = (
    ROOT
    / "research/week15/rtl/"
    "test_adaptive_reproducibility.py"
)


def contract() -> dict:
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8"
        )
    )


def epoch_record(
    mode: str = "epsilon_exploration",
) -> EpochTelemetryRecord:
    return EpochTelemetryRecord(
        schema_version="week10-adaptive-v1",
        checkpoint_semantics=(
            "post_instruction_cut_v1"
        ),
        epoch_index=0,
        selected_arm="A0",
        selection_mode=mode,
        candidate_arms=(
            "A0",
            "A1",
        ),
        target_d1=7,
        target_d2=None,
        first_executed_instruction=1,
        last_executed_instruction=500,
        actual_executed_instructions=500,
        covered_at_epoch_start_count=0,
        global_observed_l2_intent_count=1,
        attributable_observed_l2_intent_count=1,
        global_new_l2_intent_count=1,
        attributable_new_l2_intent_count=1,
        reward=2.0,
        q_value_before=0.0,
        max_q_before=0.0,
        old_q=0.0,
        new_q=1.0,
        pull_count=1,
        q_values_after=(
            ("A0", 1.0),
            ("A1", 0.0),
        ),
        pull_counts_after=(
            ("A0", 1),
            ("A1", 0),
        ),
        recent_rewards_after=(
            ("A0", 2.0),
            ("A1", 0.0),
        ),
    )


def checkpoint_record() -> CampaignCheckpointRecord:
    return CampaignCheckpointRecord(
        schema_version="week10-adaptive-v1",
        checkpoint_semantics=(
            "post_instruction_cut_v1"
        ),
        executed_instructions=1000,
        cycle=1100,
        l1_intent_count=17,
        l1_validated_count=16,
        l2_intent_count=40,
        l2_validated_count=39,
        epoch_index=2,
        q_values=(
            ("A0", 1.0),
        ),
        pull_counts=(
            ("A0", 1),
        ),
        recent_rewards=(
            ("A0", 2.0),
        ),
    )


def test_qualification_plan_is_exactly_six_fresh_runs():
    assert qualification_plan(
        contract()
    ) == [
        {
            "seed": 15001,
            "accepted_budget": 10000,
            "repetition": "A",
        },
        {
            "seed": 15001,
            "accepted_budget": 10000,
            "repetition": "B",
        },
        {
            "seed": 15002,
            "accepted_budget": 10000,
            "repetition": "A",
        },
        {
            "seed": 15002,
            "accepted_budget": 10000,
            "repetition": "B",
        },
        {
            "seed": 15003,
            "accepted_budget": 100000,
            "repetition": "A",
        },
        {
            "seed": 15003,
            "accepted_budget": 100000,
            "repetition": "B",
        },
    ]


def test_runtime_config_accepts_only_frozen_matrix(tmp_path):
    env = {
        "W15_REPRO_SEED": "15003",
        "W15_REPRO_BUDGET": "100000",
        "W15_REPRO_REPETITION": "B",
        "W15_REPRO_RESULT_DIR": str(
            tmp_path
        ),
    }

    cfg = load_runtime_config(
        env
    )

    assert cfg.root_seed == 15003
    assert cfg.accepted_budget == 100000
    assert cfg.repetition == "B"

    assert cfg.epsilon == 0.10
    assert cfg.alpha == 0.5
    assert cfg.q_floor == 0.05
    assert cfg.nominal_batch == 500
    assert cfg.checkpoint_interval == 1000


@pytest.mark.parametrize(
    (
        "seed",
        "budget",
        "repetition",
    ),
    [
        (3001, 100000, "A"),
        (15001, 100000, "A"),
        (15003, 10000, "A"),
        (15001, 10000, "C"),
    ],
)
def test_runtime_config_rejects_nonmatrix_runs(
    tmp_path,
    seed,
    budget,
    repetition,
):
    env = {
        "W15_REPRO_SEED": str(seed),
        "W15_REPRO_BUDGET": str(budget),
        "W15_REPRO_REPETITION": (
            repetition
        ),
        "W15_REPRO_RESULT_DIR": str(
            tmp_path
        ),
    }

    with pytest.raises(
        ValueError,
        match="outside frozen",
    ):
        load_runtime_config(
            env
        )


def test_trace_session_records_actual_execution_event():
    trace = ReproTraceSession()

    event = ExecutionEvent(
        instruction_index=1,
        cycle=10,
        pc=0x20,
        instruction=0x12345678,
        rs1=0,
        rs2=0,
        rd=1,
        uses_rs1=False,
        uses_rs2=False,
        writes_rd=True,
        producer_type="ALU",
        consumer_type="NONE",
    )

    trace.record_instruction_event(
        event
    )

    snapshot = trace.snapshot()

    assert (
        snapshot["trace_record_counts"]
        ["instruction_stream"]
        == 1
    )


def test_trace_session_counts_selection_modes_descriptively():
    trace = ReproTraceSession()

    trace.record_epoch(
        epoch_record(
            "epsilon_exploration"
        )
    )

    snapshot = trace.snapshot()

    assert (
        snapshot["selection_counts"]
        ["epsilon_exploration"]
        == 1
    )

    assert (
        snapshot["selection_counts"]
        ["greedy_exploitation"]
        == 0
    )

    assert (
        snapshot["selection_counts"]
        ["q_floor_uniform"]
        == 0
    )


def test_trace_session_streams_checkpoint():
    trace = ReproTraceSession()

    trace.record_checkpoint(
        checkpoint_record()
    )

    assert (
        trace.snapshot()
        ["trace_record_counts"]
        ["coverage_trace"]
        == 1
    )


def test_pair_comparison_gates_only_contract_required_traces():
    c = contract()

    required = (
        c["freeze"]
        ["trace_schema"]
        ["gate_required_traces"]
    )

    supplemental = (
        c["freeze"]
        ["trace_schema"]
        ["supplemental_traces"]
    )

    hashes_a = {
        name: "a" * 64
        for name in required
    }

    hashes_b = dict(
        hashes_a
    )

    for name in supplemental:
        hashes_a[name] = "b" * 64
        hashes_b[name] = "c" * 64

    a = {
        "reproducibility": {
            "trace_digests": hashes_a,
        }
    }

    b = {
        "reproducibility": {
            "trace_digests": hashes_b,
        }
    }

    result = compare_pair(
        a,
        b,
        contract=c,
    )

    assert (
        result["gate_required_equal"]
        is True
    )

    assert (
        result["supplemental_equal"]
        is False
    )


def test_required_trace_difference_fails_pair():
    c = contract()

    names = (
        c["freeze"]
        ["trace_schema"]
        ["gate_required_traces"]
        +
        c["freeze"]
        ["trace_schema"]
        ["supplemental_traces"]
    )

    hashes_a = {
        name: "a" * 64
        for name in names
    }

    hashes_b = dict(
        hashes_a
    )

    hashes_b[
        "instruction_stream"
    ] = "f" * 64

    a = {
        "reproducibility": {
            "trace_digests": hashes_a,
        }
    }

    b = {
        "reproducibility": {
            "trace_digests": hashes_b,
        }
    }

    result = compare_pair(
        a,
        b,
        contract=c,
    )

    assert (
        result["gate_required_equal"]
        is False
    )


def test_generated_harness_contains_frozen_trace_hook_order():
    source = HARNESS.read_text(
        encoding="utf-8"
    )

    identity = source.index(
        "READ-ONLY PLANNED-STREAM PREVALIDATION"
    )

    owner = source.index(
        "logical_owner ="
    )

    trace = source.index(
        "WEEK15 CANONICAL "
        "ACCEPTED-INSTRUCTION TRACE"
    )

    timing = source.index(
        "TIMING / ARCHITECTURE EXPECTATIONS"
    )

    exact_cut = source.index(
        "EXACT CUT — PRIORITY OVER REFILL"
    )

    assert (
        identity
        < owner
        < trace
        < timing
        < exact_cut
    )


def test_generated_harness_does_not_use_week13_runtime_seed_overrides():
    source = HARNESS.read_text(
        encoding="utf-8"
    )

    assert (
        "W13_ADAPTIVE_SEED"
        not in source
    )

    assert (
        "W13_ADAPTIVE_EPSILON"
        not in source
    )

    assert (
        "W13_ADAPTIVE_ALPHA"
        not in source
    )

    assert (
        "W13_ADAPTIVE_BATCH"
        not in source
    )


def test_week15_rtl_makefile_resolves_repo_root_at_correct_depth():
    makefile = (
        ROOT
        / "research/week15/rtl/Makefile"
    )

    source = makefile.read_text(
        encoding="utf-8"
    )

    assert (
        "REPO_ROOT := "
        "$(abspath $(THIS_DIR)/../../..)"
        in source
    )

    assert (
        "REPO_ROOT := "
        "$(abspath $(THIS_DIR)/../../../..)"
        not in source
    )

    resolved = (
        makefile.parent
        / "../../.."
    ).resolve()

    assert resolved == ROOT

    assert (
        resolved
        / "design/RegPack.sv"
    ).is_file()

    assert (
        resolved
        / (
            "research/week10/rtl/"
            "adaptive_execution_stream_tb.sv"
        )
    ).is_file()



def test_week15_python_harness_resolves_repo_root_at_correct_depth():
    harness = (
        ROOT
        / "research/week15/rtl/"
        "test_adaptive_reproducibility.py"
    )

    source = harness.read_text(
        encoding="utf-8"
    )

    correct = """REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)
"""

    inherited_wrong = """REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[4]
)
"""

    assert correct in source
    assert inherited_wrong not in source

    assert (
        harness.resolve().parents[3]
        == ROOT
    )

    assert (
        ROOT / ".git"
    ).exists()

    assert (
        ROOT / "design/RegPack.sv"
    ).is_file()
