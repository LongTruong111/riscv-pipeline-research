#!/usr/bin/env bash
set -euo pipefail

echo "=== Research environment ==="
python3 --version
python3 -c "import cocotb; print('cocotb', cocotb.__version__)"
pytest --version
iverilog -V 2>&1 | head -1
verilator --version

if command -v gtkwave >/dev/null 2>&1; then
    gtkwave --version 2>&1 | head -1
else
    echo "gtkwave: not installed"
fi

if command -v riscv64-unknown-elf-gcc >/dev/null 2>&1; then
    riscv64-unknown-elf-gcc --version | head -1
elif command -v riscv32-unknown-elf-gcc >/dev/null 2>&1; then
    riscv32-unknown-elf-gcc --version | head -1
else
    echo "RISC-V GCC: not installed"
fi
