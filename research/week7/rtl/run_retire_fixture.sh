#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

case "${MODE}" in
    normal)
        FIXTURE="${REPO_ROOT}/research/week5/rtl/fixtures/l1/T01.hex"
        EXPECT_ACCEPTED=2
        EXPECT_STALL=0
        EXPECT_FLUSH=0
        ;;
    stall)
        FIXTURE="${REPO_ROOT}/research/week5/rtl/fixtures/stall.hex"
        EXPECT_ACCEPTED=4
        EXPECT_STALL=1
        EXPECT_FLUSH=0
        ;;
    flush)
        FIXTURE="${REPO_ROOT}/research/week5/rtl/fixtures/flush.hex"
        EXPECT_ACCEPTED=3
        EXPECT_STALL=0
        EXPECT_FLUSH=1
        ;;
    *)
        echo "usage: $0 {normal|stall|flush}" >&2
        exit 2
        ;;
esac

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

EXPECT_ACCEPTED="${EXPECT_ACCEPTED}" \
EXPECT_STALL="${EXPECT_STALL}" \
EXPECT_FLUSH="${EXPECT_FLUSH}" \
N_CYCLES="${N_CYCLES:-60}" \
make -f research/week7/rtl/Makefile \
    SIM="${SIM:-verilator}"
