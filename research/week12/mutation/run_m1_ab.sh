#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

AB_DIR="${REPO_ROOT}/sim_build/week12_m1_ab"
CHECKER_DIR="${REPO_ROOT}/sim_build/week12_m1_checker"

CANONICAL_LOG="${AB_DIR}/canonical.log"
MUTANT_LOG="${AB_DIR}/mutant.log"

RAW_RESULT="${CHECKER_DIR}/m1_checker_raw.json"
WAVEFORM="${CHECKER_DIR}/week12_m1_failure.vcd"
FINAL_JSON="${CHECKER_DIR}/m1_telemetry.json"

cd "${REPO_ROOT}"

rm -rf "${AB_DIR}"
mkdir -p "${AB_DIR}"

GIT_COMMIT="$(git rev-parse HEAD)"

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
    GIT_DIRTY=1
else
    GIT_DIRTY=0
fi

echo "=== A: CANONICAL CONTROL ==="

research/week11/rtl/run_integrated_50.sh \
    | tee "${CANONICAL_LOG}"

grep -q \
    'WEEK11_INTEGRATED_50 accepted=50 retired=50' \
    "${CANONICAL_LOG}"

echo "P5_CANONICAL_CONTROL=PASS"

echo
echo "=== B: M1 MUTANT ==="

research/week12/mutation/run_m1_checker.sh \
    | tee "${MUTANT_LOG}"

grep -q \
    'WEEK12_M1_CHECKER accepted=50 retired=50' \
    "${MUTANT_LOG}"

test -s "${RAW_RESULT}"
test -s "${WAVEFORM}"

python3 - \
    "${RAW_RESULT}" \
    "${WAVEFORM}" \
    "${FINAL_JSON}" \
    "${GIT_COMMIT}" \
    "${GIT_DIRTY}" \
    <<'PY_FINALIZE'
import json
from pathlib import Path
import sys

from research.week12.telemetry.e2e_telemetry import (
    sha256_file,
)
from research.week12.telemetry.mutation_telemetry import (
    MutationSmokeRecord,
    SCHEMA_VERSION,
    write_json,
)


raw_path = Path(sys.argv[1])
waveform = Path(sys.argv[2])
output = Path(sys.argv[3])
git_commit = sys.argv[4]
git_dirty = sys.argv[5] == "1"

raw = json.loads(
    raw_path.read_text(encoding="utf-8")
)

first_failure = raw.get(
    "first_failure"
)

if not isinstance(first_failure, dict):
    raise AssertionError(
        "structured first_failure missing"
    )

if (
    first_failure.get("check_name")
    != "forward_a"
):
    raise AssertionError(
        "first failure is not Forward_A"
    )

if (
    first_failure.get("instruction_id")
    != raw.get(
        "first_target_instruction_id"
    )
):
    raise AssertionError(
        "first checker failure does not "
        "match first target activation"
    )

record = MutationSmokeRecord(
    schema_version=SCHEMA_VERSION,
    git_commit=git_commit,
    git_dirty=git_dirty,
    dut_variant="m1-smoke",
    workload="integrated50",
    canonical_control_pass=True,
    mutant_compile_pass=True,
    mutant_simulation_pass=True,
    accepted_instructions=raw[
        "accepted_instructions"
    ],
    retired_instructions=raw[
        "retired_instructions"
    ],
    target_activation_count=raw[
        "target_activation_count"
    ],
    target_suppressed_count=raw[
        "target_suppressed_count"
    ],
    checker_failure_count=raw[
        "checker_failure_count"
    ],
    authoritative_checker_failure=(
        raw["checker_failure_count"] > 0
    ),
    first_target_instruction_id=raw[
        "first_target_instruction_id"
    ],
    first_failure=first_failure,
    waveform_path=str(
        waveform.resolve()
    ),
    waveform_sha256=sha256_file(
        waveform
    ),
)

if not record.mutation_caught:
    raise AssertionError(
        "M1 mutation was not caught"
    )

write_json(
    record,
    output,
)

print("P5_M1_CAUGHT=PASS")
print(
    "m1_summary="
    f"activations="
    f"{record.target_activation_count} "
    f"checker_failures="
    f"{record.checker_failure_count} "
    f"first_failure_instruction="
    f"{record.first_failure['instruction_id']} "
    f"waveform_sha256="
    f"{record.waveform_sha256}"
)
print(f"m1_telemetry={output}")
PY_FINALIZE

test -s "${FINAL_JSON}"

echo
echo "=== FINAL EVIDENCE ==="
python3 -m json.tool "${FINAL_JSON}"

echo
echo "P5_AB=PASS"
