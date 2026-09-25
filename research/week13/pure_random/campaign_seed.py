from __future__ import annotations

from dataclasses import dataclass
import hashlib
from random import Random


SEED_DOMAIN = "week13.m1-pr.v1"

FAMILY_SUBSYSTEM = "family"
OPERAND_SUBSYSTEM = "operand"

SUPPORTED_SUBSYSTEMS = (
    FAMILY_SUBSYSTEM,
    OPERAND_SUBSYSTEM,
)


@dataclass(frozen=True)
class PureRandomSeeds:
    """
    Deterministically derived M1-PR subsystem seeds.

    One experimental root seed is domain-separated into independent
    family-selection and operand-selection stochastic streams.
    """

    root_seed: int
    family_seed: int
    operand_seed: int


@dataclass(frozen=True)
class PureRandomRngs:
    """
    Independent mutable RNG objects owned by one M1-PR run.

    The dataclass is frozen so ownership cannot be reassigned.
    The Random instances themselves remain mutable as draws are
    consumed during generation.
    """

    seeds: PureRandomSeeds
    family_rng: Random
    operand_rng: Random


def _validate_root_seed(
    root_seed: int,
) -> None:
    """
    Validate the authoritative experimental root seed.

    Negative integer seeds are not forbidden by the frozen Week-13
    addendum, so validation deliberately constrains type only.
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
    Derive one deterministic 64-bit M1-PR subsystem seed.

    Frozen Week-13 derivation:

        message =
            "week13.m1-pr.v1|"
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
        message.encode("utf-8")
    ).digest()

    return int.from_bytes(
        digest[:8],
        byteorder="big",
        signed=False,
    )


def derive_campaign_seeds(
    root_seed: int,
) -> PureRandomSeeds:
    """
    Derive both frozen M1-PR stochastic subsystem seeds.
    """
    _validate_root_seed(
        root_seed
    )

    return PureRandomSeeds(
        root_seed=root_seed,
        family_seed=derive_subsystem_seed(
            root_seed,
            FAMILY_SUBSYSTEM,
        ),
        operand_seed=derive_subsystem_seed(
            root_seed,
            OPERAND_SUBSYSTEM,
        ),
    )


def build_campaign_rngs(
    root_seed: int,
) -> PureRandomRngs:
    """
    Construct exactly one independent Random object per M1-PR
    stochastic ownership domain.
    """
    seeds = derive_campaign_seeds(
        root_seed
    )

    family_rng = Random(
        seeds.family_seed
    )

    operand_rng = Random(
        seeds.operand_seed
    )

    if family_rng is operand_rng:
        raise AssertionError(
            "M1-PR RNG objects must be independent"
        )

    return PureRandomRngs(
        seeds=seeds,
        family_rng=family_rng,
        operand_rng=operand_rng,
    )
