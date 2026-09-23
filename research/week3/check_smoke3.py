#!/usr/bin/env python3

import os
import re
import sys
from pathlib import Path

LOG = Path(
    os.environ.get(
        "SMOKE3_LOG",
        "sim/gateT3_smoke_runtime.log",
    )
)

EXPECTED = {
    1: 5,
    2: 7,
    3: 3,
}

if not LOG.exists():
    print(f"FAIL: log not found: {LOG}")
    sys.exit(2)

pattern = re.compile(
    r"Register\s*\[\s*(\d+)\s*\]\s*written with value:"
    r"\s*\[([0-9a-fA-F]+)\]"
)

actual = {}

with LOG.open("r", errors="replace") as f:
    for line in f:
        match = pattern.search(line)
        if not match:
            continue

        reg = int(match.group(1))
        value = int(match.group(2), 16)

        if reg in EXPECTED:
            actual[reg] = value

failed = False

for reg, expected in EXPECTED.items():
    got = actual.get(reg)

    if got is None:
        print(f"FAIL: x{reg} was never written")
        failed = True
    elif got != expected:
        print(f"FAIL: x{reg}: expected {expected}, got {got}")
        failed = True
    else:
        print(f"PASS: x{reg} = {got}")

if failed:
    sys.exit(1)

print("SMOKE3 PASS")
