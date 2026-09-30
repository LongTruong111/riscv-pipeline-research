from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)

FINAL_ROOT = (
    REPO_ROOT
    / "research/week15/final_campaign"
)

EXECUTION_CONTRACT_PATH = (
    FINAL_ROOT
    / "EXECUTION_CONTRACT.json"
)

IMPLEMENTATION_PLAN_PATH = (
    FINAL_ROOT
    / "IMPLEMENTATION_PLAN.json"
)

ADAPTIVE_CONTRACT_PATH = (
    REPO_ROOT
    / "research/week15/contracts/"
    "adaptive_cgs_freeze.yaml"
)

INFRA_CLOSURE_PATH = (
    FINAL_ROOT
    / "INFRA_QUALIFICATION_CLOSURE.json"
)


@dataclass(frozen=True)
class FinalRuntimeConfig:
    method: str
    phase: str

    root_seed: int
    accepted_budget: int
    repetition: str

    epsilon: float
    alpha: float
    q_floor: float
    nominal_batch: int
    checkpoint_interval: int

    result_dir: Path
    result_path: Path

    contract_sha256: str
    config_id: str

    gate_t15_head: str
    execution_contract_sha256: str
    implementation_plan_sha256: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def _load_hashed_json(
    path: Path,
) -> tuple[dict, str]:
    sidecar = Path(
        str(path) + ".sha256"
    )

    if not path.is_file():
        raise RuntimeError(
            f"missing authority: {path}"
        )

    if not sidecar.is_file():
        raise RuntimeError(
            f"missing SHA sidecar: {sidecar}"
        )

    tokens = sidecar.read_text(
        encoding="utf-8"
    ).split()

    if not tokens:
        raise RuntimeError(
            f"empty SHA sidecar: {sidecar}"
        )

    expected = tokens[0]
    actual = _sha256(path)

    if actual != expected:
        raise RuntimeError(
            f"SHA-256 mismatch for {path}: "
            f"{actual} != {expected}"
        )

    return (
        json.loads(
            path.read_text(
                encoding="utf-8"
            )
        ),
        actual,
    )


def _required(
    env: Mapping[str, str],
    name: str,
) -> str:
    value = env.get(name)

    if value is None or value == "":
        raise ValueError(
            f"required environment variable "
            f"{name} is missing"
        )

    return value


def _outside_repo(
    path: Path,
) -> None:
    if (
        path == REPO_ROOT
        or REPO_ROOT in path.parents
    ):
        raise ValueError(
            "final campaign result directory "
            "must be outside repository"
        )


def _verify_final_authorization(
    *,
    execution_contract_sha256: str,
    implementation_plan_sha256: str,
) -> None:
    closure, closure_sha = (
        _load_hashed_json(
            INFRA_CLOSURE_PATH
        )
    )

    if closure["status"] != "PASS":
        raise ValueError(
            "execution infrastructure "
            "qualification is not PASS"
        )

    if (
        closure[
            "execution_contract_sha256"
        ]
        != execution_contract_sha256
    ):
        raise ValueError(
            "infra closure execution-contract "
            "identity mismatch"
        )

    if (
        closure[
            "implementation_plan_sha256"
        ]
        != implementation_plan_sha256
    ):
        raise ValueError(
            "infra closure implementation-plan "
            "identity mismatch"
        )

    if (
        closure[
            "final_seed_use_before_closure"
        ]
        != 0
    ):
        raise ValueError(
            "invalid infra closure final-seed "
            "provenance"
        )

    if not closure_sha:
        raise AssertionError(
            "unreachable empty closure SHA"
        )


def load_final_runtime_config(
    method: str,
    env: Mapping[str, str] | None = None,
) -> FinalRuntimeConfig:
    if env is None:
        env = os.environ

    method = method.upper()

    if method not in {
        "M1",
        "M2",
        "M3",
    }:
        raise ValueError(
            f"unknown method: {method}"
        )

    execution, execution_sha = (
        _load_hashed_json(
            EXECUTION_CONTRACT_PATH
        )
    )

    implementation, implementation_sha = (
        _load_hashed_json(
            IMPLEMENTATION_PLAN_PATH
        )
    )

    adaptive, adaptive_sha = (
        _load_hashed_json(
            ADAPTIVE_CONTRACT_PATH
        )
    )

    root_seed = int(
        _required(
            env,
            "W15_FINAL_SEED",
        )
    )

    accepted_budget = int(
        _required(
            env,
            "W15_FINAL_BUDGET",
        )
    )

    phase = _required(
        env,
        "W15_FINAL_PHASE",
    ).strip().lower()

    if accepted_budget != 100000:
        raise ValueError(
            "final execution budget must be "
            "exactly 100000 accepted instructions"
        )

    matrix = {
        entry["method"]: entry
        for entry in execution[
            "infrastructure_qualification"
        ]["matrix"]
    }

    if phase == "qualification":
        entry = matrix[method]

        if root_seed != int(
            entry["seed"]
        ):
            raise ValueError(
                f"{method} qualification seed "
                f"must be {entry['seed']}, "
                f"got {root_seed}"
            )

        if accepted_budget != int(
            entry["accepted_budget"]
        ):
            raise ValueError(
                "qualification budget mismatch"
            )

        repetition = "Q"

    elif phase == "final":
        _verify_final_authorization(
            execution_contract_sha256=(
                execution_sha
            ),
            implementation_plan_sha256=(
                implementation_sha
            ),
        )

        seeds = execution[
            "final_campaign"
        ][
            f"{method}_seeds"
        ]

        if root_seed not in seeds:
            raise ValueError(
                f"{root_seed} is outside frozen "
                f"{method} final seed set"
            )

        repetition = "F"

    else:
        raise ValueError(
            "W15_FINAL_PHASE must be "
            "'qualification' or 'final'"
        )

    result_dir = Path(
        _required(
            env,
            "W15_FINAL_RESULT_DIR",
        )
    ).expanduser().resolve()

    _outside_repo(
        result_dir
    )

    freeze = adaptive["freeze"]

    epsilon = float(
        freeze["epsilon"]["value"]
    )

    alpha = float(
        freeze["alpha"]["value"]
    )

    q_floor = float(
        freeze["q_floor"]["value"]
    )

    nominal_batch = int(
        freeze["batch_semantics"]
        ["nominal_batch"]
    )

    checkpoint_interval = int(
        freeze["stopping_rule"]
        ["checkpoint_interval"]
    )

    if checkpoint_interval != 1000:
        raise RuntimeError(
            "frozen checkpoint interval changed"
        )

    config_id = (
        f"e{epsilon:.2f}_"
        f"a{alpha:.1f}_"
        f"b{nominal_batch}"
    )

    result_path = (
        result_dir
        / (
            f"{method.lower()}_"
            f"{phase}_"
            f"seed_{root_seed}_"
            f"n_{accepted_budget}.json"
        )
    )

    gate_t15_head = (
        execution[
            "base_gate"
        ]["commit"]
    )

    return FinalRuntimeConfig(
        method=method,
        phase=phase,
        root_seed=root_seed,
        accepted_budget=(
            accepted_budget
        ),
        repetition=repetition,
        epsilon=epsilon,
        alpha=alpha,
        q_floor=q_floor,
        nominal_batch=nominal_batch,
        checkpoint_interval=(
            checkpoint_interval
        ),
        result_dir=result_dir,
        result_path=result_path,
        contract_sha256=adaptive_sha,
        config_id=config_id,
        gate_t15_head=gate_t15_head,
        execution_contract_sha256=(
            execution_sha
        ),
        implementation_plan_sha256=(
            implementation_sha
        ),
    )


def load_runtime_config(
    env: Mapping[str, str] | None = None,
) -> FinalRuntimeConfig:
    """
    Compatibility binding for the source-derived
    M3 Adaptive harness.
    """
    return load_final_runtime_config(
        "M3",
        env,
    )
