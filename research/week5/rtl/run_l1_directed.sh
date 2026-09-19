#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

FIXTURE_DIR="${SCRIPT_DIR}/fixtures/l1"
INSTRUCTION_HEX="${REPO_ROOT}/instruction.hex"

SIM="${SIM:-verilator}"
N_CYCLES="${N_CYCLES:-60}"

# Optional:
#   ./run_l1_directed.sh         -> run T01..T20
#   ./run_l1_directed.sh T06     -> run only T06
SELECTED_CASE="${1:-}"

cd "${REPO_ROOT}"

if [[ ! -f "${INSTRUCTION_HEX}" ]]; then
    echo "ERROR: instruction.hex not found: ${INSTRUCTION_HEX}" >&2
    exit 1
fi

if [[ ! -d "${FIXTURE_DIR}" ]]; then
    echo "ERROR: fixture directory not found: ${FIXTURE_DIR}" >&2
    exit 1
fi

if [[ -n "${SELECTED_CASE}" ]] &&
   [[ ! "${SELECTED_CASE}" =~ ^T(0[1-9]|1[0-9]|20)$ ]]; then
    echo "ERROR: invalid case '${SELECTED_CASE}'. Expected T01..T20." >&2
    exit 1
fi

BACKUP="$(mktemp)"
cp "${INSTRUCTION_HEX}" "${BACKUP}"

cleanup() {
    cp "${BACKUP}" "${INSTRUCTION_HEX}"
    rm -f "${BACKUP}"
}
trap cleanup EXIT INT TERM

PASS_COUNT=0
FAIL_COUNT=0
RUN_COUNT=0

declare -a FAILED_CASES=()

mapfile -t CASE_ROWS < <(
    PYTHONPATH="${REPO_ROOT}" python3 - <<'PY'
from research.week5.impl.directed_cases import DIRECTED_CASES

for test_id in sorted(DIRECTED_CASES):
    case = DIRECTED_CASES[test_id]
    print(
        f"{test_id}\t"
        f"{case.target_bin}\t"
        f"{case.expected_accepted}\t"
        f"{case.oracle_stall_cycles}\t"
        f"{int(case.oracle_redirect)}"
    )
PY
)

printf "\n"
printf "============================================================\n"
printf " Week 5 L1 Directed Intent Regression\n"
printf "============================================================\n"
printf "SIM       : %s\n" "${SIM}"
printf "N_CYCLES  : %s\n" "${N_CYCLES}"

if [[ -n "${SELECTED_CASE}" ]]; then
    printf "CASE      : %s\n" "${SELECTED_CASE}"
else
    printf "CASE      : T01..T20\n"
fi

printf "============================================================\n\n"

for row in "${CASE_ROWS[@]}"; do
    IFS=$'\t' read -r \
        TEST_ID \
        TARGET_BIN \
        EXPECTED_ACCEPTED \
        ORACLE_STALL \
        ORACLE_REDIRECT \
        <<< "${row}"

    if [[ -n "${SELECTED_CASE}" ]] &&
       [[ "${TEST_ID}" != "${SELECTED_CASE}" ]]; then
        continue
    fi

    FIXTURE="${FIXTURE_DIR}/${TEST_ID}.hex"

    if [[ ! -f "${FIXTURE}" ]]; then
        echo "[${TEST_ID}] FAIL: fixture missing: ${FIXTURE}"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        RUN_COUNT=$((RUN_COUNT + 1))
        FAILED_CASES+=("${TEST_ID}")
        continue
    fi

    RUN_COUNT=$((RUN_COUNT + 1))

    cp "${FIXTURE}" "${INSTRUCTION_HEX}"

    LOG_FILE="$(mktemp)"

    printf "[%s -> %s] running ... " \
        "${TEST_ID}" \
        "${TARGET_BIN}"

    set +e

    EXPECT_STALL=0 \
    EXPECT_FLUSH=0 \
    EXPECT_ACCEPTED="${EXPECTED_ACCEPTED}" \
    EXPECT_L1_BIN="${TARGET_BIN}" \
    N_CYCLES="${N_CYCLES}" \
    make \
        -f research/week5/rtl/Makefile \
        SIM="${SIM}" \
        >"${LOG_FILE}" 2>&1

    STATUS=$?

    set -e

    SUMMARY="$(
        grep 'EXECUTION_STREAM_SMOKE' "${LOG_FILE}" \
            | tail -n 1 \
            | sed -E 's/^.*EXECUTION_STREAM_SMOKE/EXECUTION_STREAM_SMOKE/' \
            || true
    )"

    if [[ ${STATUS} -eq 0 ]]; then
        PASS_COUNT=$((PASS_COUNT + 1))

        printf "PASS\n"

        if [[ -n "${SUMMARY}" ]]; then
            printf "    %s\n" "${SUMMARY}"
        fi

        printf \
            "    oracle: stall=%s redirect=%s\n" \
            "${ORACLE_STALL}" \
            "${ORACLE_REDIRECT}"
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        FAILED_CASES+=("${TEST_ID}")

        printf "FAIL\n"

        if [[ -n "${SUMMARY}" ]]; then
            printf "    %s\n" "${SUMMARY}"
        fi

        printf \
            "    oracle: stall=%s redirect=%s\n" \
            "${ORACLE_STALL}" \
            "${ORACLE_REDIRECT}"

        printf "\n"
        printf -- "---------------- FAILURE LOG: %s ----------------\n" \
            "${TEST_ID}"

        cat "${LOG_FILE}"

        printf -- "-------------- END FAILURE LOG: %s --------------\n\n" \
            "${TEST_ID}"
    fi

    rm -f "${LOG_FILE}"
done

printf "\n"
printf "============================================================\n"
printf " L1 Directed Intent Summary\n"
printf "============================================================\n"
printf "RUN   : %d\n" "${RUN_COUNT}"
printf "PASS  : %d\n" "${PASS_COUNT}"
printf "FAIL  : %d\n" "${FAIL_COUNT}"

if [[ ${FAIL_COUNT} -ne 0 ]]; then
    printf "FAILED:"
    printf " %s" "${FAILED_CASES[@]}"
    printf "\n"
fi

printf "============================================================\n"

if [[ ${FAIL_COUNT} -ne 0 ]]; then
    exit 1
fi
