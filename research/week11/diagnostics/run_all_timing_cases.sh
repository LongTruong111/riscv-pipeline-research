#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
FIXTURE_DIR="${REPO_ROOT}/research/week5/rtl/fixtures/l1"
ORIGINAL="${REPO_ROOT}/instruction.hex"
BACKUP="$(mktemp)"

cleanup() {
    cp "${BACKUP}" "${ORIGINAL}"
    rm -f "${BACKUP}"
}
trap cleanup EXIT INT TERM HUP

cp "${ORIGINAL}" "${BACKUP}"

cd "${REPO_ROOT}"

for n in $(seq -w 1 20); do
    case_id="T${n}"
    fixture="${FIXTURE_DIR}/${case_id}.hex"

    echo
    echo "===== ${case_id} ====="

    cp "${fixture}" "${ORIGINAL}"

    TIMING_CASE="${case_id}" \
    N_CYCLES=80 \
    make -f research/week7/rtl/Makefile \
        MODULE=test_timing_retire_live \
        SIM=verilator \
        2>&1 | tee "/tmp/week11_${case_id}_timing.log"

    echo "PASS ${case_id}"
done
