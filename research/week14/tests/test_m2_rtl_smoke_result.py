from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

RESULT = (
    ROOT
    / "research/week14/results/"
    "m2_rtl_smoke/"
    "seed14001_n1000.json"
)

LOG = (
    ROOT
    / "research/week14/results/"
    "m2_rtl_smoke/"
    "seed14001_n1000.log"
)

STATIC_SMOKE = (
    ROOT
    / "research/week14/results/"
    "m2_static_smoke/"
    "weighted_plan_seed14001.json"
)

RUNTIME_PREFLIGHT = (
    ROOT
    / "research/week14/results/"
    "m2_static_smoke/"
    "runtime_compatibility_seed14001.json"
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


def test_rtl_evidence_hashes_are_exact():
    assert sha256(RESULT) == (
        "54a4ed801f9b7d64bd3ad5a7a2def796"
        "44ffa81ca88eb5975a9e6e87e02be52d"
    )

    assert sha256(LOG) == (
        "b18b917f84b0af6a6a824ed76ccabd7b"
        "2a7aaca45af85ca78c04ddd804a9a1c4"
    )


def test_smoke_status_and_provenance():
    d = load(RESULT)

    assert d["method"] == "M2-WR"
    assert d["seed"] == 14001
    assert d["accepted_budget"] == 1000

    assert d["harness_commit"] == (
        "e651878db8c071943f1ed1d9ae687eb5"
        "af5f19be"
    )

    assert d["make_returncode"] == 0
    assert d["pass_telemetry_found"] is True
    assert d["overall_pass"] is True

    assert d[
        "final_campaign_executed"
    ] is False


def test_all_machine_contract_checks_pass():
    d = load(RESULT)

    assert d["contract_checks"] == {
        "accepted": True,
        "bounded_runtime": True,
        "patched_words": True,
        "plan_hash": True,
        "seed": True,
    }


def test_plan_identity_matches_static_freeze():
    rtl = load(RESULT)["telemetry"]
    static = load(STATIC_SMOKE)

    assert rtl["seed"] == static["seed"]
    assert (
        rtl["accepted"]
        == static["accepted"]
        == 1000
    )

    assert (
        rtl["plan_hash"]
        == static["plan_hash"]
        == (
            "3b23d6e4887e305100542416c77f9399"
            "4b229c9f9dab91ac4c0ac9f86465d2c9"
        )
    )

    assert rtl["patched_words"] == (
        static["image_word_count"]
    )

    assert rtl["released_entries"] == (
        static["block_count"]
    )


def test_runtime_and_exact_cut_are_coherent():
    rtl = load(RESULT)["telemetry"]
    preflight = load(RUNTIME_PREFLIGHT)

    assert rtl["accepted"] == 1000

    assert (
        rtl["retired"]
        + rtl["in_flight"]
        == rtl["accepted"]
    )

    assert rtl["max_resident_words"] <= 128

    assert (
        rtl["max_resident_words"]
        == preflight[
            "max_resident_words"
        ]
        == 128
    )

    assert rtl["patched_words"] == 1048
    assert rtl["released_entries"] == 405


def test_checker_and_coverage_smoke_is_clean():
    rtl = load(RESULT)["telemetry"]

    assert (
        rtl["l1_intent"]
        == rtl["l1_validated"]
        == 17
    )

    assert (
        rtl["l2_intent"]
        == rtl["l2_validated"]
        == 62
    )

    log = LOG.read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert (
        "W14_M2_PREFLIGHT=PASS"
        in log
    )

    assert (
        "TESTS=1 PASS=1 FAIL=0 SKIP=0"
        in log
    )

    assert (
        "W14_M2_FUNCTIONAL_FAILURE"
        not in log
    )

    assert (
        "W14_M2_PERFORMANCE_FAILURE"
        not in log
    )

    assert (
        "W14_M2_ACCEPT_TIMING_DIVERGENCE"
        not in log
    )
