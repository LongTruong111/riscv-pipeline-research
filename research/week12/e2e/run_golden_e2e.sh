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

make -f research/week12/e2e/Makefile \
    MODULE=test_golden_e2e \
    SIM="${SIM:-verilator}"
