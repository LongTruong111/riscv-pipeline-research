from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]

AUDIT_PATH = (
    ROOT
    / "research/week14/preflight/"
    "directed_static_audit.json"
)

PREREG_PATH = (
    ROOT
    / "research/week14/preflight/"
    "directed_expected_rejections.json"
)

TREE_PATH = (
    ROOT
    / "research/week14/preflight/"
    "protected_tree_sha.json"
)

RESULT_DIR = (
    ROOT
    / "research/week14/results"
)

RESULT_JSON = (
    RESULT_DIR
    / "directed_final.json"
)

EVIDENCE_TXT = (
    RESULT_DIR
    / "directed_final_evidence.txt"
)


CASE_HEADER_RE = re.compile(
    r"\[(T\d{2}) -> (H\d{2})\] "
    r"running \.\.\. (PASS|FAIL)"
)

KV_RE = re.compile(
    r"([A-Za-z0-9_]+)=([^\s]+)"
)

REJECTION_RE = re.compile(
    r"L1_VALIDATION_REJECT "
    r"bin=(H\d{2}) "
    r"consumer_index=(\d+) "
    r"reason=(.*)$"
)

ARCH_FAILURE_RE = re.compile(
    r"ARCHITECTURAL_REALIZATION_FAIL "
    r"kind=([A-Za-z0-9_]+) "
    r"instruction_index=(\d+) "
    r"checks=(.*)$"
)

CONTROL_FAILURE_RE = re.compile(
    r"CONTROL_REALIZATION_FAIL "
    r"bin=(H\d{2}) "
    r"consumer_index=(\d+) "
    r"checks=(.*)$"
)

ORACLE_RE = re.compile(
    r"oracle:\s*stall=(\d+)\s+redirect=(\d+)"
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
    ).strip()


def git_status(*paths: str) -> str:
    return subprocess.check_output(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            *paths,
        ],
        cwd=ROOT,
        text=True,
    ).strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(65536),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def verify_protected_state() -> None:
    provenance = load_json(TREE_PATH)

    base = provenance["gate_t13_commit"]

    peeled = git(
        "rev-parse",
        "GATE_T13_COMPLETE^{commit}",
    )

    if peeled != base:
        raise RuntimeError(
            "GATE_T13_COMPLETE peel changed: "
            f"expected={base} observed={peeled}"
        )

    for path, entry in (
        provenance["protected_paths"].items()
    ):
        expected = entry["base_tree"]

        head_tree = git(
            "rev-parse",
            f"HEAD:{path}",
        )

        if head_tree != expected:
            raise RuntimeError(
                f"protected committed tree changed: "
                f"{path}: "
                f"expected={expected} "
                f"observed={head_tree}"
            )

        dirty = git_status(path)

        if dirty:
            raise RuntimeError(
                f"protected working tree dirty: "
                f"{path}\n{dirty}"
            )


def fixture_bytes_from_words(
    words: list[int],
) -> list[int]:
    """
    Return the canonical fixture payload only.

    Week-5 Txx.hex files contain exactly four little-endian
    byte lines per encoded instruction. They are intentionally
    not padded to the full 512-byte physical IMEM here.

    Padding/loading policy belongs to the frozen execution
    runner, not to fixture provenance.
    """
    result: list[int] = []

    for word in words:
        result.extend(
            [
                (word >> 0) & 0xFF,
                (word >> 8) & 0xFF,
                (word >> 16) & 0xFF,
                (word >> 24) & 0xFF,
            ]
        )

    if len(result) > 512:
        raise AssertionError(
            "canonical directed fixture "
            "exceeds 512-byte IMEM"
        )

    return result


def verify_fixture_contract() -> None:
    audit = load_json(AUDIT_PATH)

    for row in audit["cases"]:
        path = ROOT / row["fixture_path"]

        observed_sha = sha256_file(path)

        if observed_sha != row["fixture_sha256"]:
            raise RuntimeError(
                f'{row["test_id"]}: fixture SHA mismatch'
            )

        fixture_lines = [
            line.strip()
            for line in path.read_text(
                encoding="ascii"
            ).splitlines()
            if line.strip()
        ]

        observed_bytes = [
            int(line, 16)
            for line in fixture_lines
        ]

        words = [
            int(item["word"], 16)
            for item in row["instructions"]
        ]

        expected_bytes = fixture_bytes_from_words(
            words
        )

        if observed_bytes != expected_bytes:
            raise RuntimeError(
                f'{row["test_id"]}: fixture bytes '
                f'do not match DIRECTED_CASES audit'
            )


def split_csv(value: str) -> set[str]:
    if value in {"", "none"}:
        return set()

    return {
        item
        for item in value.split(",")
        if item
    }


def parse_case_log(
    test_id: str,
    text: str,
) -> dict[str, Any]:
    header_matches = list(
        CASE_HEADER_RE.finditer(text)
    )

    matching_headers = [
        match
        for match in header_matches
        if match.group(1) == test_id
    ]

    if len(matching_headers) != 1:
        raise ValueError(
            f"{test_id}: expected one case header, "
            f"got {len(matching_headers)}"
        )

    header = matching_headers[0]

    smoke_lines = [
        line
        for line in text.splitlines()
        if "EXECUTION_STREAM_SMOKE " in line
    ]

    if len(smoke_lines) != 1:
        raise ValueError(
            f"{test_id}: expected one "
            f"EXECUTION_STREAM_SMOKE line, "
            f"got {len(smoke_lines)}"
        )

    smoke_tail = smoke_lines[0].split(
        "EXECUTION_STREAM_SMOKE ",
        1,
    )[1]

    fields = {
        key: value
        for key, value in KV_RE.findall(
            smoke_tail
        )
    }

    rejections = []

    for line in text.splitlines():
        match = REJECTION_RE.search(line)

        if match:
            rejections.append(
                {
                    "bin": match.group(1),
                    "consumer_index":
                        int(match.group(2)),
                    "reason":
                        match.group(3).strip(),
                }
            )

    architectural_failures = []

    for line in text.splitlines():
        match = ARCH_FAILURE_RE.search(line)

        if match:
            architectural_failures.append(
                {
                    "kind": match.group(1),
                    "instruction_index":
                        int(match.group(2)),
                    "checks":
                        match.group(3).strip(),
                }
            )

    control_failures = []

    for line in text.splitlines():
        match = CONTROL_FAILURE_RE.search(line)

        if match:
            control_failures.append(
                {
                    "bin": match.group(1),
                    "consumer_index":
                        int(match.group(2)),
                    "checks":
                        match.group(3).strip(),
                }
            )

    oracle_matches = [
        ORACLE_RE.search(line)
        for line in text.splitlines()
        if "oracle:" in line
    ]

    oracle_matches = [
        match
        for match in oracle_matches
        if match is not None
    ]

    if len(oracle_matches) != 1:
        raise ValueError(
            f"{test_id}: expected one oracle line, "
            f"got {len(oracle_matches)}"
        )

    oracle_match = oracle_matches[0]

    return {
        "test_id": test_id,
        "header_target_bin":
            header.group(2),
        "runner_case_status":
            header.group(3),
        "fields": fields,
        "rejections": rejections,
        "architectural_failures":
            architectural_failures,
        "control_failures":
            control_failures,
        "oracle": {
            "stall":
                int(oracle_match.group(1)),
            "redirect":
                bool(int(oracle_match.group(2))),
        },
    }


def require_int(
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
            f"non-integer smoke field "
            f"{name}={value!r}"
        )
        return None


def classify_case(
    observed: dict[str, Any],
    spec: dict[str, Any],
    prereg: dict[str, Any],
) -> dict[str, Any]:
    test_id = spec["test_id"]
    target = spec["target_bin"]
    fields = observed["fields"]

    issues: list[str] = []

    if observed["header_target_bin"] != target:
        issues.append(
            "runner target bin differs from audit"
        )

    if observed["runner_case_status"] != "PASS":
        issues.append(
            "canonical execution runner did not PASS"
        )

    accepted = require_int(
        fields,
        "accepted",
        issues,
    )

    stall_cycles = require_int(
        fields,
        "stall_cycles",
        issues,
    )

    flush_cycles = require_int(
        fields,
        "flush_cycles",
        issues,
    )

    unsupported_cycles = require_int(
        fields,
        "unsupported_cycles",
        issues,
    )

    control_checks = require_int(
        fields,
        "control_checks",
        issues,
    )

    control_failures_count = require_int(
        fields,
        "control_failures",
        issues,
    )

    architectural_checks = require_int(
        fields,
        "architectural_checks",
        issues,
    )

    architectural_failures_count = require_int(
        fields,
        "architectural_failures",
        issues,
    )

    validation_attempts = require_int(
        fields,
        "validation_attempts",
        issues,
    )

    rejected_hits = require_int(
        fields,
        "rejected_hits",
        issues,
    )

    validation_pending = require_int(
        fields,
        "validation_pending",
        issues,
    )

    target_validated = require_int(
        fields,
        "target_l1_validated",
        issues,
    )

    if (
        accepted is not None
        and accepted != spec["expected_accepted"]
    ):
        issues.append(
            "accepted count mismatch: "
            f"expected={spec['expected_accepted']} "
            f"observed={accepted}"
        )

    if (
        stall_cycles is not None
        and stall_cycles
        != spec["oracle_stall_cycles"]
    ):
        issues.append(
            "stall oracle mismatch: "
            f"expected="
            f"{spec['oracle_stall_cycles']} "
            f"observed={stall_cycles}"
        )

    expected_flush = (
        1
        if spec["oracle_redirect"]
        else 0
    )

    if (
        flush_cycles is not None
        and flush_cycles != expected_flush
    ):
        issues.append(
            "redirect/flush oracle mismatch: "
            f"expected={expected_flush} "
            f"observed={flush_cycles}"
        )

    if unsupported_cycles not in {None, 0}:
        issues.append(
            "unsupported execution cycle observed"
        )

    l1_seen = split_csv(
        fields.get("l1_seen", "")
    )

    if target not in l1_seen:
        issues.append(
            f"designated Intent bin {target} "
            f"was not observed"
        )

    if (
        control_checks is not None
        and control_checks < 1
    ):
        issues.append(
            "control/timing oracle was not exercised"
        )

    minimum_arch_checks = (
        spec["expected_accepted"] * 4
    )

    if (
        architectural_checks is not None
        and architectural_checks
        < minimum_arch_checks
    ):
        issues.append(
            "architectural/value oracle appears "
            "under-exercised: "
            f"minimum={minimum_arch_checks} "
            f"observed={architectural_checks}"
        )

    if (
        validation_attempts is not None
        and validation_attempts < 1
    ):
        issues.append(
            "no per-hit validation attempt; "
            "attribution evidence is vacuous"
        )

    if validation_pending not in {None, 0}:
        issues.append(
            "validation remained pending at end "
            "of directed case"
        )

    if (
        observed["oracle"]["stall"]
        != spec["oracle_stall_cycles"]
    ):
        issues.append(
            "explicit runner stall oracle mismatch"
        )

    if (
        observed["oracle"]["redirect"]
        != bool(spec["oracle_redirect"])
    ):
        issues.append(
            "explicit runner redirect oracle mismatch"
        )

    expected_rejection_ids = set(
        prereg["expected_rejection_test_ids"]
    )

    expected_rejection = (
        test_id in expected_rejection_ids
    )

    signature_matched = False

    if expected_rejection:
        if target_validated not in {None, 0}:
            issues.append(
                "expected-rejection target "
                "was unexpectedly Validated"
            )

        if control_failures_count not in {None, 0}:
            issues.append(
                "T18 known signature requires "
                "control_pass=True"
            )

        if observed["control_failures"]:
            issues.append(
                "T18 emitted control failure; "
                "known signature is architectural-only"
            )

        kinds = split_csv(
            fields.get(
                "architectural_failure_kinds",
                "",
            )
        )

        if kinds != {"x0"}:
            issues.append(
                "T18 architectural failure kinds "
                f"must be exactly {{x0}}, got "
                f"{sorted(kinds)}"
            )

        if (
            architectural_failures_count
            is not None
            and architectural_failures_count < 1
        ):
            issues.append(
                "T18 expected x0 architectural "
                "failure was not counted"
            )

        if rejected_hits not in {None, 1}:
            issues.append(
                "T18 must produce exactly one "
                "rejected L1 hit"
            )

        rejects = observed["rejections"]

        if len(rejects) != 1:
            issues.append(
                "T18 must emit exactly one "
                "L1_VALIDATION_REJECT"
            )
        else:
            reject = rejects[0]

            if reject["bin"] != "H18":
                issues.append(
                    "T18 rejection bin is not H18"
                )

            if (
                reject["consumer_index"]
                != spec["expected_accepted"]
            ):
                issues.append(
                    "T18 rejected consumer identity "
                    "does not match canonical target"
                )

            if (
                "architectural"
                not in reject["reason"]
            ):
                issues.append(
                    "T18 rejection reason is not "
                    "architectural"
                )

        arch_fails = observed[
            "architectural_failures"
        ]

        if not arch_fails:
            issues.append(
                "T18 emitted no architectural "
                "failure evidence"
            )

        for failure in arch_fails:
            if failure["kind"] != "x0":
                issues.append(
                    "T18 contains non-x0 "
                    "architectural failure"
                )

            if (
                "architectural_x0:"
                "expected=0x0,observed=0x7"
                not in failure["checks"]
            ):
                issues.append(
                    "T18 x0 signature does not match "
                    "expected=0 observed=7"
                )

        activation_matches = any(
            failure["instruction_index"] == 1
            and failure["kind"] == "x0"
            and (
                "architectural_x0:"
                "expected=0x0,observed=0x7"
                in failure["checks"]
            )
            for failure in arch_fails
        )

        if not activation_matches:
            issues.append(
                "T18 activation instruction #1 "
                "did not expose the preregistered "
                "x0 signature"
            )

        signature_matched = not issues

    else:
        if target_validated not in {None, 1}:
            issues.append(
                "required non-rejected target "
                "did not validate"
            )

        if control_failures_count not in {None, 0}:
            issues.append(
                "unexpected control failure"
            )

        if (
            architectural_failures_count
            not in {None, 0}
        ):
            issues.append(
                "unexpected architectural failure"
            )

        if rejected_hits not in {None, 0}:
            issues.append(
                "unexpected rejected L1 hit"
            )

        if observed["rejections"]:
            issues.append(
                "unexpected L1_VALIDATION_REJECT "
                "evidence"
            )

        if observed["architectural_failures"]:
            issues.append(
                "unexpected architectural failure "
                "signature"
            )

        if observed["control_failures"]:
            issues.append(
                "unexpected control failure "
                "signature"
            )

    return {
        "test_id": test_id,
        "target_bin": target,
        "expected_rejection":
            expected_rejection,
        "expected_signature_matched":
            signature_matched,
        "intent_hit":
            target in l1_seen,
        "attribution_exercised": (
            target in l1_seen
            and validation_attempts is not None
            and validation_attempts >= 1
        ),
        "control_oracle_exercised": (
            control_checks is not None
            and control_checks >= 1
        ),
        "architectural_oracle_exercised": (
            architectural_checks is not None
            and architectural_checks
            >= minimum_arch_checks
        ),
        "target_validated":
            target_validated,
        "observed": observed,
        "issues": issues,
        "pass": not issues,
    }


def filtered_evidence(
    test_id: str,
    text: str,
) -> str:
    markers = (
        f"[{test_id} ->",
        "EXECUTION_STREAM_SMOKE ",
        "ARCHITECTURAL_REALIZATION_FAIL ",
        "CONTROL_REALIZATION_FAIL ",
        "L1_VALIDATION_REJECT ",
        "oracle:",
    )

    selected = [
        line
        for line in text.splitlines()
        if any(
            marker in line
            for marker in markers
        )
    ]

    return "\n".join(selected)


def run_one_case(
    test_id: str,
    sim: str,
    raw_dir: Path,
) -> tuple[int, str]:
    env = os.environ.copy()

    env["SIM"] = sim
    env["N_CYCLES"] = "60"

    completed = subprocess.run(
        [
            "bash",
            "research/week5/rtl/"
            "run_l1_directed.sh",
            test_id,
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    raw_path = raw_dir / f"{test_id}.log"

    raw_path.write_text(
        completed.stdout,
        encoding="utf-8",
    )

    mutable_state = git_status(
        "instruction.hex",
        "data.hex",
    )

    if mutable_state:
        raise RuntimeError(
            f"{test_id}: canonical runner did not "
            f"restore instruction/data images:\n"
            f"{mutable_state}"
        )

    return (
        completed.returncode,
        completed.stdout,
    )


def run_suite(sim: str) -> dict[str, Any]:
    verify_protected_state()
    verify_fixture_contract()

    audit = load_json(AUDIT_PATH)
    prereg = load_json(PREREG_PATH)

    specs = {
        row["test_id"]: row
        for row in audit["cases"]
    }

    expected_case_ids = [
        f"T{i:02d}"
        for i in range(1, 21)
    ]

    if sorted(specs) != expected_case_ids:
        raise RuntimeError(
            "canonical directed case set "
            "is not exactly T01..T20"
        )

    RESULT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="week14_directed_final_"
        )
    )

    raw_dir = temp_root / "raw"
    raw_dir.mkdir(parents=True)

    classified_cases = []
    evidence_sections = []

    try:
        for test_id in expected_case_ids:
            returncode, text = run_one_case(
                test_id,
                sim,
                raw_dir,
            )

            observed = parse_case_log(
                test_id,
                text,
            )

            observed["runner_returncode"] = (
                returncode
            )

            classified = classify_case(
                observed,
                specs[test_id],
                prereg,
            )

            if returncode != 0:
                classified["issues"].append(
                    "single-case runner returned "
                    f"non-zero status {returncode}"
                )
                classified["pass"] = False

            classified_cases.append(
                classified
            )

            evidence_sections.extend(
                [
                    (
                        f"===== {test_id} "
                        f"{specs[test_id]['target_bin']} "
                        f"====="
                    ),
                    filtered_evidence(
                        test_id,
                        text,
                    ),
                    "",
                ]
            )

            print(
                f"{test_id} "
                f"{specs[test_id]['target_bin']} "
                f"{'PASS' if classified['pass'] else 'FAIL'} "
                f"target_validated="
                f"{classified['target_validated']} "
                f"issues={len(classified['issues'])}"
            )

            for issue in classified["issues"]:
                print(
                    f"  - {issue}"
                )

        observed_rejections = []

        for case in classified_cases:
            for rejection in (
                case["observed"]["rejections"]
            ):
                observed_rejections.append(
                    {
                        "test_id":
                            case["test_id"],
                        **rejection,
                    }
                )

        expected_keys = {
            (
                item["test_id"],
                item["target_bin"],
            )
            for item in prereg[
                "expected_rejections"
            ]
        }

        observed_keys = {
            (
                item["test_id"],
                item["bin"],
            )
            for item in observed_rejections
        }

        unexpected_rejections = [
            item
            for item in observed_rejections
            if (
                item["test_id"],
                item["bin"],
            )
            not in expected_keys
        ]

        matched_expected = {
            (
                case["test_id"],
                case["target_bin"],
            )
            for case in classified_cases
            if case[
                "expected_signature_matched"
            ]
        }

        missing_expected = sorted(
            expected_keys - matched_expected
        )

        signature_mismatches = [
            {
                "test_id": case["test_id"],
                "target_bin":
                    case["target_bin"],
                "issues": case["issues"],
            }
            for case in classified_cases
            if (
                case["expected_rejection"]
                and not case[
                    "expected_signature_matched"
                ]
            )
        ]

        intent_count = sum(
            case["intent_hit"]
            for case in classified_cases
        )

        validated_count = sum(
            case["target_validated"] == 1
            for case in classified_cases
        )

        attribution_count = sum(
            case["attribution_exercised"]
            for case in classified_cases
        )

        control_oracle_count = sum(
            case["control_oracle_exercised"]
            for case in classified_cases
        )

        architectural_oracle_count = sum(
            case[
                "architectural_oracle_exercised"
            ]
            for case in classified_cases
        )

        overall_pass = (
            len(classified_cases) == 20
            and intent_count == 20
            and attribution_count == 20
            and control_oracle_count == 20
            and architectural_oracle_count == 20
            and validated_count == 19
            and not unexpected_rejections
            and not missing_expected
            and not signature_mismatches
            and all(
                case["pass"]
                for case in classified_cases
            )
        )

        prereg_commit = git(
            "log",
            "-1",
            "--format=%H",
            "--",
            str(
                PREREG_PATH.relative_to(ROOT)
            ),
        )

        payload = {
            "schema":
                "week14.directed-final.v1",
            "method": "M0-DIR",
            "simulator": sim,
            "harness_commit":
                git("rev-parse", "HEAD"),
            "preregistration_commit":
                prereg_commit,
            "gate_t13_commit":
                prereg["gate_t13_commit"],
            "execution_engine": (
                "research/week5/rtl/"
                "run_l1_directed.sh"
            ),
            "execution_isolation": (
                "one independent runner/"
                "simulator invocation per Txx"
            ),
            "case_count":
                len(classified_cases),
            "intent_count":
                intent_count,
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
            "expected_rejection_keys":
                sorted(
                    [
                        list(item)
                        for item in expected_keys
                    ]
                ),
            "observed_rejection_keys":
                sorted(
                    [
                        list(item)
                        for item in observed_keys
                    ]
                ),
            "unexpected_rejections":
                unexpected_rejections,
            "missing_expected_rejections":
                [
                    list(item)
                    for item in missing_expected
                ],
            "signature_mismatches":
                signature_mismatches,
            "cases": classified_cases,
            "overall_pass":
                overall_pass,
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
            "\n".join(
                evidence_sections
            ),
            encoding="utf-8",
        )

        verify_protected_state()

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
    print("===== WEEK14 DIRECTED FINAL =====")
    print(
        f"INTENT="
        f"{result['intent_count']}/"
        f"{result['intent_total']}"
    )
    print(
        f"VALIDATED="
        f"{result['validated_count']}/"
        f"{result['validated_total']}"
    )
    print(
        "ATTRIBUTION_EXERCISED="
        f"{result['attribution_exercised_count']}/20"
    )
    print(
        "CONTROL_ORACLE_EXERCISED="
        f"{result['control_oracle_exercised_count']}/20"
    )
    print(
        "ARCH_ORACLE_EXERCISED="
        f"{result['architectural_oracle_exercised_count']}/20"
    )
    print(
        "EXPECTED_REJECTIONS="
        f"{result['expected_rejection_keys']}"
    )
    print(
        "OBSERVED_REJECTIONS="
        f"{result['observed_rejection_keys']}"
    )
    print(
        "UNEXPECTED_REJECTIONS="
        f"{result['unexpected_rejections']}"
    )
    print(
        "MISSING_EXPECTED="
        f"{result['missing_expected_rejections']}"
    )
    print(
        "SIGNATURE_MISMATCHES="
        f"{result['signature_mismatches']}"
    )
    print(
        "OVERALL_PASS="
        f"{result['overall_pass']}"
    )
    print(
        f"RESULT={RESULT_JSON.relative_to(ROOT)}"
    )
    print(
        f"EVIDENCE={EVIDENCE_TXT.relative_to(ROOT)}"
    )

    return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
