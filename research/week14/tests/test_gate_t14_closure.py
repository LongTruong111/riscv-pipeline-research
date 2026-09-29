from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

CLOSURE = (
    ROOT
    / "research/week14/"
    "GATE_T14_CLOSURE.json"
)

ATTEMPT1 = (
    ROOT
    / "research/week14/results/"
    "attempt1_preregistered/"
)

RECOVERY = (
    ROOT
    / "research/week14/results/"
    "recovery_confirmation/"
)

M2 = (
    ROOT
    / "research/week14/results/"
    "m2_rtl_smoke/"
)


def load(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(65536),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
    ).strip()


def test_gate_status_is_recovered_with_erratum():
    d = load(CLOSURE)

    assert d["schema"] == (
        "week14.gate-t14-closure.v1"
    )

    assert d["status"] == (
        "RECOVERED_WITH_ERRATUM"
    )

    assert d[
        "plain_pass_prohibited"
    ] is True

    assert d[
        "gate_decision"
    ]["final_status"] == (
        "RECOVERED_WITH_ERRATUM"
    )


def test_original_directed_failure_is_not_rewritten():
    d = load(CLOSURE)
    m0 = d["directed"]

    assert m0[
        "original_preregistered_attempt"
    ] == "FAIL"

    assert m0[
        "original_attempt_reclassified"
    ] is False

    assert m0[
        "confirmation_status"
    ] == "PASS_POST_ERRATUM_CONFIRMATION"

    assert m0["intent"] == "20/20"
    assert m0["validated"] == "18/20"

    assert m0["known_root_causes"] == [
        "REGFILE_X0_WRITE",
        "LOAD_RD_X0_FALSE_STALL",
    ]


def test_directed_evidence_hashes_are_exact():
    d = load(CLOSURE)["directed"]

    assert sha256(
        ATTEMPT1
        / "directed_final.json"
    ) == d["attempt1_result_sha256"]

    assert sha256(
        ATTEMPT1
        / "directed_final_evidence.txt"
    ) == d["attempt1_evidence_sha256"]

    assert sha256(
        RECOVERY
        / "directed_recovery_confirmation.json"
    ) == d["recovery_result_sha256"]

    assert sha256(
        RECOVERY
        / "directed_recovery_confirmation_evidence.txt"
    ) == d["recovery_evidence_sha256"]


def test_m1_m2_final_campaigns_remain_future_work():
    d = load(CLOSURE)

    m1 = d["m1_pure_random"]
    m2 = d["m2_weighted_random"]

    assert m1[
        "final_campaign_executed_in_week14"
    ] is False

    assert m2[
        "final_campaign_executed_in_week14"
    ] is False

    assert m1[
        "accepted_budget_per_final_seed"
    ] == 100000

    assert m2[
        "accepted_budget_per_final_seed"
    ] == 100000

    assert m1["final_seeds"] == list(
        range(1001, 1016)
    )

    assert m2["final_seeds"] == list(
        range(2001, 2016)
    )


def test_m2_evidence_and_config_are_exact():
    d = load(CLOSURE)
    m2 = d["m2_weighted_random"]
    smoke = m2["rtl_smoke"]

    assert sha256(
        ROOT
        / "research/week14/configs/"
        "m2_weighted_random.yaml"
    ) == m2["config_sha256"]

    assert sha256(
        M2 / "seed14001_n1000.json"
    ) == smoke["result_sha256"]

    assert sha256(
        M2 / "seed14001_n1000.log"
    ) == smoke["log_sha256"]

    assert smoke["status"] == "PASS"
    assert smoke["seed"] == 14001
    assert smoke["accepted"] == 1000

    assert smoke[
        "l1_intent"
    ] == smoke["l1_validated"] == 17

    assert smoke[
        "l2_intent"
    ] == smoke["l2_validated"] == 62


def test_protected_trees_match_audit_base():
    d = load(CLOSURE)

    base = d[
        "authority"
    ]["audit_base_commit"]

    for path, expected in d[
        "protected_trees"
    ].items():
        observed = git(
            "rev-parse",
            f"{base}:{path}",
        )

        assert observed == expected


def test_gate_t13_and_audit_base_are_ancestors():
    d = load(CLOSURE)

    head = git("rev-parse", "HEAD")

    for commit in (
        d["authority"]["gate_t13_commit"],
        d["authority"]["audit_base_commit"],
    ):
        subprocess.check_call(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                commit,
                head,
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def test_scope_limitations_are_explicit():
    d = load(CLOSURE)
    limits = d["limitations"]

    assert limits[
        "final_comparative_campaign_executed"
    ] is False

    assert limits[
        "jalr_lsb_defect_activated_by_canonical_directed_suite"
    ] is False

    assert limits[
        "positive_stochastic_rd_x0_generation_enabled"
    ] is False

    assert limits[
        "directed_known_rejected_cases"
    ] == [
        "T18",
        "T19",
    ]
