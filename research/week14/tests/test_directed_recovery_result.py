from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

RESULT = (
    ROOT
    / "research/week14/results/"
    "recovery_confirmation/"
    "directed_recovery_confirmation.json"
)

EVIDENCE = (
    ROOT
    / "research/week14/results/"
    "recovery_confirmation/"
    "directed_recovery_confirmation_evidence.txt"
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


def load_result() -> dict:
    return json.loads(
        RESULT.read_text(encoding="utf-8")
    )


def test_confirmation_artifact_hashes():
    assert sha256(RESULT) == (
        "04c7cb22fa725dd76a57fb0f3c69676c"
        "0a942e14434eebcc6a69d710b67332ec"
    )

    assert sha256(EVIDENCE) == (
        "907a622c6825af3e4c7f4bd82061b1c5"
        "5038823dc513c2199a5276b68d615597"
    )


def test_confirmation_status():
    d = load_result()

    assert d["status"] == (
        "PASS_POST_ERRATUM_CONFIRMATION"
    )

    assert d[
        "confirmation_contract_pass"
    ] is True

    assert d[
        "historical_original_attempt"
    ] == "FAIL"

    assert d[
        "original_attempt_reclassified"
    ] is False


def test_directed_coverage_result():
    d = load_result()

    assert d["case_count"] == 20
    assert d["intent_count"] == 20
    assert d["validated_count"] == 18

    assert d[
        "attribution_exercised_count"
    ] == 20

    assert d[
        "control_oracle_exercised_count"
    ] == 20

    assert d[
        "architectural_oracle_exercised_count"
    ] == 20


def test_known_root_causes_are_exact():
    d = load_result()

    assert d[
        "observed_root_causes"
    ] == [
        "REGFILE_X0_WRITE",
        "LOAD_RD_X0_FALSE_STALL",
    ]

    assert d["missing_root_causes"] == []
    assert d["unexpected_root_causes"] == []
    assert d["unexpected_rejected_cases"] == []
    assert d[
        "missing_required_validated_cases"
    ] == []


def test_case_partition_is_exact():
    d = load_result()

    cases = {
        item["test_id"]: item
        for item in d["cases"]
    }

    assert set(cases) == {
        f"T{i:02d}"
        for i in range(1, 21)
    }

    for i in range(1, 21):
        test_id = f"T{i:02d}"
        case = cases[test_id]

        assert case["pass"] is True
        assert case["issues"] == []

        if test_id in {"T18", "T19"}:
            assert case[
                "target_validated"
            ] == 0
        else:
            assert case[
                "target_validated"
            ] == 1

    assert cases["T18"][
        "root_cause_id"
    ] == "REGFILE_X0_WRITE"

    assert cases["T19"][
        "root_cause_id"
    ] == "LOAD_RD_X0_FALSE_STALL"

    assert cases["T19"][
        "normative_stall_cycles"
    ] == 0

    assert cases["T19"][
        "observed_defective_stall_cycles"
    ] == 1
