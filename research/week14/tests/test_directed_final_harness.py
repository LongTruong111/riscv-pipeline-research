from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

MODULE_PATH = (
    ROOT
    / "research/week14/directed/"
    "run_directed_final.py"
)

SPEC = importlib.util.spec_from_file_location(
    "week14_directed_final",
    MODULE_PATH,
)

assert SPEC is not None
assert SPEC.loader is not None

mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


AUDIT = mod.load_json(mod.AUDIT_PATH)
PREREG = mod.load_json(mod.PREREG_PATH)

SPECS = {
    row["test_id"]: row
    for row in AUDIT["cases"]
}


def normal_log(
    test_id: str,
    target: str,
    accepted: int,
    stall: int = 0,
    redirect: int = 0,
) -> str:
    arch_checks = accepted * 4

    return f"""
[{test_id} -> {target}] running ... PASS
EXECUTION_STREAM_SMOKE cycles=60 accepted={accepted} accepted_after_stall={stall} stall_cycles={stall} flush_cycles={redirect} unsupported_cycles=0 l1_intent_bins=1 l1_seen={target} l2_intent_bins=1 control_checks=1 control_passes=1 control_failures=0 control_failed_bins=none architectural_checks={arch_checks} architectural_passes={arch_checks} architectural_failures=0 architectural_failure_kinds=none l1_validated_bins=1 l1_validated_seen={target} validation_attempts=1 validated_hits=1 rejected_hits=0 validation_pending=0 target_l1_validated=1
    oracle: stall={stall} redirect={redirect}
"""


def t18_known_log() -> str:
    return """
[T18 -> H18] running ... PASS
EXECUTION_STREAM_SMOKE cycles=60 accepted=2 accepted_after_stall=0 stall_cycles=0 flush_cycles=0 unsupported_cycles=0 l1_intent_bins=1 l1_seen=H18 l2_intent_bins=0 control_checks=1 control_passes=1 control_failures=0 control_failed_bins=none architectural_checks=8 architectural_passes=6 architectural_failures=2 architectural_failure_kinds=x0 l1_validated_bins=0 l1_validated_seen=none validation_attempts=1 validated_hits=0 rejected_hits=1 validation_pending=0 target_l1_validated=0
65.00ns WARNING ARCHITECTURAL_REALIZATION_FAIL kind=x0 instruction_index=1 checks=architectural_x0:expected=0x0,observed=0x7
75.00ns WARNING ARCHITECTURAL_REALIZATION_FAIL kind=x0 instruction_index=2 checks=architectural_x0:expected=0x0,observed=0x7
75.00ns INFO L1_VALIDATION_REJECT bin=H18 consumer_index=2 reason=architectural failed_arch=1:x0,2:x0
    oracle: stall=0 redirect=0
"""


def classify(test_id: str, text: str):
    observed = mod.parse_case_log(
        test_id,
        text,
    )

    observed["runner_returncode"] = 0

    return mod.classify_case(
        observed,
        SPECS[test_id],
        PREREG,
    )


def test_fixture_hash_and_semantic_contract():
    mod.verify_fixture_contract()


def test_normal_case_classifies_cleanly():
    result = classify(
        "T01",
        normal_log(
            "T01",
            "H01",
            2,
        ),
    )

    assert result["pass"] is True
    assert result["target_validated"] == 1
    assert result["issues"] == []


def test_redirect_case_classifies_cleanly():
    result = classify(
        "T15",
        normal_log(
            "T15",
            "H15",
            2,
            stall=0,
            redirect=1,
        ),
    )

    assert result["pass"] is True


def test_known_t18_signature_matches_exactly():
    result = classify(
        "T18",
        t18_known_log(),
    )

    assert result["pass"] is True
    assert (
        result["expected_signature_matched"]
        is True
    )


def test_t18_without_rejection_is_not_silently_accepted():
    text = normal_log(
        "T18",
        "H18",
        2,
    )

    result = classify(
        "T18",
        text,
    )

    assert result["pass"] is False
    assert (
        result["expected_signature_matched"]
        is False
    )


def test_non_t18_rejection_is_unexpected():
    text = """
[T01 -> H01] running ... PASS
EXECUTION_STREAM_SMOKE cycles=60 accepted=2 accepted_after_stall=0 stall_cycles=0 flush_cycles=0 unsupported_cycles=0 l1_intent_bins=1 l1_seen=H01 l2_intent_bins=1 control_checks=1 control_passes=0 control_failures=1 control_failed_bins=H01 architectural_checks=8 architectural_passes=8 architectural_failures=0 architectural_failure_kinds=none l1_validated_bins=0 l1_validated_seen=none validation_attempts=1 validated_hits=0 rejected_hits=1 validation_pending=0 target_l1_validated=0
60.00ns WARNING CONTROL_REALIZATION_FAIL bin=H01 consumer_index=2 checks=stall_cycles_before_accept:expected=0,observed=1
60.00ns INFO L1_VALIDATION_REJECT bin=H01 consumer_index=2 reason=control failed_arch=none
    oracle: stall=0 redirect=0
"""

    result = classify(
        "T01",
        text,
    )

    assert result["pass"] is False
    assert result["issues"]


def test_zero_control_checks_fails_vacuity_guard():
    text = normal_log(
        "T01",
        "H01",
        2,
    ).replace(
        "control_checks=1",
        "control_checks=0",
    )

    result = classify(
        "T01",
        text,
    )

    assert result["pass"] is False
    assert any(
        "not exercised" in issue
        for issue in result["issues"]
    )


def test_zero_validation_attempts_fails_attribution_guard():
    text = normal_log(
        "T01",
        "H01",
        2,
    ).replace(
        "validation_attempts=1",
        "validation_attempts=0",
    )

    result = classify(
        "T01",
        text,
    )

    assert result["pass"] is False
    assert any(
        "attribution" in issue
        for issue in result["issues"]
    )


def test_t19_is_required_to_validate_after_frozen_fix():
    result = classify(
        "T19",
        normal_log(
            "T19",
            "H19",
            2,
        ),
    )

    assert result["pass"] is True
    assert (
        result["expected_rejection"]
        is False
    )


def test_t20_is_required_to_validate_after_frozen_fix():
    result = classify(
        "T20",
        normal_log(
            "T20",
            "H20",
            2,
        ),
    )

    assert result["pass"] is True
    assert (
        result["expected_rejection"]
        is False
    )
