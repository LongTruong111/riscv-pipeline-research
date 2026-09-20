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

# ----------------------------------------------------------------------
# Intent regression accounting
# ----------------------------------------------------------------------

PASS_COUNT=0
FAIL_COUNT=0
RUN_COUNT=0

declare -a FAILED_CASES=()

# ----------------------------------------------------------------------
# Canonical Validated-Coverage accounting
#
# A target is counted as validated only when the live per-hit promotion
# layer reports target_l1_validated=1 for that case's canonical target bin.
#
# UNKNOWN is kept separate from UNVALIDATED so missing telemetry or a
# simulation/infrastructure failure is never silently classified as a DUT
# correctness failure.
# ----------------------------------------------------------------------

VALIDATED_PASS_COUNT=0
VALIDATED_REJECTED_COUNT=0
VALIDATED_UNKNOWN_COUNT=0

declare -a UNVALIDATED_BINS=()
declare -a VALIDATION_UNKNOWN_CASES=()

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
printf " Week 5 L1 Directed Canonical Regression\n"
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

        VALIDATED_UNKNOWN_COUNT=$((VALIDATED_UNKNOWN_COUNT + 1))

        FAILED_CASES+=("${TEST_ID}")
        VALIDATION_UNKNOWN_CASES+=("${TEST_ID}")

        continue
    fi

    RUN_COUNT=$((RUN_COUNT + 1))

    cp "${FIXTURE}" "${INSTRUCTION_HEX}"

    LOG_FILE="$(mktemp)"

    printf "[%s -> %s] running ... " \
        "${TEST_ID}" \
        "${TARGET_BIN}"

    set +e

    # These remain zero intentionally:
    #
    # the directed runner checks Intent reachability independently from
    # DUT realization. Control/architectural correctness is collected by
    # the live Validated-Coverage layer instead of changing Intent PASS.
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
            | sed -E \
                's/^.*EXECUTION_STREAM_SMOKE/EXECUTION_STREAM_SMOKE/' \
            || true
    )"

    DIAGNOSTICS="$(
        grep -E \
            'CONTROL_REALIZATION_FAIL|ARCHITECTURAL_REALIZATION_FAIL|L1_VALIDATION_REJECT' \
            "${LOG_FILE}" \
            || true
    )"

    TARGET_VALIDATED="$(
        printf '%s\n' "${SUMMARY}" \
            | sed -nE \
                's/.*target_l1_validated=(-1|0|1).*/\1/p' \
            | tail -n 1
    )"

    if [[ ${STATUS} -eq 0 ]]; then
        PASS_COUNT=$((PASS_COUNT + 1))

        printf "PASS\n"

        if [[ -n "${SUMMARY}" ]]; then
            printf "    %s\n" "${SUMMARY}"
        fi

        if [[ -n "${DIAGNOSTICS}" ]]; then
            printf "%s\n" "${DIAGNOSTICS}" \
                | sed 's/^/    /'
        fi

        printf \
            "    oracle: stall=%s redirect=%s\n" \
            "${ORACLE_STALL}" \
            "${ORACLE_REDIRECT}"

        case "${TARGET_VALIDATED}" in
            1)
                VALIDATED_PASS_COUNT=$((VALIDATED_PASS_COUNT + 1))
                ;;

            0)
                VALIDATED_REJECTED_COUNT=$((VALIDATED_REJECTED_COUNT + 1))

                UNVALIDATED_BINS+=("${TARGET_BIN}")
                ;;

            *)
                VALIDATED_UNKNOWN_COUNT=$((VALIDATED_UNKNOWN_COUNT + 1))

                VALIDATION_UNKNOWN_CASES+=("${TEST_ID}")
                ;;
        esac

    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        FAILED_CASES+=("${TEST_ID}")

        VALIDATED_UNKNOWN_COUNT=$((VALIDATED_UNKNOWN_COUNT + 1))
        VALIDATION_UNKNOWN_CASES+=("${TEST_ID}")

        printf "FAIL\n"

        if [[ -n "${SUMMARY}" ]]; then
            printf "    %s\n" "${SUMMARY}"
        fi

        if [[ -n "${DIAGNOSTICS}" ]]; then
            printf "%s\n" "${DIAGNOSTICS}" \
                | sed 's/^/    /'
        fi

        printf \
            "    oracle: stall=%s redirect=%s\n" \
            "${ORACLE_STALL}" \
            "${ORACLE_REDIRECT}"

        printf "\n"
        printf -- \
            "---------------- FAILURE LOG: %s ----------------\n" \
            "${TEST_ID}"

        cat "${LOG_FILE}"

        printf -- \
            "-------------- END FAILURE LOG: %s --------------\n\n" \
            "${TEST_ID}"
    fi

    rm -f "${LOG_FILE}"
done

# ----------------------------------------------------------------------
# Summary percentages
# ----------------------------------------------------------------------

INTENT_PERCENT="$(
    awk \
        -v passed="${PASS_COUNT}" \
        -v total="${RUN_COUNT}" \
        'BEGIN {
            if (total == 0) {
                printf "0.0"
            } else {
                printf "%.1f", 100.0 * passed / total
            }
        }'
)"

if [[ ${VALIDATED_UNKNOWN_COUNT} -eq 0 ]]; then
    VALIDATED_PERCENT="$(
        awk \
            -v passed="${VALIDATED_PASS_COUNT}" \
            -v total="${RUN_COUNT}" \
            'BEGIN {
                if (total == 0) {
                    printf "0.0"
                } else {
                    printf "%.1f", 100.0 * passed / total
                }
            }'
    )"
else
    VALIDATED_PERCENT="N/A"
fi

printf "\n"
printf "============================================================\n"
printf " L1 Directed Canonical Summary\n"
printf "============================================================\n"

printf "INTENT RUN          : %d\n" "${RUN_COUNT}"
printf "INTENT PASS         : %d\n" "${PASS_COUNT}"
printf "INTENT FAIL         : %d\n" "${FAIL_COUNT}"
printf \
    "INTENT COVERAGE     : %d/%d (%s%%)\n" \
    "${PASS_COUNT}" \
    "${RUN_COUNT}" \
    "${INTENT_PERCENT}"

printf "\n"

printf \
    "VALIDATED PASS      : %d\n" \
    "${VALIDATED_PASS_COUNT}"

printf \
    "VALIDATED REJECTED  : %d\n" \
    "${VALIDATED_REJECTED_COUNT}"

printf \
    "VALIDATED UNKNOWN   : %d\n" \
    "${VALIDATED_UNKNOWN_COUNT}"

if [[ ${VALIDATED_UNKNOWN_COUNT} -eq 0 ]]; then
    printf \
        "VALIDATED COVERAGE  : %d/%d (%s%%)\n" \
        "${VALIDATED_PASS_COUNT}" \
        "${RUN_COUNT}" \
        "${VALIDATED_PERCENT}"
else
    printf \
        "VALIDATED COVERAGE  : N/A (%d/%d targets validated; %d unknown)\n" \
        "${VALIDATED_PASS_COUNT}" \
        "${RUN_COUNT}" \
        "${VALIDATED_UNKNOWN_COUNT}"
fi

printf "\n"

if [[ ${#UNVALIDATED_BINS[@]} -gt 0 ]]; then
    printf "UNVALIDATED BINS    :"

    for bin_id in "${UNVALIDATED_BINS[@]}"; do
        printf " %s" "${bin_id}"
    done

    printf "\n"
else
    printf "UNVALIDATED BINS    : none\n"
fi

if [[ ${FAIL_COUNT} -ne 0 ]]; then
    printf "FAILED CASES        :"

    for test_id in "${FAILED_CASES[@]}"; do
        printf " %s" "${test_id}"
    done

    printf "\n"
fi

if [[ ${VALIDATED_UNKNOWN_COUNT} -ne 0 ]]; then
    printf "VALIDATION UNKNOWN  :"

    for test_id in "${VALIDATION_UNKNOWN_CASES[@]}"; do
        printf " %s" "${test_id}"
    done

    printf "\n"
fi

printf "============================================================\n"

# A simulation/Intent failure remains a regression failure.
#
# Missing Validated-Coverage telemetry is also an infrastructure failure:
# it must not be silently converted into an unvalidated DUT bin.
if [[ ${FAIL_COUNT} -ne 0 ]] ||
   [[ ${VALIDATED_UNKNOWN_COUNT} -ne 0 ]]; then
    exit 1
fi
