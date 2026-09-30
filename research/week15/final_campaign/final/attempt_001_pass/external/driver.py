#!/usr/bin/env python3

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


REPO = Path.home() / "nckh/risc-v-pipeline"

EXPECTED_HEAD = (
    "086e8127101aca9a934bec77af84dc5f87160f09"
)

ROOT = REPO / "research/week15/final_campaign"

EXEC = ROOT / "EXECUTION_CONTRACT.json"
LAUNCH = ROOT / "QUALIFICATION_LAUNCH_CONTRACT.json"
CLOSURE = ROOT / "INFRA_QUALIFICATION_CLOSURE.json"
MANIFEST = ROOT / "HARNESS_MANIFEST.json"

RUNTIME = ROOT / "runtime_config.py"
M1 = ROOT / "test_m1_final.py"
M2 = ROOT / "test_m2_final.py"
M3 = ROOT / "test_m3_final.py"

EXPECTED_HASHES = {
    EXEC: (
        "2f17686ec167a25c6df5369ee2372eb8"
        "ac7670a2b28dbf5b774edbf7b54f263f"
    ),
    LAUNCH: (
        "9aa2304dfe144bfa3e751638777ffa6e"
        "d5e9eeeb6ae080391c0ca49f00d6b6cd"
    ),
    CLOSURE: (
        "ab46fd743f734e5cf56af82ff577c5a4"
        "d0fc94a7a76a158fc1e0d3ea5fe3f008"
    ),
    MANIFEST: (
        "ca03d7d2ce24e4b5d69353db871acce7"
        "f0b7e7404db03668c03a933f64a659c4"
    ),
    RUNTIME: (
        "bf0a8f0ced9c5cbed5d4ffced37f4902"
        "48e1d5d303d064e6c5d76e9dbeb9ae6b"
    ),
    M1: (
        "0bb3566a001ed7760b82e92ed6d25815"
        "967eb3b0845e6209ac1c64833163d100"
    ),
    M2: (
        "e22821b80364b85d243be322ba76dc39"
        "5a4a645a9d1e0d8aadfb2dab3d1a2a79"
    ),
    M3: (
        "d4e2ae4a1b3dae78a3fa1ed4d8d204"
        "1dd4885785f1b2e37a13c7adcbe02142e3"
    ),
}

ELIGIBLE_FIXED_N = {
    "COMPLETED",
    "VALID_DUT_FAILURE_NONTERMINAL",
}

TERMINAL = "VALID_DUT_FAILURE_TERMINAL"

BUDGET = 100000


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def atomic_json(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    tmp.replace(path)


def git(*args: str) -> str:
    return subprocess.check_output(
        [
            "git",
            "-C",
            str(REPO),
            *args,
        ],
        text=True,
    ).strip()


def verify_repo_authority() -> None:
    head = git("rev-parse", "HEAD")

    if head != EXPECTED_HEAD:
        raise RuntimeError(
            "repository HEAD changed: "
            f"{head}"
        )

    dirty = git(
        "status",
        "--porcelain",
    )

    if dirty:
        raise RuntimeError(
            "repository worktree is not clean"
        )

    for path, expected in EXPECTED_HASHES.items():
        actual = sha256(path)

        if actual != expected:
            raise RuntimeError(
                "authority hash mismatch: "
                f"{path}: {actual}"
            )


def canonical_budget(
    result: dict[str, Any],
) -> int:
    top = result.get(
        "accepted_budget"
    )

    nested = (
        result
        .get("configuration", {})
        .get("accepted_budget")
    )

    if (
        top is not None
        and nested is not None
        and int(top) != int(nested)
    ):
        raise RuntimeError(
            "conflicting accepted_budget fields"
        )

    value = (
        top
        if top is not None
        else nested
    )

    if value is None:
        raise RuntimeError(
            "missing accepted_budget"
        )

    return int(value)


def canonical_lifecycle(
    result: dict[str, Any],
) -> tuple[int, int, int]:
    life = result.get("lifecycle")

    if not isinstance(life, dict):
        raise RuntimeError(
            "missing lifecycle"
        )

    accepted = int(
        life["accepted"]
    )

    retired = int(
        life["retired_checked"]
    )

    if "in_flight" in life:
        in_flight = int(
            life["in_flight"]
        )
    elif "in_flight_at_cut" in life:
        in_flight = int(
            life["in_flight_at_cut"]
        )
    else:
        raise RuntimeError(
            "missing in-flight lifecycle field"
        )

    return (
        accepted,
        retired,
        in_flight,
    )


def make_specs(
    launch: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    specs = {}

    for entry in launch["matrix"]:
        method = entry["method"]

        if method in specs:
            raise RuntimeError(
                f"duplicate qualification method {method}"
            )

        specs[method] = {
            "make_directory": (
                entry["make_directory"]
            ),
            "module": entry["module"],
        }

    if set(specs) != {
        "M1",
        "M2",
        "M3",
    }:
        raise RuntimeError(
            "qualification make-spec set mismatch"
        )

    return specs


def frozen_runs(
    execution: dict[str, Any],
) -> list[dict[str, Any]]:
    expected = {
        "M1": list(
            range(1001, 1016)
        ),
        "M2": list(
            range(2001, 2016)
        ),
        "M3": list(
            range(3001, 3016)
        ),
    }

    actual = {
        method: execution[
            "final_campaign"
        ][f"{method}_seeds"]
        for method in (
            "M1",
            "M2",
            "M3",
        )
    }

    if actual != expected:
        raise RuntimeError(
            "frozen final seed domain mismatch"
        )

    if (
        execution["final_campaign"]
        ["total_runs"]
        != 45
    ):
        raise RuntimeError(
            "total_runs mismatch"
        )

    if (
        execution["final_campaign"]
        ["total_accepted_budget"]
        != 4_500_000
    ):
        raise RuntimeError(
            "total accepted budget mismatch"
        )

    runs = []

    index = 0

    for method in (
        "M1",
        "M2",
        "M3",
    ):
        for seed in expected[method]:
            index += 1

            runs.append({
                "index": index,
                "method": method,
                "seed": seed,
                "accepted_budget": BUDGET,
            })

    if len(runs) != 45:
        raise RuntimeError(
            "run count mismatch"
        )

    return runs


def verify_plan(
    plan_path: Path,
) -> dict[str, Any]:
    plan = read_json(plan_path)

    if (
        plan["schema"]
        !=
        "week15.final-campaign-external-driver-plan.v1"
    ):
        raise RuntimeError(
            "invalid plan schema"
        )

    if (
        plan["authority_head"]
        != EXPECTED_HEAD
    ):
        raise RuntimeError(
            "plan authority HEAD mismatch"
        )

    driver_path = Path(
        plan["driver_path"]
    )

    if (
        sha256(driver_path)
        != plan["driver_sha256"]
    ):
        raise RuntimeError(
            "driver SHA mismatch"
        )

    verify_repo_authority()

    execution = read_json(EXEC)
    launch = read_json(LAUNCH)
    closure = read_json(CLOSURE)

    if closure["status"] != "PASS":
        raise RuntimeError(
            "infra closure is not PASS"
        )

    if (
        launch["status"]
        != "INFRA_QUALIFICATION_PASS_CLOSED"
    ):
        raise RuntimeError(
            "launch contract is not closed"
        )

    if (
        launch["final_campaign"]["status"]
        !=
        "AUTHORIZED_AFTER_INFRA_QUALIFICATION_CLOSURE"
    ):
        raise RuntimeError(
            "final campaign not authorized"
        )

    if (
        launch["final_campaign"]
        ["final_seed_use"]
        != 0
    ):
        raise RuntimeError(
            "unexpected recorded final seed use"
        )

    runs = frozen_runs(
        execution
    )

    if plan["runs"] != runs:
        raise RuntimeError(
            "plan run sequence mismatch"
        )

    specs = make_specs(
        launch
    )

    if (
        plan["make_specs"]
        != specs
    ):
        raise RuntimeError(
            "plan make specs mismatch"
        )

    return plan


def load_runtime_for(
    method: str,
    seed: int,
    result_dir: Path,
):
    if str(REPO) not in sys.path:
        sys.path.insert(
            0,
            str(REPO),
        )

    from research.week15.final_campaign.runtime_config import (
        load_final_runtime_config,
    )

    return load_final_runtime_config(
        method,
        {
            "W15_FINAL_SEED": str(seed),
            "W15_FINAL_BUDGET": str(BUDGET),
            "W15_FINAL_PHASE": "final",
            "W15_FINAL_RESULT_DIR": (
                str(result_dir)
            ),
        },
    )


def preflight(plan: dict[str, Any]) -> int:
    out = Path(
        plan["output_root"]
    )

    if out.exists():
        raise RuntimeError(
            "final output root already exists"
        )

    probe_root = Path(
        "/tmp/week15_final_campaign_"
        "preflight_runtime_probe"
    )

    if probe_root.exists():
        shutil.rmtree(
            probe_root
        )

    for run in plan["runs"]:
        cfg = load_runtime_for(
            run["method"],
            run["seed"],
            (
                probe_root
                / (
                    f"{run['index']:02d}_"
                    f"{run['method'].lower()}_"
                    f"seed_{run['seed']}"
                )
            ),
        )

        if cfg.phase != "final":
            raise RuntimeError(
                "runtime phase mismatch"
            )

        if cfg.root_seed != run["seed"]:
            raise RuntimeError(
                "runtime seed mismatch"
            )

        if cfg.accepted_budget != BUDGET:
            raise RuntimeError(
                "runtime budget mismatch"
            )

        if (
            cfg.result_dir
            == REPO
            or REPO in cfg.result_dir.parents
        ):
            raise RuntimeError(
                "runtime result dir inside repo"
            )

    if probe_root.exists():
        raise RuntimeError(
            "runtime-config preflight "
            "unexpectedly created output"
        )

    print(
        "FINAL_DRIVER_PREFLIGHT=PASS"
    )
    print(
        "FINAL_RUNS=45"
    )
    print(
        "FINAL_ACCEPTED_BUDGET=4500000"
    )
    print(
        "FIRST_RUN=M1:1001"
    )
    print(
        "LAST_RUN=M3:3015"
    )
    print(
        "SIMULATION_EXECUTED=NO"
    )
    print(
        "FINAL_SEED_EXECUTED=NO"
    )

    return 0


def result_json_from_run_dir(
    run_dir: Path,
) -> Path:
    candidates = sorted(
        p
        for p in run_dir.glob("*.json")
        if p.is_file()
    )

    if len(candidates) != 1:
        raise RuntimeError(
            "expected exactly one harness "
            "result JSON, got "
            f"{len(candidates)}"
        )

    return candidates[0]


def validate_fixed_n_result(
    result: dict[str, Any],
    method: str,
    seed: int,
) -> dict[str, Any]:
    if result.get("phase") != "final":
        raise RuntimeError(
            "result phase is not final"
        )

    if int(result.get("seed")) != seed:
        raise RuntimeError(
            "result seed mismatch"
        )

    if canonical_budget(result) != BUDGET:
        raise RuntimeError(
            "result accepted budget mismatch"
        )

    status = result.get("status")

    if status not in ELIGIBLE_FIXED_N:
        raise RuntimeError(
            "result status is not fixed-N eligible"
        )

    if (
        result.get(
            "post_cut_clock_edges"
        )
        != 0
    ):
        raise RuntimeError(
            "post-cut clock edge mismatch"
        )

    accepted, retired, in_flight = (
        canonical_lifecycle(
            result
        )
    )

    if accepted != BUDGET:
        raise RuntimeError(
            "accepted count mismatch"
        )

    if (
        retired
        + in_flight
        != accepted
    ):
        raise RuntimeError(
            "lifecycle invariant mismatch"
        )

    return {
        "status": status,
        "accepted": accepted,
        "retired_checked": retired,
        "in_flight": in_flight,
        "post_cut_clock_edges": 0,
    }


def validate_terminal_result(
    result: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    if result.get("phase") != "final":
        raise RuntimeError(
            "terminal result phase mismatch"
        )

    if int(result.get("seed")) != seed:
        raise RuntimeError(
            "terminal result seed mismatch"
        )

    if canonical_budget(result) != BUDGET:
        raise RuntimeError(
            "terminal result budget mismatch"
        )

    if result.get("status") != TERMINAL:
        raise RuntimeError(
            "not terminal DUT failure"
        )

    if (
        result.get(
            "terminal_divergence_status"
        )
        != "OBSERVED"
    ):
        raise RuntimeError(
            "terminal divergence not observed"
        )

    if (
        "fixed_budget_complete"
        in result
        and
        result["fixed_budget_complete"]
        is not False
    ):
        raise RuntimeError(
            "terminal fixed_budget_complete "
            "must be false"
        )

    return {
        "status": TERMINAL,
        "terminal_divergence_status": (
            "OBSERVED"
        ),
        "fixed_budget_complete": False,
    }


def file_hash_or_none(
    path: Path,
) -> str | None:
    if not path.is_file():
        return None

    return sha256(path)


def execute(plan: dict[str, Any]) -> int:
    verify_repo_authority()

    out = Path(
        plan["output_root"]
    )

    if out.exists():
        raise RuntimeError(
            "refusing to reuse final campaign "
            "output root"
        )

    runs_root = out / "runs"
    build_root = out / "_build"
    state_root = out / "state"

    runs_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    build_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    state_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    shutil.copy2(
        Path(plan["driver_path"]),
        out / "driver.py",
    )

    shutil.copy2(
        Path(plan["plan_path"]),
        out / "plan.json",
    )

    atomic_json(
        out / "campaign_state.json",
        {
            "schema": (
                "week15.final-campaign-"
                "execution-state.v1"
            ),
            "authority_head": EXPECTED_HEAD,
            "status": "RUNNING",
            "runs_expected": 45,
            "runs_started": 0,
            "runs_finished": 0,
            "final_seed_use": 0,
            "records": [],
        },
    )

    records = []
    started = 0
    finished = 0

    for run in plan["runs"]:
        verify_repo_authority()

        index = run["index"]
        method = run["method"]
        seed = run["seed"]

        spec = plan[
            "make_specs"
        ][method]

        label = (
            f"{index:02d}_"
            f"{method.lower()}_"
            f"seed_{seed}_"
            f"n_{BUDGET}"
        )

        run_dir = runs_root / label
        build_dir = build_root / label

        if (
            run_dir.exists()
            or build_dir.exists()
        ):
            raise RuntimeError(
                "run/build directory already exists"
            )

        run_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        build_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        cfg = load_runtime_for(
            method,
            seed,
            run_dir,
        )

        if (
            cfg.phase != "final"
            or cfg.root_seed != seed
            or cfg.accepted_budget != BUDGET
        ):
            raise RuntimeError(
                "runtime binding changed"
            )

        started += 1

        start_record = {
            "schema": (
                "week15.final-campaign-"
                "run-start.v1"
            ),
            "index": index,
            "method": method,
            "seed": seed,
            "accepted_budget": BUDGET,
            "authority_head": EXPECTED_HEAD,
            "final_seed_use_after_start": (
                started
            ),
        }

        atomic_json(
            state_root
            / (
                f"{index:02d}_"
                f"{method}_"
                f"{seed}.started.json"
            ),
            start_record,
        )

        atomic_json(
            out / "campaign_state.json",
            {
                "schema": (
                    "week15.final-campaign-"
                    "execution-state.v1"
                ),
                "authority_head": (
                    EXPECTED_HEAD
                ),
                "status": "RUNNING",
                "current_run": start_record,
                "runs_expected": 45,
                "runs_started": started,
                "runs_finished": finished,
                "final_seed_use": started,
                "records": records,
            },
        )

        env = os.environ.copy()

        env.update({
            "W15_FINAL_SEED": str(seed),
            "W15_FINAL_BUDGET": str(BUDGET),
            "W15_FINAL_PHASE": "final",
            "W15_FINAL_RESULT_DIR": (
                str(run_dir)
            ),
        })

        xml_path = (
            run_dir / "results.xml"
        )

        log_path = (
            run_dir / "simulator.log"
        )

        command = [
            "make",
            "-C",
            str(
                REPO
                / spec["make_directory"]
            ),
            (
                "MODULE="
                + spec["module"]
            ),
            (
                "SIM_BUILD="
                + str(build_dir)
            ),
            (
                "COCOTB_RESULTS_FILE="
                + str(xml_path)
            ),
        ]

        with log_path.open(
            "wb"
        ) as log:
            completed = subprocess.run(
                command,
                cwd=REPO,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )

        rc = int(
            completed.returncode
        )

        result_path = None
        result = None
        result_parse_error = None

        try:
            result_path = (
                result_json_from_run_dir(
                    run_dir
                )
            )

            result = read_json(
                result_path
            )
        except Exception as exc:
            result_parse_error = (
                type(exc).__name__
                + ": "
                + str(exc)
            )

        classification = None
        validation = None

        if (
            result is not None
            and xml_path.is_file()
        ):
            status = result.get(
                "status"
            )

            if (
                rc == 0
                and status
                in ELIGIBLE_FIXED_N
            ):
                try:
                    validation = (
                        validate_fixed_n_result(
                            result,
                            method,
                            seed,
                        )
                    )

                    classification = (
                        "FINAL_FIXED_N_VALID"
                    )
                except Exception as exc:
                    result_parse_error = (
                        type(exc).__name__
                        + ": "
                        + str(exc)
                    )

                    classification = (
                        "INFRA_INVALID"
                    )

            elif status == TERMINAL:
                try:
                    validation = (
                        validate_terminal_result(
                            result,
                            seed,
                        )
                    )

                    classification = (
                        "VALID_DUT_FAILURE_TERMINAL"
                    )
                except Exception as exc:
                    result_parse_error = (
                        type(exc).__name__
                        + ": "
                        + str(exc)
                    )

                    classification = (
                        "INFRA_INVALID"
                    )

            else:
                classification = (
                    "INFRA_INVALID"
                )

        else:
            classification = (
                "INFRA_INVALID"
            )

        finished += 1

        record = {
            "schema": (
                "week15.final-campaign-"
                "run-result.v1"
            ),
            "index": index,
            "method": method,
            "seed": seed,
            "accepted_budget": BUDGET,
            "classification": classification,
            "make_returncode": rc,
            "validation": validation,
            "result_parse_error": (
                result_parse_error
            ),
            "paths": {
                "run_dir": str(
                    run_dir
                ),
                "build_dir": str(
                    build_dir
                ),
                "simulator_log": str(
                    log_path
                ),
                "results_xml": str(
                    xml_path
                ),
                "result_json": (
                    str(result_path)
                    if result_path
                    is not None
                    else None
                ),
            },
            "sha256": {
                "simulator_log": (
                    file_hash_or_none(
                        log_path
                    )
                ),
                "results_xml": (
                    file_hash_or_none(
                        xml_path
                    )
                ),
                "result_json": (
                    file_hash_or_none(
                        result_path
                    )
                    if result_path
                    is not None
                    else None
                ),
            },
            "final_seed_use": started,
        }

        records.append(
            record
        )

        atomic_json(
            state_root
            / (
                f"{index:02d}_"
                f"{method}_"
                f"{seed}.result.json"
            ),
            record,
        )

        if (
            classification
            == "FINAL_FIXED_N_VALID"
        ):
            campaign_status = "RUNNING"

        elif (
            classification
            == "VALID_DUT_FAILURE_TERMINAL"
        ):
            campaign_status = (
                "STOPPED_"
                "VALID_DUT_FAILURE_TERMINAL"
            )

        else:
            campaign_status = (
                "STOPPED_INFRA_INVALID"
            )

        atomic_json(
            out / "campaign_state.json",
            {
                "schema": (
                    "week15.final-campaign-"
                    "execution-state.v1"
                ),
                "authority_head": (
                    EXPECTED_HEAD
                ),
                "status": campaign_status,
                "runs_expected": 45,
                "runs_started": started,
                "runs_finished": finished,
                "final_seed_use": started,
                "records": records,
            },
        )

        print(
            "RUN_FINISHED "
            f"index={index} "
            f"method={method} "
            f"seed={seed} "
            f"classification={classification} "
            f"rc={rc}",
            flush=True,
        )

        if (
            classification
            == "VALID_DUT_FAILURE_TERMINAL"
        ):
            atomic_json(
                out
                / "campaign_summary.json",
                {
                    "schema": (
                        "week15.final-campaign-"
                        "summary.v1"
                    ),
                    "authority_head": (
                        EXPECTED_HEAD
                    ),
                    "status": (
                        "STOPPED_"
                        "VALID_DUT_FAILURE_TERMINAL"
                    ),
                    "runs_expected": 45,
                    "runs_started": started,
                    "runs_finished": finished,
                    "final_seed_use": started,
                    "records": records,
                },
            )

            return 20

        if (
            classification
            == "INFRA_INVALID"
        ):
            atomic_json(
                out
                / "campaign_summary.json",
                {
                    "schema": (
                        "week15.final-campaign-"
                        "summary.v1"
                    ),
                    "authority_head": (
                        EXPECTED_HEAD
                    ),
                    "status": (
                        "STOPPED_INFRA_INVALID"
                    ),
                    "runs_expected": 45,
                    "runs_started": started,
                    "runs_finished": finished,
                    "final_seed_use": started,
                    "records": records,
                },
            )

            return 30

    summary = {
        "schema": (
            "week15.final-campaign-summary.v1"
        ),
        "authority_head": EXPECTED_HEAD,
        "status": "COMPLETED_45_RUNS",
        "runs_expected": 45,
        "runs_started": started,
        "runs_finished": finished,
        "final_seed_use": started,
        "total_fixed_n_accepted": (
            45 * BUDGET
        ),
        "records": records,
    }

    atomic_json(
        out / "campaign_summary.json",
        summary,
    )

    atomic_json(
        out / "campaign_state.json",
        {
            "schema": (
                "week15.final-campaign-"
                "execution-state.v1"
            ),
            "authority_head": EXPECTED_HEAD,
            "status": "COMPLETED_45_RUNS",
            "runs_expected": 45,
            "runs_started": started,
            "runs_finished": finished,
            "final_seed_use": started,
            "records": records,
        },
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--plan",
        required=True,
        type=Path,
    )

    group = parser.add_mutually_exclusive_group(
        required=True
    )

    group.add_argument(
        "--preflight",
        action="store_true",
    )

    group.add_argument(
        "--execute",
        action="store_true",
    )

    args = parser.parse_args()

    plan = verify_plan(
        args.plan
    )

    if args.preflight:
        return preflight(plan)

    return execute(plan)


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )
    except Exception as exc:
        print(
            "FINAL_DRIVER_FATAL="
            + type(exc).__name__
            + ":"
            + str(exc),
            file=sys.stderr,
            flush=True,
        )

        raise
