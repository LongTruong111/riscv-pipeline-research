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
        f"expected exactly 50 instructions, "
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

rm -rf sim_build/week12_m1_activation

make -f research/week12/mutation/Makefile \
    MODULE=test_m1_activation \
    SIM="${SIM:-verilator}"
