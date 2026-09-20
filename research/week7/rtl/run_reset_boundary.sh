#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

FIXTURE="${REPO_ROOT}/research/week5/rtl/fixtures/l1/T01.hex"
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
cp "${FIXTURE}" "${ORIGINAL}"

cd "${REPO_ROOT}"

make -f research/week7/rtl/Makefile \
    MODULE=test_reset_boundary_live \
    SIM="${SIM:-verilator}"

