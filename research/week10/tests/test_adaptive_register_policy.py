from random import Random

import pytest

from research.week10.adaptive.register_policy import (
    L2IntentCoverageState,
    POSITIVE_REGISTERS,
    RegisterTargetPolicy,
    TargetSelection,
)
from research.week10.adaptive.template_library import (
    ArmID,
    Distance,
)


ALL_REGISTERS = frozenset(POSITIVE_REGISTERS)


def test_positive_register_domain_is_exactly_x1_to_x31():
    assert POSITIVE_REGISTERS == tuple(range(1, 32))
    assert 0 not in POSITIVE_REGISTERS


def test_coverage_state_rejects_x0():
    with pytest.raises(ValueError):
        L2IntentCoverageState(
            d1_covered=frozenset({0})
        )


def test_coverage_state_rejects_register_above_x31():
    with pytest.raises(ValueError):
        L2IntentCoverageState(
            d2_covered=frozenset({32})
        )


def test_uncovered_is_returned_in_canonical_order():
    state = L2IntentCoverageState(
        d1_covered=frozenset({1, 3, 5})
    )

    uncovered = state.uncovered(Distance.D1)

    assert uncovered == tuple(
        register
        for register in range(1, 32)
        if register not in {1, 3, 5}
    )


def test_single_d1_arm_targets_only_uncovered_register():
    state = L2IntentCoverageState(
        d1_covered=frozenset(
            register
            for register in POSITIVE_REGISTERS
            if register != 17
        )
    )

    policy = RegisterTargetPolicy(Random(1234))

    target = policy.select(ArmID.A0, state)

    assert target == TargetSelection(d1=17)


def test_single_d2_arm_targets_only_uncovered_register():
    state = L2IntentCoverageState(
        d2_covered=frozenset(
            register
            for register in POSITIVE_REGISTERS
            if register != 23
        )
    )

    policy = RegisterTargetPolicy(Random(1234))

    target = policy.select(ArmID.A1, state)

    assert target == TargetSelection(d2=23)


@pytest.mark.parametrize(
    "arm_id",
    [
        ArmID.A0,
        ArmID.A2,
        ArmID.A5,
        ArmID.A7,
        ArmID.A8,
        ArmID.A9,
    ],
)
def test_all_d1_arms_use_d1_targeting(arm_id):
    state = L2IntentCoverageState(
        d1_covered=frozenset(
            register
            for register in POSITIVE_REGISTERS
            if register != 11
        )
    )

    target = RegisterTargetPolicy(
        Random(10)
    ).select(
        arm_id,
        state,
    )

    assert target.d1 == 11
    assert target.d2 is None


@pytest.mark.parametrize(
    "arm_id",
    [
        ArmID.A1,
        ArmID.A3,
        ArmID.A6,
    ],
)
def test_all_d2_arms_use_d2_targeting(arm_id):
    state = L2IntentCoverageState(
        d2_covered=frozenset(
            register
            for register in POSITIVE_REGISTERS
            if register != 19
        )
    )

    target = RegisterTargetPolicy(
        Random(10)
    ).select(
        arm_id,
        state,
    )

    assert target.d1 is None
    assert target.d2 == 19


def test_saturated_single_distance_falls_back_to_all_registers():
    state = L2IntentCoverageState(
        d1_covered=ALL_REGISTERS
    )

    for seed in range(50):
        target = RegisterTargetPolicy(
            Random(seed)
        ).select(
            ArmID.A0,
            state,
        )

        assert target.d1 in POSITIVE_REGISTERS
        assert target.d1 != 0


def test_same_seed_produces_same_single_target_trace():
    state = L2IntentCoverageState(
        d1_covered=frozenset({1, 2, 3}),
        d2_covered=frozenset({4, 5, 6}),
    )

    policy_a = RegisterTargetPolicy(Random(777))
    policy_b = RegisterTargetPolicy(Random(777))

    trace_a = [
        policy_a.select(ArmID.A0, state)
        for _ in range(20)
    ]

    trace_b = [
        policy_b.select(ArmID.A0, state)
        for _ in range(20)
    ]

    assert trace_a == trace_b


def test_a4_targets_two_distinct_registers():
    state = L2IntentCoverageState()

    for seed in range(50):
        target = RegisterTargetPolicy(
            Random(seed)
        ).select(
            ArmID.A4,
            state,
        )

        assert target.is_dual
        assert target.d1 != target.d2
        assert target.d1 in POSITIVE_REGISTERS
        assert target.d2 in POSITIVE_REGISTERS


def test_a4_hits_both_uncovered_opportunities_when_possible():
    d1_target = 7
    d2_target = 13

    state = L2IntentCoverageState(
        d1_covered=frozenset(
            register
            for register in POSITIVE_REGISTERS
            if register != d1_target
        ),
        d2_covered=frozenset(
            register
            for register in POSITIVE_REGISTERS
            if register != d2_target
        ),
    )

    for seed in range(20):
        target = RegisterTargetPolicy(
            Random(seed)
        ).select(
            ArmID.A4,
            state,
        )

        assert target.d1 == d1_target
        assert target.d2 == d2_target


def test_a4_same_single_uncovered_register_closes_only_one_side():
    only_uncovered = 9

    state = L2IntentCoverageState(
        d1_covered=frozenset(
            register
            for register in POSITIVE_REGISTERS
            if register != only_uncovered
        ),
        d2_covered=frozenset(
            register
            for register in POSITIVE_REGISTERS
            if register != only_uncovered
        ),
    )

    for seed in range(50):
        target = RegisterTargetPolicy(
            Random(seed)
        ).select(
            ArmID.A4,
            state,
        )

        assert target.d1 != target.d2

        number_of_uncovered_targets = (
            int(target.d1 == only_uncovered)
            + int(target.d2 == only_uncovered)
        )

        assert number_of_uncovered_targets == 1


def test_a4_prioritizes_remaining_uncovered_d2_when_d1_saturated():
    d2_target = 21

    state = L2IntentCoverageState(
        d1_covered=ALL_REGISTERS,
        d2_covered=frozenset(
            register
            for register in POSITIVE_REGISTERS
            if register != d2_target
        ),
    )

    for seed in range(50):
        target = RegisterTargetPolicy(
            Random(seed)
        ).select(
            ArmID.A4,
            state,
        )

        assert target.d2 == d2_target
        assert target.d1 != target.d2


def test_a4_prioritizes_remaining_uncovered_d1_when_d2_saturated():
    d1_target = 25

    state = L2IntentCoverageState(
        d1_covered=frozenset(
            register
            for register in POSITIVE_REGISTERS
            if register != d1_target
        ),
        d2_covered=ALL_REGISTERS,
    )

    for seed in range(50):
        target = RegisterTargetPolicy(
            Random(seed)
        ).select(
            ArmID.A4,
            state,
        )

        assert target.d1 == d1_target
        assert target.d1 != target.d2


def test_a4_fully_saturated_still_selects_legal_distinct_pair():
    state = L2IntentCoverageState(
        d1_covered=ALL_REGISTERS,
        d2_covered=ALL_REGISTERS,
    )

    for seed in range(50):
        target = RegisterTargetPolicy(
            Random(seed)
        ).select(
            ArmID.A4,
            state,
        )

        assert target.d1 in POSITIVE_REGISTERS
        assert target.d2 in POSITIVE_REGISTERS
        assert target.d1 != target.d2


def test_same_seed_produces_same_a4_trace():
    state = L2IntentCoverageState(
        d1_covered=frozenset({1, 2, 3, 4}),
        d2_covered=frozenset({5, 6, 7, 8}),
    )

    policy_a = RegisterTargetPolicy(Random(98765))
    policy_b = RegisterTargetPolicy(Random(98765))

    trace_a = [
        policy_a.select(ArmID.A4, state)
        for _ in range(20)
    ]

    trace_b = [
        policy_b.select(ArmID.A4, state)
        for _ in range(20)
    ]

    assert trace_a == trace_b


def test_target_selection_rejects_x0():
    with pytest.raises(ValueError):
        TargetSelection(d1=0)


def test_target_selection_rejects_equal_dual_targets():
    with pytest.raises(ValueError):
        TargetSelection(d1=10, d2=10)
