from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from random import Random
from typing import Dict, Mapping

from research.week10.adaptive.template_library import ArmID


ARM_ORDER: tuple[ArmID, ...] = tuple(
    sorted(ArmID, key=lambda arm: arm.value)
)

Q_INIT = 0.0
DEFAULT_Q_FLOOR = 0.05


class SelectionMode(str, Enum):
    """
    Mechanism used to select one adaptive arm.
    """

    EPSILON_EXPLORATION = "epsilon_exploration"
    GREEDY_EXPLOITATION = "greedy_exploitation"
    Q_FLOOR_UNIFORM = "q_floor_uniform"


@dataclass(frozen=True)
class BanditConfig:
    """
    Frozen epsilon-greedy bandit parameters.

    alpha:
        Recency-weighted action-value update coefficient.

    epsilon:
        Exploration probability when Q-floor fallback is not active.

    q_floor:
        If at least one learning observation has occurred and max(Q)
        is <= q_floor, selection falls back to seeded-uniform over all
        ten arms.
    """

    epsilon: float
    alpha: float
    q_floor: float = DEFAULT_Q_FLOOR

    def __post_init__(self) -> None:
        if not isfinite(self.epsilon):
            raise ValueError("epsilon must be finite")

        if not 0.0 <= self.epsilon <= 1.0:
            raise ValueError(
                f"epsilon must be in [0, 1], got {self.epsilon}"
            )

        if not isfinite(self.alpha):
            raise ValueError("alpha must be finite")

        if not 0.0 <= self.alpha <= 1.0:
            raise ValueError(
                f"alpha must be in [0, 1], got {self.alpha}"
            )

        if not isfinite(self.q_floor):
            raise ValueError("q_floor must be finite")

        if self.q_floor < 0.0:
            raise ValueError(
                f"q_floor must be non-negative, got {self.q_floor}"
            )


@dataclass
class ArmState:
    """
    Bounded per-arm adaptive state.
    """

    q_value: float = Q_INIT
    pull_count: int = 0
    recent_reward: float = 0.0


@dataclass(frozen=True)
class BanditDecision:
    """
    Immutable arm-selection result for one epoch.
    """

    epoch_index: int
    arm_id: ArmID
    mode: SelectionMode
    candidate_arms: tuple[ArmID, ...]
    q_value_before: float
    max_q_before: float
    epsilon: float


@dataclass(frozen=True)
class BanditUpdate:
    """
    Immutable learning update result.
    """

    epoch_index: int
    arm_id: ArmID
    reward: float
    old_q: float
    new_q: float
    pull_count: int


class BanditDecisionEngine:
    """
    Epsilon-greedy multi-armed bandit with a recency-weighted
    action-value estimate.

    This is deliberately not classical Q-learning:
      - no explicit environment state;
      - no transition model;
      - no discount factor;
      - no bootstrapped next-state action value.

    Retained adaptive state is bounded by the fixed ten-arm set.
    """

    def __init__(
        self,
        *,
        config: BanditConfig,
        rng: Random,
    ) -> None:
        self._config = config
        self._rng = rng

        self._states: Dict[ArmID, ArmState] = {
            arm: ArmState()
            for arm in ARM_ORDER
        }

        # Number of completed reward observations.
        # Also equals the next decision's epoch index.
        self._epoch_index = 0

    @property
    def config(self) -> BanditConfig:
        return self._config

    @property
    def epoch_index(self) -> int:
        return self._epoch_index

    @property
    def learning_has_begun(self) -> bool:
        return self._epoch_index > 0

    def q_values(self) -> Mapping[ArmID, float]:
        """
        Return a detached snapshot of current action values.
        """
        return {
            arm: state.q_value
            for arm, state in self._states.items()
        }

    def pull_counts(self) -> Mapping[ArmID, int]:
        """
        Return a detached snapshot of pull counts.
        """
        return {
            arm: state.pull_count
            for arm, state in self._states.items()
        }

    def recent_rewards(self) -> Mapping[ArmID, float]:
        """
        Return a detached snapshot of most recent per-arm rewards.
        """
        return {
            arm: state.recent_reward
            for arm, state in self._states.items()
        }

    def arm_state(self, arm_id: ArmID) -> ArmState:
        """
        Return a detached copy of one arm's state.
        """
        state = self._states[arm_id]

        return ArmState(
            q_value=state.q_value,
            pull_count=state.pull_count,
            recent_reward=state.recent_reward,
        )

    def select_arm(self) -> BanditDecision:
        """
        Select one arm for the next epoch.

        Priority:

        1. After learning has begun:
               max(Q) <= Q_floor
           -> seeded-uniform over all ten arms.

        2. Otherwise epsilon-greedy:
           - exploration -> uniform all ten arms;
           - exploitation -> seeded-uniform among max-Q arms.

        At epoch zero Q-floor fallback is intentionally not applied.
        """
        max_q = max(
            state.q_value
            for state in self._states.values()
        )

        if (
            self.learning_has_begun
            and max_q <= self._config.q_floor
        ):
            candidates = ARM_ORDER
            arm_id = self._rng.choice(candidates)

            return BanditDecision(
                epoch_index=self._epoch_index,
                arm_id=arm_id,
                mode=SelectionMode.Q_FLOOR_UNIFORM,
                candidate_arms=candidates,
                q_value_before=self._states[arm_id].q_value,
                max_q_before=max_q,
                epsilon=self._config.epsilon,
            )

        epsilon_draw = self._rng.random()

        if epsilon_draw < self._config.epsilon:
            candidates = ARM_ORDER
            arm_id = self._rng.choice(candidates)
            mode = SelectionMode.EPSILON_EXPLORATION

        else:
            candidates = tuple(
                arm
                for arm in ARM_ORDER
                if self._states[arm].q_value == max_q
            )

            arm_id = self._rng.choice(candidates)
            mode = SelectionMode.GREEDY_EXPLOITATION

        return BanditDecision(
            epoch_index=self._epoch_index,
            arm_id=arm_id,
            mode=mode,
            candidate_arms=candidates,
            q_value_before=self._states[arm_id].q_value,
            max_q_before=max_q,
            epsilon=self._config.epsilon,
        )

    def update(
        self,
        *,
        arm_id: ArmID,
        reward: float,
    ) -> BanditUpdate:
        """
        Apply one recency-weighted action-value update:

            Q_new = Q_old + alpha * (reward - Q_old)

        Only the selected arm is modified.
        """
        if not isfinite(reward):
            raise ValueError("reward must be finite")

        if reward < 0.0:
            raise ValueError(
                f"reward must be non-negative, got {reward}"
            )

        state = self._states[arm_id]

        old_q = state.q_value
        new_q = old_q + (
            self._config.alpha
            * (reward - old_q)
        )

        if not isfinite(new_q):
            raise RuntimeError(
                "bandit Q update produced a non-finite value"
            )

        state.q_value = new_q
        state.pull_count += 1
        state.recent_reward = reward

        completed_epoch = self._epoch_index
        self._epoch_index += 1

        return BanditUpdate(
            epoch_index=completed_epoch,
            arm_id=arm_id,
            reward=reward,
            old_q=old_q,
            new_q=new_q,
            pull_count=state.pull_count,
        )
