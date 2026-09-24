#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

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

TELEMETRY_PATH="${REPO_ROOT}/sim_build/week12_golden_e2e/golden58_telemetry.json"

GIT_COMMIT="$(git rev-parse HEAD)"

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
    GIT_DIRTY=1
else
    GIT_DIRTY=0
fi

rm -f "${TELEMETRY_PATH}"

python3 - <<'PY'
from pathlib import Path

from research.week6.golden_program import (
    GOLDEN_PROGRAM_INSTRUCTION_COUNT,
    build_golden_program,
)

words = list(build_golden_program())

if len(words) != GOLDEN_PROGRAM_INSTRUCTION_COUNT:
    raise SystemExit(
        f"expected {GOLDEN_PROGRAM_INSTRUCTION_COUNT} instructions, "
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

# Physical IMEM = 128 words = 512 byte-wide entries.
# Zero padding is intentionally outside the supported accepted ISA stream.
image_bytes.extend([0] * (512 - len(image_bytes)))

if len(image_bytes) != 512:
    raise SystemExit(
        f"expected 512 IMEM bytes, got {len(image_bytes)}"
    )

Path("instruction.hex").write_text(
    "".join(f"{byte:02x}\n" for byte in image_bytes),
    encoding="ascii",
)
PY

WEEK12_TELEMETRY_PATH="${TELEMETRY_PATH}" \
WEEK12_GIT_COMMIT="${GIT_COMMIT}" \
WEEK12_GIT_DIRTY="${GIT_DIRTY}" \
make -f research/week12/e2e/Makefile \
    MODULE=test_golden_e2e \
    SIM="${SIM:-verilator}"

test -s "${TELEMETRY_PATH}"

python3 - "${TELEMETRY_PATH}" <<'PY_TELEMETRY_CHECK'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])

payload = json.loads(
    path.read_text(encoding="utf-8")
)

required = {
    "schema_version",
    "git_commit",
    "git_dirty",
    "dut_variant",
    "workload",
    "accepted_instructions",
    "retired_instructions",
    "functional_pass",
    "performance_pass",
    "coverage_valid",
    "coverage_executed",
    "first_failure",
    "waveform_path",
    "waveform_sha256",
}

missing = required - payload.keys()

if missing:
    raise SystemExit(
        f"telemetry missing keys: {sorted(missing)}"
    )

print(f"telemetry={path}")
print(
    "telemetry_summary="
    f"accepted={payload['accepted_instructions']} "
    f"retired={payload['retired_instructions']} "
    f"functional_pass={payload['functional_pass']} "
    f"performance_pass={payload['performance_pass']} "
    f"coverage_valid={payload['coverage_valid']} "
    f"git_dirty={payload['git_dirty']}"
)
PY_TELEMETRY_CHECK

sha256sum "${TELEMETRY_PATH}"

echo "P3_TELEMETRY=PASS"
