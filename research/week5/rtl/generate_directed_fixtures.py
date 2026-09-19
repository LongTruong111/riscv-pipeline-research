#!/usr/bin/env python3

import json
from pathlib import Path

from research.week5.impl.directed_cases import DIRECTED_CASES
from research.week5.impl.rv32_encode import write_instruction_hex


REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = REPO_ROOT / "research" / "week5" / "rtl" / "fixtures" / "l1"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {}

    for test_id in sorted(DIRECTED_CASES):
        case = DIRECTED_CASES[test_id]

        hex_path = OUTPUT_DIR / f"{test_id}.hex"

        write_instruction_hex(
            hex_path,
            case.words,
        )

        manifest[test_id] = {
            "target_bin": case.target_bin,
            "expected_accepted": case.expected_accepted,
            "oracle_stall_cycles": case.oracle_stall_cycles,
            "oracle_redirect": case.oracle_redirect,
            "instruction_count": len(case.words),
            "description": case.description,
            "hex_file": str(hex_path.relative_to(REPO_ROOT)),
        }

    MANIFEST_PATH.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    print(f"Generated {len(manifest)} directed fixtures")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
