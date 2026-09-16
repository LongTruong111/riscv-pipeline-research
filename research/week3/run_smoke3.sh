#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

HEX_BACKUP="$(mktemp)"
VCD_BACKUP="$(mktemp)"

cp instruction.hex "$HEX_BACKUP"

HAD_VCD=0
if [ -f research/waveforms/baseline.vcd ]; then
    cp research/waveforms/baseline.vcd "$VCD_BACKUP"
    HAD_VCD=1
fi

cleanup() {
    cp "$HEX_BACKUP" instruction.hex
    rm -f "$HEX_BACKUP"

    if [ "$HAD_VCD" -eq 1 ]; then
        cp "$VCD_BACKUP" research/waveforms/baseline.vcd
    else
        rm -f research/waveforms/baseline.vcd
    fi

    rm -f "$VCD_BACKUP"
}

trap cleanup EXIT

cp research/week3/smoke3.hex instruction.hex

bash research/build.sh 2>&1 | tee research/week3/gateT3_smoke.log

cp research/waveforms/baseline.vcd \
   research/week3/waveforms/smoke3.vcd
