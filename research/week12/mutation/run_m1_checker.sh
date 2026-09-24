#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

TRACE_BUILD="${REPO_ROOT}/sim_build/week12_m1_checker"
RAW_WAVE="${REPO_ROOT}/dump.vcd"
FINAL_WAVE="${TRACE_BUILD}/week12_m1_failure.vcd"
RAW_RESULT="${TRACE_BUILD}/m1_checker_raw.json"

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

rm -rf "${TRACE_BUILD}"
rm -f "${RAW_WAVE}"

mkdir -p "${TRACE_BUILD}"

python3 - <<'PY_FIXTURE'
from pathlib import Path

from research.week11.integrated_sequence import (
    build_week11_integrated_sequence,
)

words = list(
    build_week11_integrated_sequence()
)

if len(words) != 50:
    raise SystemExit(
        f"expected 50 instructions, "
        f"got {len(words)}"
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

image_bytes.extend(
    [0] * (512 - len(image_bytes))
)

if len(image_bytes) != 512:
    raise SystemExit(
        f"expected 512 IMEM bytes, "
        f"got {len(image_bytes)}"
    )

Path("instruction.hex").write_text(
    "".join(
        f"{byte:02x}\n"
        for byte in image_bytes
    ),
    encoding="ascii",
)
PY_FIXTURE

WEEK12_M1_RESULT_PATH="${RAW_RESULT}" \
COMPILE_ARGS="${COMPILE_ARGS:-} --trace --trace-structs" \
SIM_ARGS="${SIM_ARGS:-} --trace" \
make \
    -f research/week12/mutation/Makefile \
    MODULE=test_m1_checker \
    SIM="${SIM:-verilator}" \
    SIM_BUILD="${TRACE_BUILD}"

test -f "${TRACE_BUILD}/Vtop_classes.mk"

grep -q '^VM_TRACE = 1$' \
    "${TRACE_BUILD}/Vtop_classes.mk"

grep -q '^VM_TRACE_VCD = 1$' \
    "${TRACE_BUILD}/Vtop_classes.mk"

test -s "${RAW_RESULT}"
test -s "${RAW_WAVE}"

mv "${RAW_WAVE}" "${FINAL_WAVE}"

test -s "${FINAL_WAVE}"

echo "m1_raw_result=${RAW_RESULT}"
echo "m1_waveform=${FINAL_WAVE}"
stat -c 'm1_waveform_bytes=%s' \
    "${FINAL_WAVE}"

sha256sum "${FINAL_WAVE}"

echo "P5_M1_CHECKER_WAVEFORM=PASS"
