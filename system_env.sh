#!/usr/bin/env bash

# Frozen development environment — GĐ1

# Ubuntu / WSL2: Ubuntu 22.04 LTS
# Python: 3.10.12
# Cocotb: 1.9.2
# Icarus Verilog: 11.0
# Verilator: 5.034
# GTKWave: <điền output thật>
# RISC-V GCC: <điền output thật>

python3 --version
python3 -c "import cocotb; print('cocotb', cocotb.__version__)"
iverilog -V | head -1
verilator --version
gtkwave --version 2>&1 | head -1
