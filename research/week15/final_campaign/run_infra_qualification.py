from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)

FINAL_ROOT = (
    REPO_ROOT
    / "research/week15/final_campaign"
)

LAUNCH_PATH = (
    FINAL_ROOT
    / "QUALIFICATION_LAUNCH_CONTRACT.json"
)


def sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def load_hashed_json(
    path: Path,
) -> dict[str, Any]:
    sidecar = Path(
        str(path) + ".sha256"
    )

    expected = (
        sidecar.read_text(
            encoding="utf-8"
        )
        .split()[0]
    )

    actual = sha256(path)

    if actual != expected:
        raise RuntimeError(
            f"SHA mismatch for {path}: "
            f"{actual} != {expected}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
    ).strip()


def verify_repository() -> None:
    dirty = git(
        "status",
        "--porcelain",
    )

    if dirty:
        raise RuntimeError(
            "qualification requires "
            "clean repository"
        )

    if (
        git(
            "rev-parse",
            "GATE_T15_COMPLETE^{commit}",
        )
        !=
        "eefdc2da7afa6d5930fa0bf40ab460164d11958e"
    ):
        raise RuntimeError(
            "Gate T15 identity mismatch"
        )


def validate_result(
    result: dict[str, Any],
    *,
    method: str,
    seed: int,
    accepted_budget: int,
) -> None:
    if result.get("seed") != seed:
        raise RuntimeError(
            f"{method}: result seed mismatch"
        )

    if (
        result.get("accepted_budget")
        != accepted_budget
    ):
        raise RuntimeError(
            f"{method}: accepted budget mismatch"
        )

    allowed = {
        "COMPLETED",
        (
            "VALID_DUT_FAILURE_"
            "NONTERMINAL"
        ),
    }

    status = result.get("status")

    if status not in allowed:
        raise RuntimeError(
            f"{method}: invalid status {status!r}"
        )

    if (
        result.get(
            "post_cut_clock_edges"
        )
        != 0
    ):
        raise RuntimeError(
            f"{method}: post-cut clock edge "
            "violation"
        )

    lifecycle = result.get(
        "lifecycle"
    )

    if not isinstance(
        lifecycle,
        dict,
    ):
        raise RuntimeError(
            f"{method}: missing lifecycle"
        )

    accepted = lifecycle.get(
        "accepted"
    )

    retired = lifecycle.get(
        "retired_checked"
    )

    in_flight = lifecycle.get(
        "in_flight"
    )

    if accepted != accepted_budget:
        raise RuntimeError(
            f"{method}: exact-N mismatch"
        )

    if not isinstance(
        retired,
        int,
    ):
        raise RuntimeError(
            f"{method}: invalid retired count"
        )

    if not isinstance(
        in_flight,
        int,
    ):
        raise RuntimeError(
            f"{method}: invalid in-flight count"
        )

    if (
        retired + in_flight
        != accepted
    ):
        raise RuntimeError(
            f"{method}: lifecycle invariant "
            "failed"
        )


def run_one(
    entry: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    method = str(
        entry["method"]
    )

    seed = int(
        entry["seed"]
    )

    budget = int(
        entry["accepted_budget"]
    )

    run_dir = (
        output_root
        / (
            f"{method.lower()}_"
            f"seed_{seed}_"
            f"n_{budget}"
        )
    )

    if run_dir.exists():
        raise RuntimeError(
            f"refusing to overwrite run dir: "
            f"{run_dir}"
        )

    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    build_dir = (
        output_root
        / "_build"
        / method.lower()
    )

    if build_dir.exists():
        shutil.rmtree(
            build_dir
        )

    build_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    result_path = (
        run_dir
        / entry[
            "expected_result_name"
        ]
    )

    results_xml = (
        run_dir
        / "results.xml"
    )

    simulator_log = (
        run_dir
        / "simulator.log"
    )

    command = [
        "make",
        "-C",
        str(
            REPO_ROOT
            / entry[
                "make_directory"
            ]
        ),
        (
            "MODULE="
            + str(
                entry["module"]
            )
        ),
        (
            "SIM_BUILD="
            + str(build_dir)
        ),
        (
            "COCOTB_RESULTS_FILE="
            + str(results_xml)
        ),
    ]

    env = os.environ.copy()

    env.update(
        {
            "W15_FINAL_SEED": str(
                seed
            ),
            "W15_FINAL_BUDGET": str(
                budget
            ),
            "W15_FINAL_PHASE": (
                "qualification"
            ),
            "W15_FINAL_RESULT_DIR": str(
                run_dir
            ),
        }
    )

    with simulator_log.open(
        "w",
        encoding="utf-8",
    ) as log:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )

    record: dict[str, Any] = {
        "method": method,
        "seed": seed,
        "accepted_budget": budget,
        "command": command,
        "returncode": (
            completed.returncode
        ),
        "run_dir": str(run_dir),
        "result_path": str(
            result_path
        ),
        "results_xml": str(
            results_xml
        ),
        "simulator_log": str(
            simulator_log
        ),
        "result_exists": (
            result_path.is_file()
        ),
        "results_xml_exists": (
            results_xml.is_file()
        ),
        "simulator_log_sha256": (
            sha256(simulator_log)
        ),
    }

    if completed.returncode != 0:
        record["classification"] = (
            "INFRA_INVALID"
        )

        return record

    if not results_xml.is_file():
        record["classification"] = (
            "INFRA_INVALID"
        )

        return record

    if not result_path.is_file():
        record["classification"] = (
            "INFRA_INVALID"
        )

        return record

    result = json.loads(
        result_path.read_text(
            encoding="utf-8"
        )
    )

    validate_result(
        result,
        method=method,
        seed=seed,
        accepted_budget=budget,
    )

    record.update(
        {
            "classification": (
                "QUALIFICATION_VALID"
            ),
            "result_status": (
                result["status"]
            ),
            "result_sha256": (
                sha256(result_path)
            ),
            "results_xml_sha256": (
                sha256(results_xml)
            ),
            "lifecycle": (
                result["lifecycle"]
            ),
            "post_cut_clock_edges": (
                result[
                    "post_cut_clock_edges"
                ]
            ),
        }
    )

    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--execute",
        action="store_true",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    launch = load_hashed_json(
        LAUNCH_PATH
    )

    verify_repository()

    output_root = (
        args.output_root
        .expanduser()
        .resolve()
    )

    if (
        output_root == REPO_ROOT
        or REPO_ROOT
        in output_root.parents
    ):
        raise ValueError(
            "output-root must be outside "
            "repository"
        )

    matrix = launch["matrix"]

    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "PLAN_ONLY",
                    "matrix": matrix,
                    "output_root": str(
                        output_root
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )

        return 0

    if output_root.exists():
        if any(
            output_root.iterdir()
        ):
            raise RuntimeError(
                "output-root must be absent "
                "or empty"
            )
    else:
        output_root.mkdir(
            parents=True,
        )

    records = []

    for entry in matrix:
        record = run_one(
            entry,
            output_root,
        )

        records.append(
            record
        )

        if (
            record[
                "classification"
            ]
            != "QUALIFICATION_VALID"
        ):
            break

    full_pass = (
        len(records) == len(matrix)
        and all(
            record[
                "classification"
            ]
            == "QUALIFICATION_VALID"
            for record in records
        )
    )

    summary = {
        "schema": (
            "week15.infra-qualification-"
            "result.v1"
        ),
        "status": (
            "PASS"
            if full_pass
            else "FAIL"
        ),
        "qualification_head": git(
            "rev-parse",
            "HEAD",
        ),
        "runs_expected": len(
            matrix
        ),
        "runs_executed": len(
            records
        ),
        "final_seed_use": 0,
        "performance_used_for_gate": (
            False
        ),
        "coverage_level_used_for_gate": (
            False
        ),
        "results_used_for_tuning": False,
        "runs": records,
    }

    summary_path = (
        output_root
        / "qualification_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "QUALIFICATION_SUMMARY="
        + str(summary_path)
    )

    print(
        "QUALIFICATION_STATUS="
        + summary["status"]
    )

    return 0 if full_pass else 1


if __name__ == "__main__":
    sys.exit(main())
