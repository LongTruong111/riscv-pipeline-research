#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

HEX_BACKUP="$(mktemp)"
cp instruction.hex "$HEX_BACKUP"

cleanup() {
    cp "$HEX_BACKUP" instruction.hex
    rm -f "$HEX_BACKUP"
}

trap cleanup EXIT

mkdir -p sim
cp research/week3/smoke3.hex instruction.hex

bash research/build.sh 2>&1 | tee sim/gateT3_smoke_runtime.log
