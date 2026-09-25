#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

CANON_BUILD="${REPO_ROOT}/sim_build/week13_m2_canonical"
MUTANT_BUILD="${REPO_ROOT}/sim_build/week13_m2_mutant"

CANON_RESULT="${CANON_BUILD}/m2_canonical.json"
MUTANT_RESULT="${MUTANT_BUILD}/m2_mutant.json"

RAW_WAVE="${REPO_ROOT}/dump.vcd"
FINAL_WAVE="${MUTANT_BUILD}/week13_m2_failure.vcd"

ORIGINAL="${REPO_ROOT}/instruction.hex"
BACKUP="$(mktemp)"

restore_instruction_hex() {
    if [[ -f "${BACKUP}" ]]; then
        cp "${BACKUP}" "${ORIGINAL}"
        rm -f "${BACKUP}"
    fi
}

trap restore_instruction_hex EXIT
trap 'exit 130' INT TERM HUP

cp "${ORIGINAL}" "${BACKUP}"

cd "${REPO_ROOT}"

rm -rf "${CANON_BUILD}" "${MUTANT_BUILD}"
rm -f "${RAW_WAVE}"

mkdir -p "${CANON_BUILD}" "${MUTANT_BUILD}"

python3 - <<'PY_FIXTURE'
from pathlib import Path

from research.week5.impl.directed_cases import DIRECTED_CASES

case = DIRECTED_CASES["T18"]
words = list(case.words)

if len(words) != 2:
    raise SystemExit(
        f"expected T18 to contain 2 instructions, got {len(words)}"
    )

image_bytes = []

for word in words:
    image_bytes.extend(
        [
            (word >> 0) & 0xFF,
            (word >> 8) & 0xFF,
            (word >> 16) & 0xFF,
            (word >> 24) & 0xFF,
        ]
    )

image_bytes.extend([0] * (512 - len(image_bytes)))

if len(image_bytes) != 512:
    raise SystemExit(
        f"expected 512 IMEM bytes, got {len(image_bytes)}"
    )

Path("instruction.hex").write_text(
    "".join(f"{byte:02x}\n" for byte in image_bytes),
    encoding="ascii",
)
PY_FIXTURE

echo "=== M2 canonical control ==="

WEEK13_M2_MODE=canonical \
WEEK13_M2_RESULT_PATH="${CANON_RESULT}" \
make \
    -f research/week13/mutation/Makefile \
    FORWARDING_VARIANT=canonical \
    SIM="${SIM:-verilator}" \
    SIM_BUILD="${CANON_BUILD}"

test -s "${CANON_RESULT}"

echo "=== M2 mutant ==="

WEEK13_M2_MODE=mutant \
WEEK13_M2_RESULT_PATH="${MUTANT_RESULT}" \
COMPILE_ARGS="${COMPILE_ARGS:-} --trace --trace-structs" \
SIM_ARGS="${SIM_ARGS:-} --trace" \
make \
    -f research/week13/mutation/Makefile \
    FORWARDING_VARIANT=m2 \
    SIM="${SIM:-verilator}" \
    SIM_BUILD="${MUTANT_BUILD}"

test -s "${MUTANT_RESULT}"

test -f "${MUTANT_BUILD}/Vtop_classes.mk"

grep -q '^VM_TRACE = 1$' \
    "${MUTANT_BUILD}/Vtop_classes.mk"

grep -q '^VM_TRACE_VCD = 1$' \
    "${MUTANT_BUILD}/Vtop_classes.mk"

test -s "${RAW_WAVE}"

mv "${RAW_WAVE}" "${FINAL_WAVE}"

test -s "${FINAL_WAVE}"

python3 - \
    "${CANON_RESULT}" \
    "${MUTANT_RESULT}" <<'PY_CHECK'
import json
import sys
from pathlib import Path

canonical = json.loads(Path(sys.argv[1]).read_text())
mutant = json.loads(Path(sys.argv[2]).read_text())

assert canonical["target_activation_count"] == 1
assert canonical["checker_failure_count"] == 0
assert canonical["target_forward_a"] == 0
assert canonical["first_failure"] is None

assert mutant["target_activation_count"] == 1
assert mutant["checker_failure_count"] == 1
assert mutant["target_forward_a"] == 2

failure = mutant["first_failure"]

assert failure is not None
assert failure["checker"] == "week5_h18_control"
assert failure["check_name"] == "forward_a_x0_exclusion"
assert failure["expected"] == 0
assert failure["observed"] == 2

assert (
    canonical["target_instruction_id"]
    == mutant["target_instruction_id"]
)

assert canonical["target_pc"] == mutant["target_pc"]

print("canonical_control_pass=true")
print("mutation_target_activated=true")
print("authoritative_checker_failure=true")
print("first_failure_known=true")
print("M2_CAUGHT=PASS")
PY_CHECK

echo "m2_canonical_result=${CANON_RESULT}"
echo "m2_mutant_result=${MUTANT_RESULT}"
echo "m2_waveform=${FINAL_WAVE}"

stat -c 'm2_waveform_bytes=%s' \
    "${FINAL_WAVE}"

sha256sum "${FINAL_WAVE}"
