#!/usr/bin/env bash
set -euo pipefail

mkdir -p sim

iverilog -g2012   -o sim/sim.out   design/RegPack.sv   $(ls design/*.v design/*.sv | grep -v RegPack)   verif/tb_top.sv

vvp sim/sim.out
