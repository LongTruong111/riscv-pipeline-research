from __future__ import annotations

from dataclasses import dataclass
import hashlib
from random import Random


SEED_DOMAIN = "week10-adaptive-cgs-v1"

DECISION_SUBSYSTEM = "decision"
TARGET_SUBSYSTEM = "target"
REALIZATION_SUBSYSTEM = "realization"

SUPPORTED_SUBSYSTEMS = (
    DECISION_SUBSYSTEM,
    TARGET_SUBSYSTEM,
    REALIZATION_SUBSYSTEM,
)


@dataclass(frozen=True)
class CampaignSeeds:
    """
    Deterministically derived Adaptive-CGS subsystem seeds.

    One authoritative experimental root seed is domain-separated into
    independent stochastic subsystem seeds.
    """

    root_seed: int
    decision_seed: int
    target_seed: int
    realization_seed: int


@dataclass(frozen=True)
class CampaignRngs:
    """
    Independent mutable RNG objects owned by one Adaptive-CGS run.

    The dataclass is frozen so RNG ownership cannot be reassigned after
    construction.  Each Random instance itself remains intentionally
    mutable as stochastic draws are consumed during campaign execution.
    """

    seeds: CampaignSeeds
    decision_rng: Random
    target_rng: Random
    realization_rng: Random


def _validate_root_seed(
    root_seed: int,
) -> None:
    """
    Validate the authoritative experimental seed.

    Negative integers are not forbidden by the frozen amendment, so this
    function deliberately validates type only rather than inventing a
    new numerical restriction.
    """
    if (
        isinstance(root_seed, bool)
        or not isinstance(root_seed, int)
    ):
        raise ValueError(
            "root_seed must be an integer"
        )


def _validate_subsystem(
    subsystem: str,
) -> None:
    if (
        not isinstance(subsystem, str)
        or subsystem not in SUPPORTED_SUBSYSTEMS
    ):
        raise ValueError(
            "subsystem must be one of: "
            + ", ".join(
                SUPPORTED_SUBSYSTEMS
            )
        )


def derive_subsystem_seed(
    root_seed: int,
    subsystem: str,
) -> int:
    """
    Derive one deterministic 64-bit subsystem seed.

    Frozen derivation:

        message =
            "week10-adaptive-cgs-v1|"
            + decimal(root_seed)
            + "|"
            + subsystem

        digest = SHA256(UTF8(message))

        seed =
            unsigned big-endian integer represented by digest[0:8]

    Python hash() is deliberately not involved.

    Complexity:
        O(1) time and O(1) memory with respect to campaign length N.
    """
    _validate_root_seed(
        root_seed
    )

    _validate_subsystem(
        subsystem
    )

    message = (
        f"{SEED_DOMAIN}|"
        f"{root_seed}|"
        f"{subsystem}"
    )

    digest = hashlib.sha256(
        message.encode(
            "utf-8"
        )
    ).digest()

    return int.from_bytes(
        digest[:8],
        byteorder="big",
        signed=False,
    )


def derive_campaign_seeds(
    root_seed: int,
) -> CampaignSeeds:
    """
    Derive all three frozen Adaptive-CGS stochastic subsystem seeds.
    """
    _validate_root_seed(
        root_seed
    )

    return CampaignSeeds(
        root_seed=root_seed,
        decision_seed=(
            derive_subsystem_seed(
                root_seed,
                DECISION_SUBSYSTEM,
            )
        ),
        target_seed=(
            derive_subsystem_seed(
                root_seed,
                TARGET_SUBSYSTEM,
            )
        ),
        realization_seed=(
            derive_subsystem_seed(
                root_seed,
                REALIZATION_SUBSYSTEM,
            )
        ),
    )


def build_campaign_rngs(
    root_seed: int,
) -> CampaignRngs:
    """
    Construct exactly one independent Random object per stochastic
    Adaptive-CGS subsystem.

    No mutable RNG object is shared between decision, target, and
    realization ownership domains.
    """
    seeds = derive_campaign_seeds(
        root_seed
    )

    decision_rng = Random(
        seeds.decision_seed
    )

    target_rng = Random(
        seeds.target_seed
    )

    realization_rng = Random(
        seeds.realization_seed
    )

    if (
        decision_rng is target_rng
        or decision_rng is realization_rng
        or target_rng is realization_rng
    ):
        raise AssertionError(
            "Adaptive-CGS RNG objects must be independent"
        )

    return CampaignRngs(
        seeds=seeds,
        decision_rng=decision_rng,
        target_rng=target_rng,
        realization_rng=realization_rng,
    )
