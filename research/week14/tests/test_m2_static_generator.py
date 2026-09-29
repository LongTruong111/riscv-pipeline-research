from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import pytest

from research.week10.adaptive.template_library import (
    ArmID,
)
from research.week14.weighted_random.static_generator import (
    ARM_TICKETS,
    POSITIVE_REGISTERS,
    StaticUniformTargetSampler,
    derive_rng_seed,
    generate_weighted_random_plan,
)


ROOT = Path(__file__).resolve().parents[3]

SOURCE = (
    ROOT
    / "research/week14/weighted_random/"
    "static_generator.py"
)


def test_frozen_ticket_table_is_exact():
    assert ARM_TICKETS == (
        ArmID.A0,
        ArmID.A0,
        ArmID.A1,
        ArmID.A1,
        ArmID.A2,
        ArmID.A2,
        ArmID.A3,
        ArmID.A3,
        ArmID.A4,
        ArmID.A5,
        ArmID.A5,
        ArmID.A6,
        ArmID.A6,
        ArmID.A7,
        ArmID.A8,
        ArmID.A9,
    )

    assert Counter(ARM_TICKETS) == {
        ArmID.A0: 2,
        ArmID.A1: 2,
        ArmID.A2: 2,
        ArmID.A3: 2,
        ArmID.A4: 1,
        ArmID.A5: 2,
        ArmID.A6: 2,
        ArmID.A7: 1,
        ArmID.A8: 1,
        ArmID.A9: 1,
    }

    assert len(ARM_TICKETS) == 16


def test_rng_domains_are_deterministic_and_separate():
    seed = 14001

    values_a = {
        domain: derive_rng_seed(
            seed,
            domain,
        )
        for domain in (
            "arm",
            "target",
            "realization",
        )
    }

    values_b = {
        domain: derive_rng_seed(
            seed,
            domain,
        )
        for domain in (
            "arm",
            "target",
            "realization",
        )
    }

    assert values_a == values_b

    assert len(
        set(values_a.values())
    ) == 3


def test_static_target_domain_and_a4_distinct():
    from random import Random

    sampler = StaticUniformTargetSampler(
        Random(123456)
    )

    for arm in ArmID:
        for _ in range(100):
            target = sampler.sample(arm)

            if target.d1 is not None:
                assert (
                    target.d1
                    in POSITIVE_REGISTERS
                )

            if target.d2 is not None:
                assert (
                    target.d2
                    in POSITIVE_REGISTERS
                )

            if arm is ArmID.A4:
                assert target.d1 is not None
                assert target.d2 is not None
                assert (
                    target.d1
                    != target.d2
                )


def test_plan_is_exact_cut_and_deterministic():
    a = generate_weighted_random_plan(
        14001,
        1000,
    )

    b = generate_weighted_random_plan(
        14001,
        1000,
    )

    assert (
        a.accepted_instruction_count
        == 1000
    )

    assert (
        b.accepted_instruction_count
        == 1000
    )

    assert a.plan_hash == b.plan_hash

    assert a.hash_payload() == (
        b.hash_payload()
    )

    assert not any(
        block.is_partial
        for block in a.blocks[:-1]
    )


def test_all_planned_a4_targets_are_distinct():
    plan = generate_weighted_random_plan(
        14001,
        1000,
    )

    a4_count = 0

    for block in plan.blocks:
        if block.arm_id is not ArmID.A4:
            continue

        a4_count += 1

        assert (
            block.target.d1
            != block.target.d2
        )

    assert a4_count > 0


def test_source_has_no_adaptive_feedback_import():
    tree = ast.parse(
        SOURCE.read_text(
            encoding="utf-8"
        )
    )

    forbidden_modules = (
        "coverage_collector",
        "decision_engine",
        "epoch_coordinator",
        "l2_live_coordinator",
    )

    forbidden_imported_names = {
        "RegisterTargetPolicy",
        "L2IntentCoverageState",
        "BanditDecisionEngine",
        "AdaptiveEpochCoordinator",
    }

    for node in ast.walk(tree):
        if isinstance(
            node,
            ast.ImportFrom,
        ):
            module = node.module or ""

            assert not any(
                token in module
                for token
                in forbidden_modules
            )

            for alias in node.names:
                assert (
                    alias.name
                    not in forbidden_imported_names
                )


def test_generator_api_exposes_no_feedback_argument():
    import inspect

    from research.week14.weighted_random.static_generator import (
        generate_weighted_random_plan,
    )

    parameters = set(
        inspect.signature(
            generate_weighted_random_plan
        ).parameters
    )

    assert parameters == {
        "root_seed",
        "accepted_instruction_budget",
    }


def test_semantic_no_feedback_guards(
    monkeypatch,
):
    """
    If M2 accidentally starts using Adaptive targeting or
    bandit selection, these guards make plan generation fail.
    """
    from research.week10.adaptive import (
        decision_engine,
        register_policy,
    )

    baseline = generate_weighted_random_plan(
        14001,
        1000,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "adaptive feedback path was touched"
        )

    monkeypatch.setattr(
        register_policy.RegisterTargetPolicy,
        "select",
        forbidden,
    )

    monkeypatch.setattr(
        register_policy.L2IntentCoverageState,
        "uncovered",
        forbidden,
    )

    monkeypatch.setattr(
        decision_engine.BanditDecisionEngine,
        "select_arm",
        forbidden,
    )

    guarded = generate_weighted_random_plan(
        14001,
        1000,
    )

    assert (
        guarded.plan_hash
        == baseline.plan_hash
    )


def test_invalid_budget_fails_fast():
    with pytest.raises(ValueError):
        generate_weighted_random_plan(
            14001,
            0,
        )
