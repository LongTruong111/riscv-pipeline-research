from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

HARNESS = (
    ROOT
    / "research/week14/weighted_random/rtl/"
    "test_m2_preflight_exact_cut.py"
)

PROVENANCE = (
    ROOT
    / "research/week14/weighted_random/rtl/"
    "HARNESS_PROVENANCE.json"
)

M1 = (
    ROOT
    / "research/week13/pure_random/rtl/"
    "test_m1_preflight_exact_cut.py"
)


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
    ).strip()


def test_source_provenance_is_gate_t13():
    d = json.loads(
        PROVENANCE.read_text(
            encoding="utf-8"
        )
    )

    assert d["status"] == (
        "FROZEN_BEFORE_RTL_SMOKE"
    )

    assert d[
        "derived_from"
    ]["gate_t13_commit"] == git(
        "rev-parse",
        "GATE_T13_COMPLETE^{commit}",
    )

    assert d[
        "derived_from"
    ]["git_blob"] == git(
        "hash-object",
        str(M1),
    )


def test_m2_kat_is_exact():
    d = json.loads(
        PROVENANCE.read_text(
            encoding="utf-8"
        )
    )

    smoke = d["smoke_contract"]

    assert smoke["seed"] == 14001
    assert smoke[
        "accepted_budget"
    ] == 1000

    assert smoke["plan_hash"] == (
        "3b23d6e4887e305100542416c77f9399"
        "4b229c9f9dab91ac4c0ac9f86465d2c9"
    )

    assert smoke["block_count"] == 405
    assert smoke[
        "image_word_count"
    ] == 1048

    assert smoke[
        "last_logical_generation"
    ] == 8

    assert smoke[
        "final_block_partial"
    ] is False

    assert smoke[
        "final_campaign_seed"
    ] is False


def test_m1_specific_plan_logic_is_absent():
    text = HARNESS.read_text(
        encoding="utf-8"
    )

    forbidden = (
        "generate_pure_random_plan",
        "build_runtime_entries",
        "realized.family",
        "EXPECTED_FAMILIES",
        "EXPECTED_FINAL_PC",
        "plan.final_expected_pc",
        "expected_accepted_families",
        "discard_unexecuted_suffix",
        "W13_M1_",
    )

    for token in forbidden:
        assert token not in text


def test_common_checker_cut_stack_is_preserved():
    text = HARNESS.read_text(
        encoding="utf-8"
    )

    for token in (
        "ExecutionEventAdapter",
        "RetireMonitor",
        "StreamingFunctionalScoreboard",
        "StreamingPerformanceMonitor",
        "WrapAwareRV32ArchitecturalModel",
        "WrapAwareMutableTimingOracleV1",
        "CampaignInvariantLedger",
        "CampaignCutDriver",
        "build_campaign_lifecycle_snapshot",
        "PureRandomRuntimeWindow",
    ):
        assert token in text


def test_complete_boundary_cleanup_is_explicit():
    text = HARNESS.read_text(
        encoding="utf-8"
    )

    assert (
        "assert not "
        "plan.blocks[-1].is_partial"
        in text
    )

    assert (
        "assert not "
        "final_plan_block.is_partial"
        in text
    )

    assert (
        "window.pending_entry_count"
        in text
    )

    assert (
        "== 0"
        in text
    )

    assert (
        "discard_unexecuted_suffix"
        not in text
    )


def test_no_adaptive_feedback_policy_imported():
    tree = ast.parse(
        HARNESS.read_text(
            encoding="utf-8"
        )
    )

    forbidden_names = {
        "RegisterTargetPolicy",
        "BanditDecisionEngine",
        "AdaptiveEpochCoordinator",
    }

    for node in ast.walk(tree):
        if not isinstance(
            node,
            ast.ImportFrom,
        ):
            continue

        for alias in node.names:
            assert (
                alias.name
                not in forbidden_names
            )
