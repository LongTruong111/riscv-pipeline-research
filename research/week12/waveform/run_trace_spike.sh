#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

TRACE_BUILD="${REPO_ROOT}/sim_build/week12_waveform_spike"
RAW_WAVE="${REPO_ROOT}/dump.vcd"
FINAL_WAVE="${TRACE_BUILD}/week12_trace_spike.vcd"

cd "${REPO_ROOT}"

rm -rf "${TRACE_BUILD}"
rm -f "${RAW_WAVE}"

# Reuse the frozen Week11 integrated-50 runner.
#
# SIM_BUILD is passed as a make command-line variable through MAKEFLAGS,
# so the trace-enabled model cannot reuse the canonical Week11 build.
#
# COMPILE_ARGS/SIM_ARGS enable Verilator tracing directly rather than
# relying on cocotb's deprecated VERILATOR_TRACE variable.
MAKEFLAGS="${MAKEFLAGS:-} SIM_BUILD=${TRACE_BUILD}" \
COMPILE_ARGS="${COMPILE_ARGS:-} --trace --trace-structs" \
SIM_ARGS="${SIM_ARGS:-} --trace" \
N_CYCLES=90 \
SIM=verilator \
research/week11/rtl/run_integrated_50.sh

test -f "${TRACE_BUILD}/Vtop_classes.mk"

grep -q '^VM_TRACE = 1$' \
    "${TRACE_BUILD}/Vtop_classes.mk"

grep -q '^VM_TRACE_VCD = 1$' \
    "${TRACE_BUILD}/Vtop_classes.mk"

test -s "${RAW_WAVE}"

mv "${RAW_WAVE}" "${FINAL_WAVE}"

test -s "${FINAL_WAVE}"

echo "trace_build=${TRACE_BUILD}"
echo "waveform=${FINAL_WAVE}"
stat -c 'waveform_bytes=%s' "${FINAL_WAVE}"
sha256sum "${FINAL_WAVE}"

echo "W0_TRACE_INFRA=PASS"
