#!/usr/bin/env bash
set -euo pipefail

CASE="${1:-}"

case "${CASE}" in
    T01|T19|T20)
        ;;
    *)
        echo "usage: $0 {T01|T19|T20}" >&2
        exit 2
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

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

if [[ ! -f "${FIXTURE}" ]]; then
    echo "ERROR: fixture not found: ${FIXTURE}" >&2
    exit 1
fi

cp "${ORIGINAL}" "${BACKUP}"
cp "${FIXTURE}" "${ORIGINAL}"

cd "${REPO_ROOT}"

export CASE
export MODULE=test_week8_live
export PYTHONPATH="${REPO_ROOT}/research/week8/rtl:${REPO_ROOT}:${PYTHONPATH:-}"

rm -f results.xml

make -f research/week7/rtl/Makefile results.xml
