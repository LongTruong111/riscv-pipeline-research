from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

from research.week9.coverage_collector import CoverageCheckpoint
from research.week10.adaptive.epoch_coordinator import EpochCompletion
from research.week10.adaptive.template_library import ArmID


SCHEMA_VERSION = "week10-adaptive-v1"
CHECKPOINT_SEMANTICS = "post_instruction_cut_v1"


FloatArmSnapshot = tuple[tuple[str, float], ...]
IntArmSnapshot = tuple[tuple[str, int], ...]


class DecisionStateSource(Protocol):
    """
    Minimal adaptive-decision state required by telemetry.

    The real BanditDecisionEngine already satisfies this protocol.
    """

    @property
    def epoch_index(self) -> int:
        ...

    def q_values(self) -> Mapping[ArmID, float]:
        ...

    def pull_counts(self) -> Mapping[ArmID, int]:
        ...

    def recent_rewards(self) -> Mapping[ArmID, float]:
        ...


@dataclass(frozen=True)
class EpochTelemetryRecord:
    schema_version: str
    checkpoint_semantics: str

    epoch_index: int

    selected_arm: str
    selection_mode: str
    candidate_arms: tuple[str, ...]

    target_d1: int | None
    target_d2: int | None

    first_executed_instruction: int
    last_executed_instruction: int
    actual_executed_instructions: int

    covered_at_epoch_start_count: int

    global_observed_l2_intent_count: int
    attributable_observed_l2_intent_count: int

    global_new_l2_intent_count: int
    attributable_new_l2_intent_count: int

    reward: float

    q_value_before: float
    max_q_before: float

    old_q: float
    new_q: float
    pull_count: int

    q_values_after: FloatArmSnapshot
    pull_counts_after: IntArmSnapshot
    recent_rewards_after: FloatArmSnapshot


@dataclass(frozen=True)
class CampaignCheckpointRecord:
    schema_version: str
    checkpoint_semantics: str

    executed_instructions: int
    cycle: int

    l1_intent_count: int
    l1_validated_count: int

    l2_intent_count: int
    l2_validated_count: int

    epoch_index: int

    q_values: FloatArmSnapshot
    pull_counts: IntArmSnapshot
    recent_rewards: FloatArmSnapshot


@dataclass(frozen=True)
class CampaignRunSummary:
    schema_version: str
    checkpoint_semantics: str

    seed: int
    epsilon: float
    alpha: float
    q_floor: float

    nominal_batch: int
    instruction_budget: int

    executed_instructions: int
    completed_epochs: int
    termination_reason: str

    final_l1_intent_count: int
    final_l1_validated_count: int

    final_l2_intent_count: int
    final_l2_validated_count: int

    final_q_values: FloatArmSnapshot
    final_pull_counts: IntArmSnapshot
    final_recent_rewards: FloatArmSnapshot


def _float_arm_snapshot(
    values: Mapping[ArmID, float],
) -> FloatArmSnapshot:
    return tuple(
        sorted(
            (
                arm.value,
                float(value),
            )
            for arm, value in values.items()
        )
    )


def _int_arm_snapshot(
    values: Mapping[ArmID, int],
) -> IntArmSnapshot:
    return tuple(
        sorted(
            (
                arm.value,
                int(value),
            )
            for arm, value in values.items()
        )
    )


def _validate_target_register(
    value: int | None,
    *,
    name: str,
) -> None:
    if value is None:
        return

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= 31
    ):
        raise ValueError(
            f"{name} must be None or an integer in [1, 31]"
        )


class CampaignTelemetryRecorder:
    """
    Week10 adaptive-campaign telemetry coordinator.

    This class does not recompute:
      - reward;
      - arm selection;
      - Q updates;
      - coverage.

    It only validates and snapshots already-authoritative runtime
    results.

    With retain_records=False and streaming sinks, retained telemetry
    memory is O(1) with respect to campaign length. Snapshot cost is
    O(10) = O(1) because the adaptive arm universe is fixed.
    """

    def __init__(
        self,
        *,
        seed: int,
        epsilon: float,
        alpha: float,
        q_floor: float,
        nominal_batch: int,
        instruction_budget: int,
        retain_records: bool = True,
        epoch_sink: Callable[
            [EpochTelemetryRecord],
            None,
        ]
        | None = None,
        checkpoint_sink: Callable[
            [CampaignCheckpointRecord],
            None,
        ]
        | None = None,
        summary_sink: Callable[
            [CampaignRunSummary],
            None,
        ]
        | None = None,
    ) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")

        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon must be in [0, 1]")

        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")

        if q_floor < 0.0:
            raise ValueError("q_floor must be non-negative")

        if (
            isinstance(nominal_batch, bool)
            or not isinstance(nominal_batch, int)
            or nominal_batch <= 0
        ):
            raise ValueError(
                "nominal_batch must be a positive integer"
            )

        if (
            isinstance(instruction_budget, bool)
            or not isinstance(instruction_budget, int)
            or instruction_budget <= 0
        ):
            raise ValueError(
                "instruction_budget must be a positive integer"
            )

        self.seed = seed
        self.epsilon = float(epsilon)
        self.alpha = float(alpha)
        self.q_floor = float(q_floor)

        self.nominal_batch = nominal_batch
        self.instruction_budget = instruction_budget

        self.retain_records = retain_records

        self.epoch_sink = epoch_sink
        self.checkpoint_sink = checkpoint_sink
        self.summary_sink = summary_sink

        self._epoch_records: list[
            EpochTelemetryRecord
        ] = []

        self._checkpoint_records: list[
            CampaignCheckpointRecord
        ] = []

        self._summary: CampaignRunSummary | None = None

        self._completed_epochs = 0
        self._closed_epoch_executed_instructions = 0

        self._last_checkpoint_instruction = 0

    @property
    def epoch_records(
        self,
    ) -> tuple[EpochTelemetryRecord, ...]:
        return tuple(self._epoch_records)

    @property
    def checkpoint_records(
        self,
    ) -> tuple[CampaignCheckpointRecord, ...]:
        return tuple(self._checkpoint_records)

    @property
    def summary(self) -> CampaignRunSummary | None:
        return self._summary

    @property
    def completed_epochs(self) -> int:
        return self._completed_epochs

    @property
    def closed_epoch_executed_instructions(
        self,
    ) -> int:
        return self._closed_epoch_executed_instructions

    def record_epoch(
        self,
        completion: EpochCompletion,
        *,
        decision_state: DecisionStateSource,
    ) -> EpochTelemetryRecord:
        decision = completion.start.decision
        reward_result = completion.reward_result
        update = completion.bandit_update

        expected_epoch = self._completed_epochs

        if decision.epoch_index != expected_epoch:
            raise AssertionError(
                "epoch telemetry discontinuity: "
                f"expected={expected_epoch}, "
                f"decision={decision.epoch_index}"
            )

        if update.epoch_index != decision.epoch_index:
            raise AssertionError(
                "decision/update epoch mismatch"
            )

        if reward_result.arm_id != decision.arm_id:
            raise AssertionError(
                "decision/reward arm mismatch"
            )

        if update.arm_id != decision.arm_id:
            raise AssertionError(
                "decision/update arm mismatch"
            )

        if update.reward != reward_result.reward:
            raise AssertionError(
                "reward result and bandit update disagree"
            )

        if decision.epsilon != self.epsilon:
            raise AssertionError(
                "decision epsilon differs from campaign config"
            )

        actual = reward_result.actual_executed_instructions

        if (
            isinstance(actual, bool)
            or not isinstance(actual, int)
            or actual <= 0
        ):
            raise AssertionError(
                "epoch actual executed count must be positive"
            )

        target_d1 = completion.start.target.d1
        target_d2 = completion.start.target.d2

        _validate_target_register(
            target_d1,
            name="target_d1",
        )

        _validate_target_register(
            target_d2,
            name="target_d2",
        )

        first_executed = (
            self._closed_epoch_executed_instructions + 1
        )

        last_executed = (
            first_executed
            + actual
            - 1
        )

        q_values = decision_state.q_values()
        pull_counts = decision_state.pull_counts()
        recent_rewards = decision_state.recent_rewards()

        if decision_state.epoch_index != expected_epoch + 1:
            raise AssertionError(
                "decision-engine epoch index did not advance "
                "exactly once at epoch completion"
            )

        if q_values[decision.arm_id] != update.new_q:
            raise AssertionError(
                "selected-arm Q snapshot disagrees with update"
            )

        if pull_counts[decision.arm_id] != update.pull_count:
            raise AssertionError(
                "selected-arm pull-count snapshot disagrees "
                "with update"
            )

        if (
            recent_rewards[decision.arm_id]
            != reward_result.reward
        ):
            raise AssertionError(
                "selected-arm recent reward disagrees "
                "with epoch reward"
            )

        record = EpochTelemetryRecord(
            schema_version=SCHEMA_VERSION,
            checkpoint_semantics=CHECKPOINT_SEMANTICS,
            epoch_index=decision.epoch_index,
            selected_arm=decision.arm_id.value,
            selection_mode=decision.mode.value,
            candidate_arms=tuple(
                arm.value
                for arm in decision.candidate_arms
            ),
            target_d1=target_d1,
            target_d2=target_d2,
            first_executed_instruction=(
                first_executed
            ),
            last_executed_instruction=(
                last_executed
            ),
            actual_executed_instructions=actual,
            covered_at_epoch_start_count=len(
                completion.start.covered_at_epoch_start
            ),
            global_observed_l2_intent_count=len(
                reward_result.observed_intent_bins
            ),
            attributable_observed_l2_intent_count=len(
                reward_result.attributable_observed_intent_bins
            ),
            global_new_l2_intent_count=(
                reward_result.global_new_count
            ),
            attributable_new_l2_intent_count=(
                reward_result.attributable_new_count
            ),
            reward=reward_result.reward,
            q_value_before=decision.q_value_before,
            max_q_before=decision.max_q_before,
            old_q=update.old_q,
            new_q=update.new_q,
            pull_count=update.pull_count,
            q_values_after=_float_arm_snapshot(
                q_values
            ),
            pull_counts_after=_int_arm_snapshot(
                pull_counts
            ),
            recent_rewards_after=_float_arm_snapshot(
                recent_rewards
            ),
        )

        self._completed_epochs += 1
        self._closed_epoch_executed_instructions = (
            last_executed
        )

        if self.retain_records:
            self._epoch_records.append(record)

        if self.epoch_sink is not None:
            self.epoch_sink(record)

        return record

    def record_checkpoint(
        self,
        checkpoint: CoverageCheckpoint,
        *,
        epoch_index: int,
        decision_state: DecisionStateSource,
    ) -> CampaignCheckpointRecord:
        if (
            isinstance(epoch_index, bool)
            or not isinstance(epoch_index, int)
            or epoch_index < 0
        ):
            raise ValueError(
                "epoch_index must be a non-negative integer"
            )

        if (
            checkpoint.executed_instructions
            <= self._last_checkpoint_instruction
        ):
            raise AssertionError(
                "checkpoint executed-instruction count "
                "must be strictly increasing"
            )

        record = CampaignCheckpointRecord(
            schema_version=SCHEMA_VERSION,
            checkpoint_semantics=CHECKPOINT_SEMANTICS,
            executed_instructions=(
                checkpoint.executed_instructions
            ),
            cycle=checkpoint.cycle,
            l1_intent_count=(
                checkpoint.l1_intent_count
            ),
            l1_validated_count=(
                checkpoint.l1_validated_count
            ),
            l2_intent_count=(
                checkpoint.l2_intent_count
            ),
            l2_validated_count=(
                checkpoint.l2_validated_count
            ),
            epoch_index=epoch_index,
            q_values=_float_arm_snapshot(
                decision_state.q_values()
            ),
            pull_counts=_int_arm_snapshot(
                decision_state.pull_counts()
            ),
            recent_rewards=_float_arm_snapshot(
                decision_state.recent_rewards()
            ),
        )

        self._last_checkpoint_instruction = (
            checkpoint.executed_instructions
        )

        if self.retain_records:
            self._checkpoint_records.append(record)

        if self.checkpoint_sink is not None:
            self.checkpoint_sink(record)

        return record

    def finalize(
        self,
        *,
        termination_reason: str,
        executed_instructions: int,
        final_l1_intent_count: int,
        final_l1_validated_count: int,
        final_l2_intent_count: int,
        final_l2_validated_count: int,
        decision_state: DecisionStateSource,
    ) -> CampaignRunSummary:
        if self._summary is not None:
            raise RuntimeError(
                "campaign telemetry already finalized"
            )

        if not termination_reason:
            raise ValueError(
                "termination_reason must be non-empty"
            )

        if (
            executed_instructions
            != self._closed_epoch_executed_instructions
        ):
            raise AssertionError(
                "final executed count does not equal "
                "the sum of closed adaptive epochs"
            )

        if (
            decision_state.epoch_index
            != self._completed_epochs
        ):
            raise AssertionError(
                "final decision-engine epoch index differs "
                "from completed telemetry epochs"
            )

        final_counts = (
            final_l1_intent_count,
            final_l1_validated_count,
            final_l2_intent_count,
            final_l2_validated_count,
        )

        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for value in final_counts
        ):
            raise ValueError(
                "final coverage counts must be "
                "non-negative integers"
            )

        summary = CampaignRunSummary(
            schema_version=SCHEMA_VERSION,
            checkpoint_semantics=CHECKPOINT_SEMANTICS,
            seed=self.seed,
            epsilon=self.epsilon,
            alpha=self.alpha,
            q_floor=self.q_floor,
            nominal_batch=self.nominal_batch,
            instruction_budget=self.instruction_budget,
            executed_instructions=(
                executed_instructions
            ),
            completed_epochs=self._completed_epochs,
            termination_reason=termination_reason,
            final_l1_intent_count=(
                final_l1_intent_count
            ),
            final_l1_validated_count=(
                final_l1_validated_count
            ),
            final_l2_intent_count=(
                final_l2_intent_count
            ),
            final_l2_validated_count=(
                final_l2_validated_count
            ),
            final_q_values=_float_arm_snapshot(
                decision_state.q_values()
            ),
            final_pull_counts=_int_arm_snapshot(
                decision_state.pull_counts()
            ),
            final_recent_rewards=_float_arm_snapshot(
                decision_state.recent_rewards()
            ),
        )

        self._summary = summary

        if self.summary_sink is not None:
            self.summary_sink(summary)

        return summary
