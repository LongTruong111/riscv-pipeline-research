from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

MODULE_PATH = (
    ROOT
    / "research/week14/directed/"
    "run_directed_recovery_confirmation.py"
)

SPEC = importlib.util.spec_from_file_location(
    "week14_recovery_confirmation",
    MODULE_PATH,
)

assert SPEC is not None
assert SPEC.loader is not None

mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


RECOVERY = mod.load_json(
    mod.RECOVERY_PATH
)

PREREG = mod.load_json(
    mod.PREREG_PATH
)

AUDIT = mod.load_json(
    mod.AUDIT_PATH
)

SPECS = {
    row["test_id"]: row
    for row in AUDIT["cases"]
}


def t19_log(
    *,
    stall: int = 1,
    arch_failures: int = 0,
) -> str:
    arch_kinds = (
        "none"
        if arch_failures == 0
        else "writeback"
    )

    return f"""
[T19 -> H19] running ... PASS
EXECUTION_STREAM_SMOKE cycles=60 accepted=2 accepted_after_stall={stall} stall_cycles={stall} flush_cycles=0 unsupported_cycles=0 l1_intent_bins=2 l1_seen=H18,H19 l2_intent_bins=0 control_checks=2 control_passes=0 control_failures=2 control_failed_bins=H18,H19 architectural_checks=8 architectural_passes={8-arch_failures} architectural_failures={arch_failures} architectural_failure_kinds={arch_kinds} l1_validated_bins=0 l1_validated_seen=none validation_attempts=2 validated_hits=0 rejected_hits=2 validation_pending=0 target_l1_validated=0
60.00ns WARNING CONTROL_REALIZATION_FAIL bin=H18 consumer_index=2 checks=stall_cycles_before_accept:expected=0,observed=1
60.00ns INFO L1_VALIDATION_REJECT bin=H18 consumer_index=2 reason=control failed_arch=none
60.00ns WARNING CONTROL_REALIZATION_FAIL bin=H19 consumer_index=2 checks=stall_cycles_before_accept:expected=0,observed=1
60.00ns INFO L1_VALIDATION_REJECT bin=H19 consumer_index=2 reason=control failed_arch=none
    oracle: stall=0 redirect=0
"""


def normal_log(
    test_id: str,
    target: str,
    accepted: int,
) -> str:
    arch = accepted * 4

    return f"""
[{test_id} -> {target}] running ... PASS
EXECUTION_STREAM_SMOKE cycles=60 accepted={accepted} accepted_after_stall=0 stall_cycles=0 flush_cycles=0 unsupported_cycles=0 l1_intent_bins=1 l1_seen={target} l2_intent_bins=1 control_checks=1 control_passes=1 control_failures=0 control_failed_bins=none architectural_checks={arch} architectural_passes={arch} architectural_failures=0 architectural_failure_kinds=none l1_validated_bins=1 l1_validated_seen={target} validation_attempts=1 validated_hits=1 rejected_hits=0 validation_pending=0 target_l1_validated=1
    oracle: stall=0 redirect=0
"""


def classify(
    test_id: str,
    text: str,
):
    observed = mod.base.parse_case_log(
        test_id,
        text,
    )

    observed["runner_returncode"] = 0

    return mod.classify_case(
        observed,
        SPECS[test_id],
        PREREG,
        RECOVERY,
    )


def test_static_authority():
    mod.verify_static_authority()


def test_required_validated_set_is_exact():
    assert RECOVERY[
        "required_validated_cases"
    ] == [
        f"T{i:02d}"
        for i in range(1, 21)
        if i not in (18, 19)
    ]


def test_normal_case_uses_original_semantics():
    result = classify(
        "T01",
        normal_log(
            "T01",
            "H01",
            2,
        ),
    )

    assert result["pass"] is True
    assert result[
        "classification_mode"
    ] == "ORIGINAL_HARNESS_SEMANTICS"


def test_t19_exact_known_signature_passes():
    result = classify(
        "T19",
        t19_log(),
    )

    assert result["pass"] is True
    assert result[
        "known_defect_signature_matched"
    ] is True

    assert result[
        "normative_stall_cycles"
    ] == 0

    assert result[
        "observed_defective_stall_cycles"
    ] == 1


def test_t19_does_not_rewrite_normative_oracle():
    t19 = next(
        item
        for item in RECOVERY[
            "known_defect_confirmation"
        ]
        if item["test_id"] == "T19"
    )

    assert t19[
        "normative_control"
    ]["stall_cycles"] == 0

    assert t19[
        "required_observed_signature"
    ]["observed_stall_cycles"] == 1


def test_t19_wrong_observed_stall_fails():
    result = classify(
        "T19",
        t19_log(stall=0),
    )

    assert result["pass"] is False

    assert any(
        "false-stall signature"
        in issue
        for issue in result["issues"]
    )


def test_t19_architectural_failure_fails():
    result = classify(
        "T19",
        t19_log(
            arch_failures=1,
        ),
    )

    assert result["pass"] is False

    assert any(
        "architectural failure count"
        in issue
        for issue in result["issues"]
    )


def test_plain_pass_label_is_prohibited():
    gate = RECOVERY[
        "gate_semantics"
    ]

    assert gate[
        "plain_PASS_is_prohibited"
    ] is True

    assert gate[
        "confirmation_success_label"
    ] == (
        "PASS_POST_ERRATUM_CONFIRMATION"
    )
