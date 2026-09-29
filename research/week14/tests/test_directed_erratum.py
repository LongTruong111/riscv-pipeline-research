from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

ATTEMPT = (
    ROOT
    / "research/week14/results/"
    "attempt1_preregistered"
)

ERRATUM = (
    ROOT
    / "research/week14/preflight/"
    "directed_preregistration_erratum.json"
)

PREREG = (
    ROOT
    / "research/week14/preflight/"
    "directed_expected_rejections.json"
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


def load(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def test_original_preregistration_is_not_rewritten():
    p = load(PREREG)

    assert p["status"] == (
        "PREREGISTERED_PRE_DUT"
    )

    assert p[
        "expected_rejection_test_ids"
    ] == ["T18"]


def test_attempt1_artifacts_are_exact():
    result = (
        ATTEMPT
        / "directed_final.json"
    )

    evidence = (
        ATTEMPT
        / "directed_final_evidence.txt"
    )

    assert sha256(result) == (
        "16765633d033b369559745a8e903e7a0"
        "b20367113ce7b3c4f1606112cf1d761c"
    )

    assert sha256(evidence) == (
        "2ca23a9b3cab82754a609dd555ec83e50"
        "eb124b590a678cbbab9a5a9b24d9dc1"
    )


def test_attempt1_remains_fail():
    d = load(
        ATTEMPT
        / "directed_final.json"
    )

    assert d["intent_count"] == 20
    assert d["validated_count"] == 18
    assert d["overall_pass"] is False

    assert d[
        "expected_rejection_keys"
    ] == [["T18", "H18"]]

    assert d[
        "observed_rejection_keys"
    ] == [
        ["T18", "H18"],
        ["T19", "H18"],
        ["T19", "H19"],
    ]


def test_erratum_is_explicitly_post_falsification():
    d = load(ERRATUM)

    assert d["status"] == (
        "POST_FALSIFICATION_ERRATUM"
    )

    assert d["non_retroactive"] is True

    corrected = d[
        "corrected_directed_characterization"
    ]

    assert corrected["intent"] == "20/20"
    assert corrected["validated"] == "18/20"

    assert corrected[
        "designated_rejected_cases"
    ] == [
        "T18",
        "T19",
    ]

    assert corrected[
        "original_gate_attempt_"
        "reclassified_as_pass"
    ] is False


def test_h19_and_h20_are_not_conflated():
    d = load(ERRATUM)

    static = d["static_evidence"]

    assert static[
        "hazard_detection_has_source_use"
    ] is True

    assert static[
        "hazard_detection_has_rd_x0_exclusion"
    ] is False

    assert static[
        "fresh_rebuild_reproduced_t19"
    ] is True

    assert static[
        "fresh_rebuild_t20_passed"
    ] is True
