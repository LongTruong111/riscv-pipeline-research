from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]

BASE_HARNESS_PATH = (
    ROOT
    / "research/week14/directed/"
    "run_directed_final.py"
)

RECOVERY_PATH = (
    ROOT
    / "research/week14/preflight/"
    "directed_recovery_contract.json"
)

PREREG_PATH = (
    ROOT
    / "research/week14/preflight/"
    "directed_expected_rejections.json"
)

AUDIT_PATH = (
    ROOT
    / "research/week14/preflight/"
    "directed_static_audit.json"
)

ATTEMPT1_PATH = (
    ROOT
    / "research/week14/results/"
    "attempt1_preregistered/"
    "directed_final.json"
)

RESULT_DIR = (
    ROOT
    / "research/week14/results/"
    "recovery_confirmation"
)

RESULT_JSON = (
    RESULT_DIR
    / "directed_recovery_confirmation.json"
)

EVIDENCE_TXT = (
    RESULT_DIR
    / "directed_recovery_confirmation_evidence.txt"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "week14_directed_final_base",
        BASE_HARNESS_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "cannot load base Directed harness"
        )

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(module)

    return module


base = load_module()


def load_json(path: Path) -> dict[str, Any]:
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


def as_int(
    fields: dict[str, str],
    name: str,
    issues: list[str],
) -> int | None:
    value = fields.get(name)

    if value is None:
        issues.append(
            f"missing smoke field: {name}"
        )
        return None

    try:
        return int(value)
    except ValueError:
        issues.append(
            f"invalid integer field "
            f"{name}={value!r}"
        )
        return None


def csv_set(value: str | None) -> set[str]:
    if value in {None, "", "none"}:
        return set()

    return {
        item
        for item in value.split(",")
        if item
    }


def verify_static_authority() -> None:
    recovery_commit = git(
        "log",
        "-1",
        "--format=%H",
        "--",
        str(
            RECOVERY_PATH.relative_to(ROOT)
        ),
    )

    expected_recovery_commit = git(
        "rev-parse",
        "7c28676",
    )

    if recovery_commit != expected_recovery_commit:
        raise RuntimeError(
            "recovery contract provenance changed"
        )

    subprocess.check_call(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            expected_recovery_commit,
            "HEAD",
        ],
        cwd=ROOT,
    )

    contract = load_json(RECOVERY_PATH)

    if contract["status"] != (
        "PROSPECTIVE_POST_ERRATUM_"
        "CONFIRMATION_CONTRACT"
    ):
        raise RuntimeError(
            "recovery contract status invalid"
        )

    if contract[
        "is_original_preregistration"
    ] is not False:
        raise RuntimeError(
            "recovery contract incorrectly claims "
            "original preregistration status"
        )

    if contract[
        "historical_status"
    ][
        "original_preregistered_attempt"
    ] != "FAIL":
        raise RuntimeError(
            "historical Attempt 1 status changed"
        )

    if contract[
        "gate_semantics"
    ]["plain_PASS_is_prohibited"] is not True:
        raise RuntimeError(
            "plain PASS prohibition missing"
        )

    expected_attempt_sha = contract[
        "authority"
    ]["attempt1_result_sha256"]

    observed_attempt_sha = sha256(
        ATTEMPT1_PATH
    )

    if observed_attempt_sha != expected_attempt_sha:
        raise RuntimeError(
            "Attempt-1 result hash changed"
        )

    base.verify_protected_state()
    base.verify_fixture_contract()


def classify_t19(
    observed: dict[str, Any],
    spec: dict[str, Any],
    recovery: dict[str, Any],
) -> dict[str, Any]:
    issues: list[str] = []

    target = "H19"
    fields = observed["fields"]

    t19_contract = next(
        item
        for item in recovery[
            "known_defect_confirmation"
        ]
        if item["test_id"] == "T19"
    )

    known = t19_contract[
        "required_observed_signature"
    ]

    normative = t19_contract[
        "normative_control"
    ]

    if observed["header_target_bin"] != target:
        issues.append(
            "runner target is not H19"
        )

    if observed["runner_case_status"] != "PASS":
        issues.append(
            "canonical execution engine failed"
        )

    accepted = as_int(
        fields,
        "accepted",
        issues,
    )

    stall_cycles = as_int(
        fields,
        "stall_cycles",
        issues,
    )

    flush_cycles = as_int(
        fields,
        "flush_cycles",
        issues,
    )

    unsupported = as_int(
        fields,
        "unsupported_cycles",
        issues,
    )

    control_checks = as_int(
        fields,
        "control_checks",
        issues,
    )

    control_failures = as_int(
        fields,
        "control_failures",
        issues,
    )

    arch_checks = as_int(
        fields,
        "architectural_checks",
        issues,
    )

    arch_failures = as_int(
        fields,
        "architectural_failures",
        issues,
    )

    validation_attempts = as_int(
        fields,
        "validation_attempts",
        issues,
    )

    rejected_hits = as_int(
        fields,
        "rejected_hits",
        issues,
    )

    pending = as_int(
        fields,
        "validation_pending",
        issues,
    )

    target_validated = as_int(
        fields,
        "target_l1_validated",
        issues,
    )

    if accepted != spec["expected_accepted"]:
        issues.append(
            "T19 accepted-count mismatch"
        )

    # The explicit runner oracle remains normative.
    if observed["oracle"]["stall"] != (
        normative["stall_cycles"]
    ):
        issues.append(
            "T19 normative stall oracle changed"
        )

    if observed["oracle"]["redirect"] != (
        normative["redirect"]
    ):
        issues.append(
            "T19 normative redirect oracle changed"
        )

    # Separately confirm the frozen DUT defect.
    if stall_cycles != known[
        "observed_stall_cycles"
    ]:
        issues.append(
            "T19 frozen false-stall signature "
            "not reproduced"
        )

    if flush_cycles != 0:
        issues.append(
            "T19 unexpected redirect/flush"
        )

    if unsupported != 0:
        issues.append(
            "T19 unsupported execution observed"
        )

    if target_validated != known[
        "target_validated"
    ]:
        issues.append(
            "T19 target validation state mismatch"
        )

    if arch_failures != known[
        "architectural_failures"
    ]:
        issues.append(
            "T19 architectural failure count "
            "does not match recovery contract"
        )

    if observed["architectural_failures"]:
        issues.append(
            "T19 emitted architectural failure "
            "evidence"
        )

    expected_bins = set(
        known["control_failure_bins"]
    )

    actual_failed_bins = csv_set(
        fields.get("control_failed_bins")
    )

    if actual_failed_bins != expected_bins:
        issues.append(
            "T19 control failure bins mismatch: "
            f"expected={sorted(expected_bins)} "
            f"observed="
            f"{sorted(actual_failed_bins)}"
        )

    if control_checks != 2:
        issues.append(
            "T19 must exercise two correlated "
            "control checks"
        )

    if control_failures != 2:
        issues.append(
            "T19 must produce two correlated "
            "control rejections"
        )

    if arch_checks is None or arch_checks < 8:
        issues.append(
            "T19 architectural oracle "
            "under-exercised"
        )

    if validation_attempts != 2:
        issues.append(
            "T19 must exercise two per-hit "
            "validation attempts"
        )

    if rejected_hits != 2:
        issues.append(
            "T19 must produce two correlated "
            "rejected hits"
        )

    if pending != 0:
        issues.append(
            "T19 validation remained pending"
        )

    l1_seen = csv_set(
        fields.get("l1_seen")
    )

    if l1_seen != {"H18", "H19"}:
        issues.append(
            "T19 Intent set must be exactly "
            "{H18,H19}"
        )

    rejection_bins = {
        item["bin"]
        for item in observed["rejections"]
    }

    if rejection_bins != set(
        known["rejected_bins"]
    ):
        issues.append(
            "T19 rejection-bin set mismatch"
        )

    if len(observed["rejections"]) != 2:
        issues.append(
            "T19 must emit exactly two "
            "L1_VALIDATION_REJECT records"
        )

    for rejection in observed["rejections"]:
        if rejection["consumer_index"] != 2:
            issues.append(
                "T19 rejection consumer identity "
                "changed"
            )

        if rejection["reason"] != (
            "control failed_arch=none"
        ):
            issues.append(
                "T19 rejection reason changed"
            )

    control_failure_bins = {
        item["bin"]
        for item in observed[
            "control_failures"
        ]
    }

    if control_failure_bins != expected_bins:
        issues.append(
            "T19 CONTROL_REALIZATION_FAIL "
            "bin set mismatch"
        )

    if len(
        observed["control_failures"]
    ) != 2:
        issues.append(
            "T19 must emit exactly two "
            "control-failure records"
        )

    for failure in observed[
        "control_failures"
    ]:
        if failure["consumer_index"] != 2:
            issues.append(
                "T19 control-failure consumer "
                "identity changed"
            )

        if failure["checks"] != (
            "stall_cycles_before_accept:"
            "expected=0,observed=1"
        ):
            issues.append(
                "T19 false-stall signature changed"
            )

    return {
        "test_id": "T19",
        "target_bin": "H19",
        "classification_mode":
            "KNOWN_DEFECT_CONFIRMATION",
        "root_cause_id":
            "LOAD_RD_X0_FALSE_STALL",
        "normative_stall_cycles":
            normative["stall_cycles"],
        "observed_defective_stall_cycles":
            stall_cycles,
        "intent_hit":
            "H19" in l1_seen,
        "target_validated":
            target_validated,
        "known_defect_signature_matched":
            not issues,
        "observed": observed,
        "issues": issues,
        "pass": not issues,
    }


def classify_case(
    observed: dict[str, Any],
    spec: dict[str, Any],
    prereg: dict[str, Any],
    recovery: dict[str, Any],
) -> dict[str, Any]:
    test_id = spec["test_id"]

    if test_id == "T19":
        return classify_t19(
            observed,
            spec,
            recovery,
        )

    result = base.classify_case(
        observed,
        spec,
        prereg,
    )

    result["classification_mode"] = (
        "ORIGINAL_HARNESS_SEMANTICS"
    )

    if test_id == "T18":
        result["root_cause_id"] = (
            "REGFILE_X0_WRITE"
        )

        result[
            "known_defect_signature_matched"
        ] = result[
            "expected_signature_matched"
        ]

    else:
        result["root_cause_id"] = None

        result[
            "known_defect_signature_matched"
        ] = False

    return result


def run_suite(sim: str) -> dict[str, Any]:
    verify_static_authority()

    recovery = load_json(RECOVERY_PATH)
    prereg = load_json(PREREG_PATH)
    audit = load_json(AUDIT_PATH)

    specs = {
        row["test_id"]: row
        for row in audit["cases"]
    }

    case_ids = [
        f"T{i:02d}"
        for i in range(1, 21)
    ]

    if sorted(specs) != case_ids:
        raise RuntimeError(
            "canonical T01..T20 set changed"
        )

    if RESULT_DIR.exists():
        raise RuntimeError(
            "recovery confirmation result "
            "directory already exists"
        )

    RESULT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    # Force a fresh Verilator build once before confirmation.
    shutil.rmtree(
        ROOT
        / "sim_build/week5_execution_stream",
        ignore_errors=True,
    )

    temp_root = Path(
        tempfile.mkdtemp(
            prefix=(
                "week14_recovery_confirmation_"
            )
        )
    )

    raw_dir = temp_root / "raw"
    raw_dir.mkdir(parents=True)

    classified_cases: list[
        dict[str, Any]
    ] = []

    evidence: list[str] = [
        "WEEK14 DIRECTED RECOVERY CONFIRMATION",
        "",
        (
            "Historical original preregistered "
            "Attempt 1 remains FAIL."
        ),
        (
            "This run is governed by the "
            "post-erratum recovery contract."
        ),
        "",
    ]

    try:
        for test_id in case_ids:
            rc, text = base.run_one_case(
                test_id,
                sim,
                raw_dir,
            )

            observed = base.parse_case_log(
                test_id,
                text,
            )

            observed["runner_returncode"] = rc

            result = classify_case(
                observed,
                specs[test_id],
                prereg,
                recovery,
            )

            if rc != 0:
                result["issues"].append(
                    "canonical runner returned "
                    f"non-zero status {rc}"
                )
                result["pass"] = False

            classified_cases.append(result)

            evidence.extend(
                [
                    (
                        f"===== {test_id} "
                        f"{specs[test_id]['target_bin']} "
                        f"====="
                    ),
                    base.filtered_evidence(
                        test_id,
                        text,
                    ),
                    "",
                ]
            )

            print(
                f"{test_id} "
                f"{specs[test_id]['target_bin']} "
                f"{'PASS' if result['pass'] else 'FAIL'} "
                f"validated="
                f"{result['target_validated']} "
                f"mode="
                f"{result['classification_mode']} "
                f"issues={len(result['issues'])}"
            )

            for issue in result["issues"]:
                print(f"  - {issue}")

        required_validated = set(
            recovery[
                "required_validated_cases"
            ]
        )

        observed_validated = {
            case["test_id"]
            for case in classified_cases
            if case["target_validated"] == 1
        }

        missing_required_validated = sorted(
            required_validated
            - observed_validated
        )

        unexpected_validated = sorted(
            observed_validated
            - required_validated
        )

        t18 = next(
            case
            for case in classified_cases
            if case["test_id"] == "T18"
        )

        t19 = next(
            case
            for case in classified_cases
            if case["test_id"] == "T19"
        )

        observed_root_causes = []

        if (
            t18["pass"]
            and t18[
                "known_defect_signature_matched"
            ]
        ):
            observed_root_causes.append(
                "REGFILE_X0_WRITE"
            )

        if (
            t19["pass"]
            and t19[
                "known_defect_signature_matched"
            ]
        ):
            observed_root_causes.append(
                "LOAD_RD_X0_FALSE_STALL"
            )

        expected_root_causes = recovery[
            "confirmation_acceptance"
        ][
            "known_root_causes_observed_exactly"
        ]

        missing_root_causes = sorted(
            set(expected_root_causes)
            - set(observed_root_causes)
        )

        unexpected_root_causes = sorted(
            set(observed_root_causes)
            - set(expected_root_causes)
        )

        intent_count = sum(
            bool(case["intent_hit"])
            for case in classified_cases
        )

        validated_count = sum(
            case["target_validated"] == 1
            for case in classified_cases
        )

        attribution_count = 0
        control_oracle_count = 0
        architectural_oracle_count = 0

        for case in classified_cases:
            fields = case["observed"]["fields"]

            if int(
                fields.get(
                    "validation_attempts",
                    "0",
                )
            ) >= 1:
                attribution_count += 1

            if int(
                fields.get(
                    "control_checks",
                    "0",
                )
            ) >= 1:
                control_oracle_count += 1

            if int(
                fields.get(
                    "architectural_checks",
                    "0",
                )
            ) >= 1:
                architectural_oracle_count += 1

        unexpected_rejected_cases = sorted(
            {
                case["test_id"]
                for case in classified_cases
                if (
                    case["observed"][
                        "rejections"
                    ]
                    and case["test_id"]
                    not in {"T18", "T19"}
                )
            }
        )

        confirmation_pass = (
            len(classified_cases) == 20
            and intent_count == 20
            and validated_count == 18
            and attribution_count == 20
            and control_oracle_count == 20
            and architectural_oracle_count == 20
            and not missing_required_validated
            and not unexpected_validated
            and not missing_root_causes
            and not unexpected_root_causes
            and not unexpected_rejected_cases
            and all(
                case["pass"]
                for case in classified_cases
            )
        )

        labels = recovery["gate_semantics"]

        status = (
            labels[
                "confirmation_success_label"
            ]
            if confirmation_pass
            else labels[
                "confirmation_failure_label"
            ]
        )

        payload = {
            "schema": (
                "week14.directed-recovery-"
                "confirmation.v1"
            ),
            "method": "M0-DIR",
            "status": status,
            "confirmation_contract_pass":
                confirmation_pass,
            "historical_original_attempt":
                "FAIL",
            "original_attempt_reclassified":
                False,
            "simulator": sim,
            "confirmation_runner_commit":
                git("rev-parse", "HEAD"),
            "recovery_contract_commit":
                git("rev-parse", "7c28676"),
            "original_preregistration_commit":
                recovery[
                    "authority"
                ][
                    "original_preregistration_commit"
                ],
            "erratum_commit":
                recovery[
                    "authority"
                ]["erratum_commit"],
            "gate_t13_commit":
                recovery[
                    "authority"
                ]["gate_t13_commit"],
            "case_count":
                len(classified_cases),
            "intent_count": intent_count,
            "intent_total": 20,
            "validated_count":
                validated_count,
            "validated_total": 20,
            "attribution_exercised_count":
                attribution_count,
            "control_oracle_exercised_count":
                control_oracle_count,
            "architectural_oracle_exercised_count":
                architectural_oracle_count,
            "required_validated_cases":
                sorted(required_validated),
            "observed_validated_cases":
                sorted(observed_validated),
            "missing_required_validated_cases":
                missing_required_validated,
            "unexpected_validated_cases":
                unexpected_validated,
            "expected_root_causes":
                expected_root_causes,
            "observed_root_causes":
                observed_root_causes,
            "missing_root_causes":
                missing_root_causes,
            "unexpected_root_causes":
                unexpected_root_causes,
            "unexpected_rejected_cases":
                unexpected_rejected_cases,
            "cases": classified_cases,
            "eligible_final_gate_status_if_"
            "remaining_obligations_pass":
                labels[
                    "eligible_final_gate_status_if_all_"
                    "remaining_week14_obligations_pass"
                ],
        }

        RESULT_JSON.write_text(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        EVIDENCE_TXT.write_text(
            "\n".join(evidence),
            encoding="utf-8",
        )

        verify_static_authority()

        return payload

    finally:
        shutil.rmtree(
            temp_root,
            ignore_errors=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--sim",
        default="verilator",
    )

    args = parser.parse_args()

    result = run_suite(args.sim)

    print()
    print(
        "===== WEEK14 DIRECTED "
        "RECOVERY CONFIRMATION ====="
    )

    for key in (
        "status",
        "confirmation_contract_pass",
        "historical_original_attempt",
        "original_attempt_reclassified",
        "intent_count",
        "validated_count",
        "attribution_exercised_count",
        "control_oracle_exercised_count",
        "architectural_oracle_exercised_count",
        "observed_root_causes",
        "missing_root_causes",
        "unexpected_root_causes",
        "unexpected_rejected_cases",
        "missing_required_validated_cases",
    ):
        print(f"{key}={result[key]}")

    print(
        "eligible_final_gate_status="
        + result[
            "eligible_final_gate_status_if_"
            "remaining_obligations_pass"
        ]
    )

    print(
        f"result={RESULT_JSON.relative_to(ROOT)}"
    )

    print(
        f"evidence="
        f"{EVIDENCE_TXT.relative_to(ROOT)}"
    )

    return (
        0
        if result[
            "confirmation_contract_pass"
        ]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
