from __future__ import annotations

import builtins

import pytest

from research.week10.adaptive.campaign_seed import (
    DECISION_SUBSYSTEM,
    REALIZATION_SUBSYSTEM,
    TARGET_SUBSYSTEM,
    build_campaign_rngs,
    derive_campaign_seeds,
    derive_subsystem_seed,
)


GATE_ROOT_SEED = 20260921

GATE_DECISION_SEED = (
    16680843080276206783
)

GATE_TARGET_SEED = (
    1163466188706097826
)

GATE_REALIZATION_SEED = (
    7717841318315519387
)


def test_gate_t10_seed_derivation_exact_vector():
    """
    Frozen amendment test vector.

    This test uses exact externally frozen constants rather than
    computing the expected value with the implementation under test.
    """
    seeds = derive_campaign_seeds(
        GATE_ROOT_SEED
    )

    assert (
        seeds.root_seed
        == GATE_ROOT_SEED
    )

    assert (
        seeds.decision_seed
        == GATE_DECISION_SEED
    )

    assert (
        seeds.target_seed
        == GATE_TARGET_SEED
    )

    assert (
        seeds.realization_seed
        == GATE_REALIZATION_SEED
    )


def test_seed_derivation_is_deterministic():
    first = derive_campaign_seeds(
        GATE_ROOT_SEED
    )

    second = derive_campaign_seeds(
        GATE_ROOT_SEED
    )

    assert first == second


def test_subsystem_seeds_are_distinct():
    seeds = derive_campaign_seeds(
        GATE_ROOT_SEED
    )

    derived = {
        seeds.decision_seed,
        seeds.target_seed,
        seeds.realization_seed,
    }

    assert len(derived) == 3


def test_different_root_seed_changes_all_stream_seeds():
    first = derive_campaign_seeds(
        GATE_ROOT_SEED
    )

    second = derive_campaign_seeds(
        GATE_ROOT_SEED + 1
    )

    assert (
        first.decision_seed
        != second.decision_seed
    )

    assert (
        first.target_seed
        != second.target_seed
    )

    assert (
        first.realization_seed
        != second.realization_seed
    )


def test_unsupported_subsystem_is_rejected():
    with pytest.raises(
        ValueError,
        match="subsystem must be one of",
    ):
        derive_subsystem_seed(
            GATE_ROOT_SEED,
            "unsupported",
        )

    with pytest.raises(
        ValueError,
        match="subsystem must be one of",
    ):
        derive_subsystem_seed(
            GATE_ROOT_SEED,
            123,  # type: ignore[arg-type]
        )


def test_invalid_root_seed_types_are_rejected():
    invalid_values = (
        True,
        False,
        20260921.0,
        "20260921",
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
    """
    builtins.hash() is deliberately disabled.

    Seed derivation must still reproduce the frozen exact test vector.
    """

    def forbidden_hash(_value):
        raise AssertionError(
            "Python hash() must not participate "
            "in campaign seed derivation"
        )

    monkeypatch.setattr(
        builtins,
        "hash",
        forbidden_hash,
    )

    seeds = derive_campaign_seeds(
        GATE_ROOT_SEED
    )

    assert (
        seeds.decision_seed
        == GATE_DECISION_SEED
    )

    assert (
        seeds.target_seed
        == GATE_TARGET_SEED
    )

    assert (
        seeds.realization_seed
        == GATE_REALIZATION_SEED
    )


def test_rng_objects_are_independent_and_reproducible():
    """
    Extra draws from decision_rng must not perturb target_rng or
    realization_rng.

    A fresh construction from the same root seed must reproduce each
    subsystem stream exactly.
    """
    baseline = build_campaign_rngs(
        GATE_ROOT_SEED
    )

    perturbed = build_campaign_rngs(
        GATE_ROOT_SEED
    )

    assert (
        baseline.decision_rng
        is not baseline.target_rng
    )

    assert (
        baseline.decision_rng
        is not baseline.realization_rng
    )

    assert (
        baseline.target_rng
        is not baseline.realization_rng
    )

    baseline_target = [
        baseline.target_rng.getrandbits(
            64
        )
        for _ in range(8)
    ]

    baseline_realization = [
        baseline.realization_rng.getrandbits(
            64
        )
        for _ in range(8)
    ]

    # Deliberately perturb only the decision stream.
    for _ in range(100):
        perturbed.decision_rng.random()

    perturbed_target = [
        perturbed.target_rng.getrandbits(
            64
        )
        for _ in range(8)
    ]

    perturbed_realization = [
        perturbed.realization_rng.getrandbits(
            64
        )
        for _ in range(8)
    ]

    assert (
        perturbed_target
        == baseline_target
    )

    assert (
        perturbed_realization
        == baseline_realization
    )

    # Rebuilding from the same root seed also reproduces the decision
    # stream from its initial state.
    first = build_campaign_rngs(
        GATE_ROOT_SEED
    )

    second = build_campaign_rngs(
        GATE_ROOT_SEED
    )

    first_decision = [
        first.decision_rng.getrandbits(
            64
        )
        for _ in range(8)
    ]

    second_decision = [
        second.decision_rng.getrandbits(
            64
        )
        for _ in range(8)
    ]

    assert (
        first_decision
        == second_decision
    )


def test_direct_subsystem_api_matches_campaign_bundle():
    seeds = derive_campaign_seeds(
        GATE_ROOT_SEED
    )

    assert (
        derive_subsystem_seed(
            GATE_ROOT_SEED,
            DECISION_SUBSYSTEM,
        )
        == seeds.decision_seed
    )

    assert (
        derive_subsystem_seed(
            GATE_ROOT_SEED,
            TARGET_SUBSYSTEM,
        )
        == seeds.target_seed
    )

    assert (
        derive_subsystem_seed(
            GATE_ROOT_SEED,
            REALIZATION_SUBSYSTEM,
        )
        == seeds.realization_seed
    )
