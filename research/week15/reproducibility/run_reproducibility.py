from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)

CONTRACT = (
    REPO_ROOT
    / "research/week15/contracts/"
    "adaptive_cgs_freeze.yaml"
)

RTL_DIR = (
    REPO_ROOT
    / "research/week15/rtl"
)

MODULE = (
    "test_adaptive_reproducibility"
)

ELIGIBLE_FIXED_N_STATUSES = {
    "COMPLETED",
    "VALID_DUT_FAILURE_NONTERMINAL",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def load_contract() -> dict:
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8"
        )
    )


def git_text(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    return result.stdout.strip()


def qualification_plan(
    contract: dict | None = None,
) -> list[dict]:
    if contract is None:
        contract = load_contract()

    matrix = (
        contract["freeze"]
        ["reproducibility_rule"]
        ["qualification_matrix"]
    )

    plan = []

    for entry in matrix:
        for repetition in entry[
            "repetitions"
        ]:
            plan.append(
                {
                    "seed": int(
                        entry["seed"]
                    ),
                    "accepted_budget": int(
                        entry[
                            "accepted_budget"
                        ]
                    ),
                    "repetition": str(
                        repetition
                    ),
                }
            )

    return plan


def expected_result_filename(
    *,
    seed: int,
    accepted_budget: int,
    repetition: str,
    contract: dict | None = None,
) -> str:
    if contract is None:
        contract = load_contract()

    freeze = contract["freeze"]

    epsilon = float(
        freeze["epsilon"]["value"]
    )

    alpha = float(
        freeze["alpha"]["value"]
    )

    batch = int(
        freeze["batch_semantics"]
        ["nominal_batch"]
    )

    config_id = (
        f"e{epsilon:.2f}_"
        f"a{alpha:.1f}_"
        f"b{batch}"
    )

    return (
        f"adaptive_repro_{config_id}_"
        f"seed_{seed}_"
        f"n_{accepted_budget}_"
        f"rep_{repetition}.json"
    )


def validate_fixed_n_result(
    record: dict,
    *,
    seed: int,
    accepted_budget: int,
    repetition: str,
    expected_head: str,
    contract: dict,
) -> None:
    freeze = contract["freeze"]

    assert record["seed"] == seed

    assert (
        record["configuration"]
        ["accepted_budget"]
        == accepted_budget
    )

    assert (
        record["configuration"]["epsilon"]
        == freeze["epsilon"]["value"]
    )

    assert (
        record["configuration"]["alpha"]
        == freeze["alpha"]["value"]
    )

    assert (
        record["configuration"]["q_floor"]
        == freeze["q_floor"]["value"]
    )

    assert (
        record["configuration"]
        ["nominal_batch"]
        == freeze["batch_semantics"]
        ["nominal_batch"]
    )

    assert (
        record["configuration"]
        ["checkpoint_interval"]
        == freeze["stopping_rule"]
        ["checkpoint_interval"]
    )

    assert (
        record["provenance"]
        ["harness_revision"]
        == expected_head
    )

    if record["status"] not in (
        ELIGIBLE_FIXED_N_STATUSES
    ):
        raise AssertionError(
            "qualification run did not "
            "complete fixed-N campaign: "
            f"{record['status']}"
        )

    assert (
        record["fixed_budget_complete"]
        is True
    )

    assert (
        record["lifecycle"]["accepted"]
        == accepted_budget
    )

    repro = record[
        "reproducibility"
    ]

    assert (
        repro["repetition"]
        == repetition
    )

    assert (
        repro["contract_sha256"]
        == sha256(CONTRACT)
    )

    digests = repro[
        "trace_digests"
    ]

    counts = repro[
        "trace_record_counts"
    ]

    required = (
        freeze["trace_schema"]
        ["gate_required_traces"]
    )

    supplemental = (
        freeze["trace_schema"]
        ["supplemental_traces"]
    )

    for name in (
        list(required)
        + list(supplemental)
    ):
        digest = digests[name]

        assert len(digest) == 64
        int(digest, 16)

    assert (
        counts["instruction_stream"]
        == accepted_budget
    )

    checkpoint_interval = (
        freeze["stopping_rule"]
        ["checkpoint_interval"]
    )

    assert accepted_budget % (
        checkpoint_interval
    ) == 0

    assert (
        counts["coverage_trace"]
        == (
            accepted_budget
            // checkpoint_interval
        )
    )

    epoch_count = counts[
        "epoch_trace"
    ]

    assert (
        counts["arm_decision_trace"]
        == epoch_count
    )

    assert (
        counts["reward_trace"]
        == epoch_count
    )

    assert (
        counts["q_trace"]
        == epoch_count
    )

    selection_counts = repro[
        "selection_counts"
    ]

    assert set(selection_counts) == {
        "epsilon_exploration",
        "greedy_exploitation",
        "q_floor_uniform",
    }

    assert (
        sum(selection_counts.values())
        == epoch_count
    )


def compare_pair(
    a: dict,
    b: dict,
    *,
    contract: dict,
) -> dict:
    freeze = contract["freeze"]

    required = (
        freeze["trace_schema"]
        ["gate_required_traces"]
    )

    supplemental = (
        freeze["trace_schema"]
        ["supplemental_traces"]
    )

    a_hashes = (
        a["reproducibility"]
        ["trace_digests"]
    )

    b_hashes = (
        b["reproducibility"]
        ["trace_digests"]
    )

    required_equality = {
        name: (
            a_hashes[name]
            == b_hashes[name]
        )
        for name in required
    }

    supplemental_equality = {
        name: (
            a_hashes[name]
            == b_hashes[name]
        )
        for name in supplemental
    }

    return {
        "gate_required_equal": all(
            required_equality.values()
        ),
        "gate_required_trace_equality": (
            required_equality
        ),
        "supplemental_equal": all(
            supplemental_equality.values()
        ),
        "supplemental_trace_equality": (
            supplemental_equality
        ),
        "a_trace_digests": a_hashes,
        "b_trace_digests": b_hashes,
    }


def run_one(
    *,
    run: dict,
    run_dir: Path,
    sim_build: Path,
) -> Path:
    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    result_path = (
        run_dir
        / expected_result_filename(
            seed=run["seed"],
            accepted_budget=(
                run["accepted_budget"]
            ),
            repetition=run["repetition"],
        )
    )

    log_path = (
        run_dir
        / "simulator.log"
    )

    results_xml = (
        run_dir
        / "results.xml"
    )

    env = os.environ.copy()

    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "W15_REPRO_SEED": str(
                run["seed"]
            ),
            "W15_REPRO_BUDGET": str(
                run["accepted_budget"]
            ),
            "W15_REPRO_REPETITION": (
                run["repetition"]
            ),
            "W15_REPRO_RESULT_DIR": str(
                run_dir
            ),
            "COCOTB_RESULTS_FILE": str(
                results_xml
            ),
        }
    )

    command = [
        "make",
        "-C",
        str(RTL_DIR),
        "SIM=verilator",
        f"MODULE={MODULE}",
        f"SIM_BUILD={sim_build}",
    ]

    with log_path.open(
        "w",
        encoding="utf-8",
    ) as log:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

    if not result_path.is_file():
        raise RuntimeError(
            "qualification process produced "
            "no result artifact; "
            f"returncode={completed.returncode}, "
            f"log={log_path}"
        )

    if completed.returncode != 0:
        raise RuntimeError(
            "qualification simulator process "
            "failed; "
            f"returncode={completed.returncode}, "
            f"result={result_path}, "
            f"log={log_path}"
        )

    return result_path


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Actually run the frozen six-process "
            "qualification matrix. Without this flag "
            "only the preregistered plan is printed."
        ),
    )

    args = parser.parse_args()

    contract = load_contract()

    output_root = (
        args.output_root
        .expanduser()
        .resolve()
    )

    if (
        output_root == REPO_ROOT
        or REPO_ROOT in output_root.parents
    ):
        raise SystemExit(
            "output-root must be outside repository"
        )

    head = git_text(
        "rev-parse",
        "HEAD",
    )

    dirty = git_text(
        "status",
        "--porcelain",
    )

    plan = qualification_plan(
        contract
    )

    print(
        json.dumps(
            {
                "head": head,
                "contract_sha256": (
                    sha256(CONTRACT)
                ),
                "fresh_process_per_run": True,
                "git_dirty": bool(dirty),
                "plan": plan,
            },
            indent=2,
            sort_keys=True,
        )
    )

    if not args.execute:
        print(
            "NO_QUALIFICATION_EXECUTED"
        )
        return 0

    # Qualification evidence is admissible only from
    # the committed frozen harness. A dirty tree is
    # acceptable for plan inspection, never execution.
    if dirty:
        raise SystemExit(
            "qualification execution requires "
            "clean git tree"
        )

    campaign_root = (
        output_root
        / head
    )

    if campaign_root.exists():
        raise SystemExit(
            "refusing selective rerun or overwrite: "
            f"{campaign_root} already exists"
        )

    campaign_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    sim_build = (
        campaign_root
        / "sim_build"
    )

    records = {}

    for run in plan:
        key = (
            run["seed"],
            run["repetition"],
        )

        run_dir = (
            campaign_root
            / (
                f"seed_{run['seed']}_"
                f"n_{run['accepted_budget']}_"
                f"rep_{run['repetition']}"
            )
        )

        result_path = run_one(
            run=run,
            run_dir=run_dir,
            sim_build=sim_build,
        )

        record = json.loads(
            result_path.read_text(
                encoding="utf-8"
            )
        )

        validate_fixed_n_result(
            record,
            seed=run["seed"],
            accepted_budget=(
                run["accepted_budget"]
            ),
            repetition=(
                run["repetition"]
            ),
            expected_head=head,
            contract=contract,
        )

        records[key] = {
            "record": record,
            "result_path": str(
                result_path
            ),
            "result_sha256": sha256(
                result_path
            ),
        }

    pair_results = []

    matrix = (
        contract["freeze"]
        ["reproducibility_rule"]
        ["qualification_matrix"]
    )

    for entry in matrix:
        seed = int(entry["seed"])

        a = records[
            (seed, "A")
        ]["record"]

        b = records[
            (seed, "B")
        ]["record"]

        comparison = compare_pair(
            a,
            b,
            contract=contract,
        )

        pair_results.append(
            {
                "seed": seed,
                "accepted_budget": int(
                    entry[
                        "accepted_budget"
                    ]
                ),
                **comparison,
            }
        )

    gate_pass = all(
        item["gate_required_equal"]
        for item in pair_results
    )

    summary = {
        "schema": (
            "week15.adaptive-repro-"
            "qualification.v1"
        ),
        "head": head,
        "contract_sha256": (
            sha256(CONTRACT)
        ),
        "total_runs": len(plan),
        "total_accepted_budget": sum(
            item["accepted_budget"]
            for item in plan
        ),
        "fresh_process_per_run": True,
        "performance_used_for_gate": False,
        "coverage_level_used_for_gate": False,
        "individual_results": [
            {
                "seed": seed,
                "repetition": repetition,
                "result_path": data[
                    "result_path"
                ],
                "result_sha256": data[
                    "result_sha256"
                ],
            }
            for (
                seed,
                repetition,
            ), data in sorted(
                records.items()
            )
        ],
        "pairs": pair_results,
        "status": (
            "PASS"
            if gate_pass
            else "REPRODUCIBILITY_FAIL"
        ),
    }

    summary_path = (
        campaign_root
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
        f"SUMMARY={summary_path}"
    )

    print(
        f"STATUS={summary['status']}"
    )

    if not gate_pass:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
