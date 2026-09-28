from __future__ import annotations

from dataclasses import dataclass
from itertools import product


PILOT_SEEDS = (
    13001,
    13002,
    13003,
)

EPSILON_CANDIDATES = (
    0.05,
    0.10,
    0.20,
)

ALPHA_CANDIDATES = (
    0.1,
    0.3,
    0.5,
)

BATCH_CANDIDATES = (
    500,
    1000,
    2000,
)

Q_FLOOR = 0.05

ACCEPTED_BUDGET = 10_000
CHECKPOINT_INTERVAL = 1_000

L2_BIN_COUNT = 62


@dataclass(
    frozen=True,
    slots=True,
)
class AdaptivePilotConfig:
    epsilon: float
    alpha: float
    nominal_batch: int


@dataclass(
    frozen=True,
    slots=True,
)
class AdaptivePilotRun:
    config: AdaptivePilotConfig
    seed: int


def hyperparameter_configs(
) -> tuple[AdaptivePilotConfig, ...]:
    """
    Frozen Week-13 FULL_GRID order:

        epsilon -> alpha -> batch

    Count:
        3 * 3 * 3 = 27.
    """
    return tuple(
        AdaptivePilotConfig(
            epsilon=epsilon,
            alpha=alpha,
            nominal_batch=batch,
        )
        for epsilon, alpha, batch
        in product(
            EPSILON_CANDIDATES,
            ALPHA_CANDIDATES,
            BATCH_CANDIDATES,
        )
    )


def pilot_runs(
) -> tuple[AdaptivePilotRun, ...]:
    """
    Three frozen independent pilot seeds per configuration.

    Count:
        27 * 3 = 81.
    """
    return tuple(
        AdaptivePilotRun(
            config=config,
            seed=seed,
        )
        for config in hyperparameter_configs()
        for seed in PILOT_SEEDS
    )
