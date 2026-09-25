from __future__ import annotations

import builtins

import pytest

from research.week13.pure_random.campaign_seed import (
    FAMILY_SUBSYSTEM,
    OPERAND_SUBSYSTEM,
    build_campaign_rngs,
    derive_campaign_seeds,
    derive_subsystem_seed,
)


PILOT_ROOT_1 = 11001
PILOT_ROOT_2 = 11002
PILOT_ROOT_3 = 11003


# Frozen known-answer vectors independently derived from:
#
#   SHA256(
#       "week13.m1-pr.v1|<root>|<subsystem>"
#   )[:8]
#
# interpreted as unsigned big-endian integers.
EXPECTED_VECTORS = {
    11001: (
        12131135992333324812,
        4984692458708750469,
    ),
    11002: (
        13268515483109392200,
        5507540597328377590,
    ),
    11003: (
        11180930624090561245,
        1123661732314749461,
    ),
}


@pytest.mark.parametrize(
    "root_seed",
    (
        PILOT_ROOT_1,
        PILOT_ROOT_2,
        PILOT_ROOT_3,
    ),
)
def test_pilot_seed_derivation_exact_vectors(
    root_seed: int,
):
    expected_family, expected_operand = (
        EXPECTED_VECTORS[root_seed]
    )

    seeds = derive_campaign_seeds(
        root_seed
    )

    assert seeds.root_seed == root_seed
    assert (
        seeds.family_seed
        == expected_family
    )
    assert (
        seeds.operand_seed
        == expected_operand
    )


def test_seed_derivation_is_deterministic():
    first = derive_campaign_seeds(
        PILOT_ROOT_1
    )

    second = derive_campaign_seeds(
        PILOT_ROOT_1
    )

    assert first == second


def test_subsystem_seeds_are_distinct():
    seeds = derive_campaign_seeds(
        PILOT_ROOT_1
    )

    assert (
        seeds.family_seed
        != seeds.operand_seed
    )


def test_different_root_seed_changes_stream_seeds():
    first = derive_campaign_seeds(
        PILOT_ROOT_1
    )

    second = derive_campaign_seeds(
        PILOT_ROOT_2
    )

    assert (
        first.family_seed
        != second.family_seed
    )

    assert (
        first.operand_seed
        != second.operand_seed
    )


def test_unsupported_subsystem_is_rejected():
    with pytest.raises(
        ValueError,
        match="subsystem must be one of",
    ):
        derive_subsystem_seed(
            PILOT_ROOT_1,
            "unsupported",
        )

    with pytest.raises(
        ValueError,
        match="subsystem must be one of",
    ):
        derive_subsystem_seed(
            PILOT_ROOT_1,
            123,  # type: ignore[arg-type]
        )


def test_invalid_root_seed_types_are_rejected():
    invalid_values = (
        True,
        False,
        11001.0,
        "11001",
        None,
    )

    for invalid in invalid_values:
        with pytest.raises(
            ValueError,
            match="root_seed must be an integer",
        ):
            derive_campaign_seeds(
                invalid  # type: ignore[arg-type]
            )


def test_derivation_does_not_use_python_hash(
    monkeypatch,
):
    def forbidden_hash(_value):
        raise AssertionError(
            "Python hash() must not participate "
            "in M1-PR seed derivation"
        )

    monkeypatch.setattr(
        builtins,
        "hash",
        forbidden_hash,
    )

    seeds = derive_campaign_seeds(
        PILOT_ROOT_1
    )

    expected_family, expected_operand = (
        EXPECTED_VECTORS[PILOT_ROOT_1]
    )

    assert (
        seeds.family_seed
        == expected_family
    )

    assert (
        seeds.operand_seed
        == expected_operand
    )


def test_rng_objects_are_independent_and_reproducible():
    baseline = build_campaign_rngs(
        PILOT_ROOT_1
    )

    perturbed = build_campaign_rngs(
        PILOT_ROOT_1
    )

    assert (
        baseline.family_rng
        is not baseline.operand_rng
    )

    baseline_operand = [
        baseline.operand_rng.getrandbits(
            64
        )
        for _ in range(8)
    ]

    # Deliberately consume only the family stream.
    for _ in range(100):
        perturbed.family_rng.random()

    perturbed_operand = [
        perturbed.operand_rng.getrandbits(
            64
        )
        for _ in range(8)
    ]

    assert (
        perturbed_operand
        == baseline_operand
    )

    # Fresh construction with the same root must reproduce
    # the family stream from its initial state.
    first = build_campaign_rngs(
        PILOT_ROOT_1
    )

    second = build_campaign_rngs(
        PILOT_ROOT_1
    )

    first_family = [
        first.family_rng.getrandbits(
            64
        )
        for _ in range(8)
    ]

    second_family = [
        second.family_rng.getrandbits(
            64
        )
        for _ in range(8)
    ]

    assert (
        first_family
        == second_family
    )


def test_direct_subsystem_api_matches_campaign_bundle():
    seeds = derive_campaign_seeds(
        PILOT_ROOT_1
    )

    assert (
        derive_subsystem_seed(
            PILOT_ROOT_1,
            FAMILY_SUBSYSTEM,
        )
        == seeds.family_seed
    )

    assert (
        derive_subsystem_seed(
            PILOT_ROOT_1,
            OPERAND_SUBSYSTEM,
        )
        == seeds.operand_seed
    )
