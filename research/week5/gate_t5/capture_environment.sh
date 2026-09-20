#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

OUT="research/week5/gate_t5/ENVIRONMENT_MANIFEST.txt"

{
    echo "timestamp=$(date --iso-8601=seconds)"
    echo "workspace=$(pwd -P)"
    echo "filesystem=$(stat -f -c '%T' .)"
    echo "git_branch=$(git branch --show-current)"
    echo "git_commit=$(git rev-parse HEAD)"
    echo "python_executable=$(python3 -c 'import sys; print(sys.executable)')"
    echo "python_version=$(python3 --version 2>&1)"
    echo "verilator_version=$(verilator --version 2>&1)"
    echo "cocotb_version=$(python3 -c 'import cocotb; print(cocotb.__version__)')"
    echo "pytest_version=$(pytest --version 2>&1)"
    echo "cpu_count=$(nproc)"
    echo
    echo "===== uname ====="
    uname -a
    echo
    echo "===== OS ====="
    cat /etc/os-release
    echo
    echo "===== CPU ====="
    lscpu
    echo
    echo "===== MEMORY ====="
    free -h
    echo
    echo "===== FILESYSTEM ====="
    df -T .
} > "${OUT}"

echo "Wrote ${OUT}"
