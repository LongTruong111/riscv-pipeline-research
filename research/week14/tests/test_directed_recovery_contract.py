from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

RECOVERY = (
    ROOT
    / "research/week14/preflight/"
    "directed_recovery_contract.json"
)

PREREG = (
    ROOT
    / "research/week14/preflight/"
    "directed_expected_rejections.json"
)

ERRATUM = (
    ROOT
    / "research/week14/preflight/"
    "directed_preregistration_erratum.json"
)


def load(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def test_original_preregistration_remains_unchanged():
    d = load(PREREG)

    assert d[
        "expected_rejection_test_ids"
    ] == ["T18"]


def test_recovery_contract_is_explicitly_nonretroactive():
    d = load(RECOVERY)

    assert d[
        "created_after_falsification"
    ] is True

    assert d[
        "is_original_preregistration"
    ] is False

    assert d["non_retroactive"] is True

    assert d[
        "historical_status"
    ][
        "original_preregistered_attempt"
    ] == "FAIL"

    assert d[
        "historical_status"
    ][
        "may_be_reclassified_as_pass"
    ] is False


def test_corrected_defect_set_is_exact():
    d = load(RECOVERY)

    defects = {
        item["root_cause_id"]
        for item in d[
            "known_defect_confirmation"
        ]
    }

    assert defects == {
        "REGFILE_X0_WRITE",
        "LOAD_RD_X0_FALSE_STALL",
    }

    assert d[
        "required_validated_cases"
    ] == [
        f"T{i:02d}"
        for i in range(1, 21)
        if i not in (18, 19)
    ]

    assert d[
        "normative_directed_contract"
    ]["expected_validated"] == "18/20"


def test_t19_normative_and_defect_behavior_are_separate():
    d = load(RECOVERY)

    t19 = next(
        item
        for item in d[
            "known_defect_confirmation"
        ]
        if item["test_id"] == "T19"
    )

    # Correct architectural timing is NOT rewritten.
    assert t19[
        "normative_control"
    ]["stall_cycles"] == 0

    # Frozen-DUT defect signature is recorded separately.
    assert t19[
        "required_observed_signature"
    ]["observed_stall_cycles"] == 1

    assert t19[
        "required_observed_signature"
    ]["architectural_failures"] == 0

    assert set(
        t19[
            "required_observed_signature"
        ]["control_failure_bins"]
    ) == {
        "H18",
        "H19",
    }

    assert t19[
        "correlation_rule"
    ]["root_cause_count"] == 1


def test_final_status_cannot_hide_falsification():
    d = load(RECOVERY)

    gate = d["gate_semantics"]

    assert gate[
        "confirmation_success_label"
    ] == (
        "PASS_POST_ERRATUM_CONFIRMATION"
    )

    assert gate[
        "eligible_final_gate_status_if_all_"
        "remaining_week14_obligations_pass"
    ] == "RECOVERED_WITH_ERRATUM"

    assert gate[
        "plain_PASS_is_prohibited"
    ] is True

    erratum = load(ERRATUM)

    assert erratum[
        "corrected_directed_characterization"
    ][
        "original_gate_attempt_reclassified_as_pass"
    ] is False
