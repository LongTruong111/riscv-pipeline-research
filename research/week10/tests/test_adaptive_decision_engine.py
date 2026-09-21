from random import Random

import pytest

from research.week10.adaptive.decision_engine import (
    ARM_ORDER,
    DEFAULT_Q_FLOOR,
    Q_INIT,
    BanditConfig,
    BanditDecisionEngine,
    SelectionMode,
)
from research.week10.adaptive.template_library import ArmID


class ScriptedRandom(Random):
    """
    Controlled RNG used only for deterministic policy-conformance tests.

    random_values:
        Values returned by random().

    choice_indices:
        Requested candidate index for each choice(). The index is
        reduced modulo sequence length so tests can explicitly exercise
        candidate-set semantics without probabilistic assertions.
    """

    def __init__(
        self,
        *,
        random_values=(),
        choice_indices=(),
    ):
        super().__init__(0)
        self._random_values = list(random_values)
        self._choice_indices = list(choice_indices)

    def random(self):
        if not self._random_values:
            raise AssertionError(
                "unexpected random() call"
            )

        return self._random_values.pop(0)

    def choice(self, sequence):
        if not sequence:
            raise AssertionError(
                "choice() received empty candidate sequence"
            )

        if not self._choice_indices:
            raise AssertionError(
                "unexpected choice() call"
            )

        index = self._choice_indices.pop(0)

        return sequence[index % len(sequence)]


def config(
    *,
    epsilon=0.10,
    alpha=0.30,
    q_floor=DEFAULT_Q_FLOOR,
):
    return BanditConfig(
        epsilon=epsilon,
        alpha=alpha,
        q_floor=q_floor,
    )


def test_arm_order_is_exactly_all_ten_frozen_arms():
    assert ARM_ORDER == (
        ArmID.A0,
        ArmID.A1,
        ArmID.A2,
        ArmID.A3,
        ArmID.A4,
        ArmID.A5,
        ArmID.A6,
        ArmID.A7,
        ArmID.A8,
        ArmID.A9,
    )


@pytest.mark.parametrize(
    "epsilon",
    [-0.01, 1.01, float("inf"), float("nan")],
)
def test_invalid_epsilon_rejected(epsilon):
    with pytest.raises(ValueError):
        BanditConfig(
            epsilon=epsilon,
            alpha=0.30,
        )


@pytest.mark.parametrize(
    "alpha",
    [-0.01, 1.01, float("inf"), float("nan")],
)
def test_invalid_alpha_rejected(alpha):
    with pytest.raises(ValueError):
        BanditConfig(
            epsilon=0.10,
            alpha=alpha,
        )


@pytest.mark.parametrize(
    "q_floor",
    [-0.01, float("inf"), float("nan")],
)
def test_invalid_q_floor_rejected(q_floor):
    with pytest.raises(ValueError):
        BanditConfig(
            epsilon=0.10,
            alpha=0.30,
            q_floor=q_floor,
        )


def test_initial_state_is_frozen_zero_state():
    engine = BanditDecisionEngine(
        config=config(),
        rng=Random(1),
    )

    assert engine.epoch_index == 0
    assert not engine.learning_has_begun

    assert all(
        value == Q_INIT
        for value in engine.q_values().values()
    )

    assert all(
        count == 0
        for count in engine.pull_counts().values()
    )

    assert all(
        reward == 0.0
        for reward in engine.recent_rewards().values()
    )


def test_epoch_zero_does_not_use_q_floor_fallback():
    rng = ScriptedRandom(
        random_values=[0.50],
        choice_indices=[4],
    )

    engine = BanditDecisionEngine(
        config=config(
            epsilon=0.10,
            q_floor=0.05,
        ),
        rng=rng,
    )

    decision = engine.select_arm()

    assert decision.epoch_index == 0

    # All Q values are zero and therefore below Q_floor, but the
    # fallback must not be active before the first learning update.
    assert (
        decision.mode
        is SelectionMode.GREEDY_EXPLOITATION
    )

    assert decision.candidate_arms == ARM_ORDER
    assert decision.arm_id == ArmID.A4


def test_epsilon_exploration_uses_all_ten_arms():
    rng = ScriptedRandom(
        random_values=[0.05],
        choice_indices=[8],
    )

    engine = BanditDecisionEngine(
        config=config(epsilon=0.10),
        rng=rng,
    )

    decision = engine.select_arm()

    assert (
        decision.mode
        is SelectionMode.EPSILON_EXPLORATION
    )
    assert decision.candidate_arms == ARM_ORDER
    assert decision.arm_id == ArmID.A8


def test_epsilon_equal_zero_forces_exploitation():
    rng = ScriptedRandom(
        random_values=[0.0],
        choice_indices=[3],
    )

    engine = BanditDecisionEngine(
        config=config(epsilon=0.0),
        rng=rng,
    )

    decision = engine.select_arm()

    assert (
        decision.mode
        is SelectionMode.GREEDY_EXPLOITATION
    )


def test_epsilon_equal_one_forces_exploration():
    rng = ScriptedRandom(
        random_values=[0.999],
        choice_indices=[6],
    )

    engine = BanditDecisionEngine(
        config=config(epsilon=1.0),
        rng=rng,
    )

    decision = engine.select_arm()

    assert (
        decision.mode
        is SelectionMode.EPSILON_EXPLORATION
    )
    assert decision.arm_id == ArmID.A6


def test_q_update_matches_recency_weighted_formula():
    engine = BanditDecisionEngine(
        config=config(alpha=0.30),
        rng=Random(1),
    )

    update_1 = engine.update(
        arm_id=ArmID.A2,
        reward=2.0,
    )

    assert update_1.old_q == pytest.approx(0.0)
    assert update_1.new_q == pytest.approx(0.6)

    update_2 = engine.update(
        arm_id=ArmID.A2,
        reward=1.0,
    )

    expected = 0.6 + 0.30 * (1.0 - 0.6)

    assert update_2.old_q == pytest.approx(0.6)
    assert update_2.new_q == pytest.approx(expected)
    assert update_2.new_q == pytest.approx(0.72)


def test_only_selected_arm_q_is_updated():
    engine = BanditDecisionEngine(
        config=config(alpha=0.50),
        rng=Random(1),
    )

    before = dict(engine.q_values())

    engine.update(
        arm_id=ArmID.A5,
        reward=4.0,
    )

    after = dict(engine.q_values())

    for arm in ARM_ORDER:
        if arm is ArmID.A5:
            assert after[arm] == pytest.approx(2.0)
        else:
            assert after[arm] == before[arm]


def test_update_increments_only_selected_pull_count():
    engine = BanditDecisionEngine(
        config=config(),
        rng=Random(1),
    )

    engine.update(
        arm_id=ArmID.A3,
        reward=1.0,
    )

    counts = engine.pull_counts()

    assert counts[ArmID.A3] == 1

    for arm in ARM_ORDER:
        if arm is not ArmID.A3:
            assert counts[arm] == 0


def test_recent_reward_is_per_arm():
    engine = BanditDecisionEngine(
        config=config(),
        rng=Random(1),
    )

    engine.update(
        arm_id=ArmID.A1,
        reward=3.0,
    )

    engine.update(
        arm_id=ArmID.A7,
        reward=2.0,
    )

    rewards = engine.recent_rewards()

    assert rewards[ArmID.A1] == pytest.approx(3.0)
    assert rewards[ArmID.A7] == pytest.approx(2.0)
    assert rewards[ArmID.A0] == pytest.approx(0.0)


def test_epoch_index_advances_after_each_observation():
    engine = BanditDecisionEngine(
        config=config(),
        rng=Random(1),
    )

    assert engine.epoch_index == 0

    update_0 = engine.update(
        arm_id=ArmID.A0,
        reward=1.0,
    )

    assert update_0.epoch_index == 0
    assert engine.epoch_index == 1

    update_1 = engine.update(
        arm_id=ArmID.A1,
        reward=1.0,
    )

    assert update_1.epoch_index == 1
    assert engine.epoch_index == 2


@pytest.mark.parametrize(
    "reward",
    [-0.01, float("inf"), float("-inf"), float("nan")],
)
def test_invalid_reward_rejected(reward):
    engine = BanditDecisionEngine(
        config=config(),
        rng=Random(1),
    )

    with pytest.raises(ValueError):
        engine.update(
            arm_id=ArmID.A0,
            reward=reward,
        )


def test_q_floor_fallback_activates_after_learning():
    rng = ScriptedRandom(
        choice_indices=[7],
    )

    engine = BanditDecisionEngine(
        config=config(
            epsilon=0.0,
            alpha=1.0,
            q_floor=0.05,
        ),
        rng=rng,
    )

    # First completed observation leaves max(Q)=0.01 <= 0.05.
    engine.update(
        arm_id=ArmID.A0,
        reward=0.01,
    )

    decision = engine.select_arm()

    assert (
        decision.mode
        is SelectionMode.Q_FLOOR_UNIFORM
    )
    assert decision.candidate_arms == ARM_ORDER
    assert decision.arm_id == ArmID.A7


def test_q_floor_uniform_does_not_consume_epsilon_draw():
    rng = ScriptedRandom(
        # Deliberately no random_values.
        choice_indices=[2],
    )

    engine = BanditDecisionEngine(
        config=config(
            epsilon=0.90,
            alpha=1.0,
            q_floor=0.05,
        ),
        rng=rng,
    )

    engine.update(
        arm_id=ArmID.A0,
        reward=0.0,
    )

    decision = engine.select_arm()

    assert (
        decision.mode
        is SelectionMode.Q_FLOOR_UNIFORM
    )
    assert decision.arm_id == ArmID.A2


def test_above_q_floor_uses_normal_epsilon_greedy():
    rng = ScriptedRandom(
        random_values=[0.50],
        choice_indices=[0],
    )

    engine = BanditDecisionEngine(
        config=config(
            epsilon=0.10,
            alpha=1.0,
            q_floor=0.05,
        ),
        rng=rng,
    )

    engine.update(
        arm_id=ArmID.A6,
        reward=1.0,
    )

    decision = engine.select_arm()

    assert (
        decision.mode
        is SelectionMode.GREEDY_EXPLOITATION
    )
    assert decision.candidate_arms == (ArmID.A6,)
    assert decision.arm_id == ArmID.A6


def test_exploitation_selects_only_max_q_arm():
    rng = ScriptedRandom(
        random_values=[0.99],
        choice_indices=[0],
    )

    engine = BanditDecisionEngine(
        config=config(
            epsilon=0.10,
            alpha=1.0,
        ),
        rng=rng,
    )

    engine.update(
        arm_id=ArmID.A4,
        reward=2.0,
    )

    decision = engine.select_arm()

    assert decision.max_q_before == pytest.approx(2.0)
    assert decision.candidate_arms == (ArmID.A4,)
    assert decision.arm_id == ArmID.A4


def test_equal_max_q_tie_uses_seeded_choice():
    rng = ScriptedRandom(
        random_values=[0.99],
        choice_indices=[1],
    )

    engine = BanditDecisionEngine(
        config=config(
            epsilon=0.10,
            alpha=1.0,
            q_floor=0.05,
        ),
        rng=rng,
    )

    engine.update(
        arm_id=ArmID.A2,
        reward=2.0,
    )

    engine.update(
        arm_id=ArmID.A7,
        reward=2.0,
    )

    decision = engine.select_arm()

    assert decision.candidate_arms == (
        ArmID.A2,
        ArmID.A7,
    )

    # choice index 1 must select the second tied maximum.
    assert decision.arm_id == ArmID.A7


def test_exploration_can_select_nonmaximal_arm():
    rng = ScriptedRandom(
        random_values=[0.01],
        choice_indices=[9],
    )

    engine = BanditDecisionEngine(
        config=config(
            epsilon=0.10,
            alpha=1.0,
        ),
        rng=rng,
    )

    engine.update(
        arm_id=ArmID.A0,
        reward=3.0,
    )

    decision = engine.select_arm()

    assert (
        decision.mode
        is SelectionMode.EPSILON_EXPLORATION
    )

    assert decision.candidate_arms == ARM_ORDER
    assert decision.arm_id == ArmID.A9
    assert decision.arm_id is not ArmID.A0


def test_no_global_q_decay_occurs():
    engine = BanditDecisionEngine(
        config=config(alpha=0.50),
        rng=Random(1),
    )

    engine.update(
        arm_id=ArmID.A0,
        reward=4.0,
    )

    q_a0 = engine.q_values()[ArmID.A0]

    engine.update(
        arm_id=ArmID.A1,
        reward=2.0,
    )

    assert engine.q_values()[ArmID.A0] == pytest.approx(
        q_a0
    )


def test_arm_state_returns_detached_copy():
    engine = BanditDecisionEngine(
        config=config(),
        rng=Random(1),
    )

    snapshot = engine.arm_state(ArmID.A0)

    snapshot.q_value = 999.0

    assert engine.q_values()[ArmID.A0] == Q_INIT


def test_same_seed_same_inputs_produce_identical_trace():
    seed = 20260921

    engine_a = BanditDecisionEngine(
        config=config(),
        rng=Random(seed),
    )

    engine_b = BanditDecisionEngine(
        config=config(),
        rng=Random(seed),
    )

    rewards = [
        0.0,
        1.0,
        0.0,
        2.0,
        0.5,
        0.0,
        3.0,
        0.0,
        1.5,
        0.0,
        0.25,
        2.5,
    ]

    trace_a = []
    trace_b = []

    for reward in rewards:
        decision_a = engine_a.select_arm()
        update_a = engine_a.update(
            arm_id=decision_a.arm_id,
            reward=reward,
        )

        decision_b = engine_b.select_arm()
        update_b = engine_b.update(
            arm_id=decision_b.arm_id,
            reward=reward,
        )

        trace_a.append(
            (
                decision_a,
                update_a,
                dict(engine_a.q_values()),
            )
        )

        trace_b.append(
            (
                decision_b,
                update_b,
                dict(engine_b.q_values()),
            )
        )

    assert trace_a == trace_b


def test_different_seed_is_allowed_to_change_trace():
    config_value = config()

    engine_a = BanditDecisionEngine(
        config=config_value,
        rng=Random(1001),
    )

    engine_b = BanditDecisionEngine(
        config=config_value,
        rng=Random(2001),
    )

    trace_a = []
    trace_b = []

    for _ in range(30):
        decision_a = engine_a.select_arm()
        decision_b = engine_b.select_arm()

        trace_a.append(decision_a.arm_id)
        trace_b.append(decision_b.arm_id)

        engine_a.update(
            arm_id=decision_a.arm_id,
            reward=0.0,
        )

        engine_b.update(
            arm_id=decision_b.arm_id,
            reward=0.0,
        )

    assert trace_a != trace_b


def test_q_snapshot_is_detached_from_engine():
    engine = BanditDecisionEngine(
        config=config(),
        rng=Random(1),
    )

    snapshot = engine.q_values()

    # q_values() returns a detached ordinary mapping.
    snapshot[ArmID.A0] = 100.0

    assert engine.q_values()[ArmID.A0] == Q_INIT
