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

CONTRACT_PATH = (
    REPO_ROOT
    / "research/week15/contracts/"
    "adaptive_cgs_freeze.yaml"
)

CONTRACT_HASH_PATH = Path(
    str(CONTRACT_PATH) + ".sha256"
)


@dataclass(frozen=True)
class QualificationRuntimeConfig:
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def _load_contract() -> tuple[dict, str]:
    expected = (
        CONTRACT_HASH_PATH
        .read_text(encoding="utf-8")
        .split()[0]
    )

    actual = _sha256(CONTRACT_PATH)

    if actual != expected:
        raise RuntimeError(
            "Week15 Adaptive-CGS contract "
            "SHA-256 mismatch"
        )

    contract = json.loads(
        CONTRACT_PATH.read_text(
            encoding="utf-8"
        )
    )

    return contract, actual


def _required_environment(
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


def qualification_matrix() -> tuple[
    tuple[int, int, str],
    ...
]:
    contract, _ = _load_contract()

    entries = (
        contract["freeze"]
        ["reproducibility_rule"]
        ["qualification_matrix"]
    )

    flattened = []

    for entry in entries:
        seed = int(entry["seed"])
        budget = int(
            entry["accepted_budget"]
        )

        for repetition in entry["repetitions"]:
            flattened.append(
                (
                    seed,
                    budget,
                    str(repetition),
                )
            )

    return tuple(flattened)


def load_runtime_config(
    env: Mapping[str, str] | None = None,
) -> QualificationRuntimeConfig:
    if env is None:
        env = os.environ

    contract, contract_sha = (
        _load_contract()
    )

    freeze = contract["freeze"]

    root_seed = int(
        _required_environment(
            env,
            "W15_REPRO_SEED",
        )
    )

    accepted_budget = int(
        _required_environment(
            env,
            "W15_REPRO_BUDGET",
        )
    )

    repetition = (
        _required_environment(
            env,
            "W15_REPRO_REPETITION",
        )
    )

    qualification_key = (
        root_seed,
        accepted_budget,
        repetition,
    )

    allowed = set(
        qualification_matrix()
    )

    if qualification_key not in allowed:
        raise ValueError(
            "run is outside frozen Week15 "
            "qualification matrix: "
            f"{qualification_key}"
        )

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

    result_dir = Path(
        _required_environment(
            env,
            "W15_REPRO_RESULT_DIR",
        )
    ).expanduser().resolve()

    if (
        result_dir == REPO_ROOT
        or REPO_ROOT in result_dir.parents
    ):
        raise ValueError(
            "W15_REPRO_RESULT_DIR must be "
            "outside repository"
        )

    config_id = (
        f"e{epsilon:.2f}_"
        f"a{alpha:.1f}_"
        f"b{nominal_batch}"
    )

    result_path = (
        result_dir
        / (
            f"adaptive_repro_{config_id}_"
            f"seed_{root_seed}_"
            f"n_{accepted_budget}_"
            f"rep_{repetition}.json"
        )
    )

    return QualificationRuntimeConfig(
        root_seed=root_seed,
        accepted_budget=accepted_budget,
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
        contract_sha256=contract_sha,
        config_id=config_id,
    )
