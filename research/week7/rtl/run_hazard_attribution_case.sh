#!/usr/bin/env bash
set -euo pipefail

CASE="${1:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

case "${CASE}" in
    T01|T06|T15)
        ;;
    *)
        echo "usage: $0 {T01|T06|T15}" >&2
        exit 2
        ;;
esac

FIXTURE="${REPO_ROOT}/research/week5/rtl/fixtures/l1/${CASE}.hex"
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

ATTRIBUTION_CASE="${CASE}" \
N_CYCLES="${N_CYCLES:-60}" \
make -f research/week7/rtl/Makefile \
    MODULE=test_hazard_attribution_live \
    SIM="${SIM:-verilator}"

