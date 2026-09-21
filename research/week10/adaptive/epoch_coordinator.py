from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterable, Tuple

from research.week5.impl.coverage_model import (
    D1,
    D2,
    L2Hit,
)
from research.week5.impl.execution_event import ExecutionEvent
from research.week7.timing_oracle_v1 import TimingExpectationV1

from research.week10.adaptive.decision_engine import (
    BanditDecision,
    BanditDecisionEngine,
    BanditUpdate,
)
from research.week10.adaptive.provenance import (
    AttributionRegistry,
    AttributionWitness,
)
from research.week10.adaptive.register_policy import (
    L2IntentCoverageState,
    RegisterTargetPolicy,
    TargetSelection,
)
from research.week10.adaptive.reward_engine import (
    EpochRewardResult,
    EpochRewardTracker,
    L2IntentBin,
)
from research.week10.adaptive.template_library import Distance
from research.week10.l2_live_coordinator import L2LiveCoordinator
from research.week10.l2_realization import L2ValidationOutcome


@dataclass(frozen=True)
class EpochStart:
    """
    Immutable adaptive decision made at the beginning of one epoch.
    """

    decision: BanditDecision
    target: TargetSelection
    covered_at_epoch_start: FrozenSet[L2IntentBin]


@dataclass(frozen=True)
class EpochCompletion:
    """
    Immutable result produced when one adaptive epoch is closed.
    """

    start: EpochStart
    reward_result: EpochRewardResult
    bandit_update: BanditUpdate


@dataclass
class _ActiveEpoch:
    start: EpochStart
    reward_tracker: EpochRewardTracker


class AdaptiveEpochCoordinator:
    """
    Coordinates the bounded Adaptive-CGS learning lifecycle.

    Responsibilities:
      - snapshot global L2 Intent at epoch start;
      - select exactly one adaptive arm;
      - select arm-compatible L2 target register(s);
      - observe live L2 Intent hits;
      - compute attributable Intent reward;
      - update only the selected bandit arm.

    Explicitly not responsible for:
      - counting clock cycles;
      - deciding whether an instruction was architecturally executed;
      - RTL simulation;
      - Validated-coverage reward;
      - campaign termination;
      - telemetry persistence.

    Those remain separate concerns.
    """

    def __init__(
        self,
        *,
        decision_engine: BanditDecisionEngine,
        register_policy: RegisterTargetPolicy,
        live_coordinator: L2LiveCoordinator,
    ) -> None:
        if not isinstance(
            decision_engine,
            BanditDecisionEngine,
        ):
            raise TypeError(
                "decision_engine must be BanditDecisionEngine"
            )

        if not isinstance(
            register_policy,
            RegisterTargetPolicy,
        ):
            raise TypeError(
                "register_policy must be RegisterTargetPolicy"
            )

        if not isinstance(
            live_coordinator,
            L2LiveCoordinator,
        ):
            raise TypeError(
                "live_coordinator must be L2LiveCoordinator"
            )

        self._decision_engine = decision_engine
        self._register_policy = register_policy
        self._live = live_coordinator

        self._active: _ActiveEpoch | None = None
        self._attribution = AttributionRegistry()

    @property
    def pending_attribution_witness_count(
        self,
    ) -> int:
        return self._attribution.pending_count

    @property
    def active(self) -> bool:
        return self._active is not None
    @property
    def current_epoch(self) -> EpochStart | None:
        if self._active is None:
            return None

        return self._active.start

    @property
    def decision_engine(self) -> BanditDecisionEngine:
        return self._decision_engine

    @property
    def live_coordinator(self) -> L2LiveCoordinator:
        return self._live

    @staticmethod
    def _distance_from_live(
        distance: int,
    ) -> Distance:
        if distance == D1:
            return Distance.D1

        if distance == D2:
            return Distance.D2

        raise ValueError(
            f"L2 distance must be d1/d2, got {distance}"
        )

    @classmethod
    def _intent_bin_from_hit(
        cls,
        hit: L2Hit,
    ) -> L2IntentBin:
        return L2IntentBin(
            distance=cls._distance_from_live(
                hit.distance
            ),
            register=hit.register,
        )

    def _snapshot_global_intent(
        self,
    ) -> FrozenSet[L2IntentBin]:
        """
        Snapshot current Week9 global L2 Intent state.

        Validated state is deliberately ignored.
        """
        bins: set[L2IntentBin] = set()

        for (
            distance_name,
            register,
        ), state in self._live.coverage.l2_state.items():
            if not state.intent_seen:
                continue

            if distance_name == "d1":
                distance = Distance.D1
            elif distance_name == "d2":
                distance = Distance.D2
            else:
                raise RuntimeError(
                    "unexpected L2 coverage distance: "
                    f"{distance_name!r}"
                )

            bins.add(
                L2IntentBin(
                    distance=distance,
                    register=register,
                )
            )

        return frozenset(bins)

    @staticmethod
    def _targeting_coverage(
        snapshot: FrozenSet[L2IntentBin],
    ) -> L2IntentCoverageState:
        """
        Convert the global Intent snapshot into the bounded representation
        required by RegisterTargetPolicy.
        """
        d1_covered = frozenset(
            bin_value.register
            for bin_value in snapshot
            if bin_value.distance is Distance.D1
        )

        d2_covered = frozenset(
            bin_value.register
            for bin_value in snapshot
            if bin_value.distance is Distance.D2
        )

        return L2IntentCoverageState(
            d1_covered=d1_covered,
            d2_covered=d2_covered,
        )

    def begin_epoch(self) -> EpochStart:
        """
        Start exactly one adaptive epoch.

        No second epoch may be started until the active epoch has been
        finalized.
        """
        if self._active is not None:
            raise RuntimeError(
                "cannot begin a new epoch while another is active"
            )

        if self._attribution.pending_count != 0:
            raise RuntimeError(
                "cannot begin epoch with stale "
                "attribution witnesses"
            )

        covered_at_start = (
            self._snapshot_global_intent()
        )

        decision = self._decision_engine.select_arm()

        target = self._register_policy.select(
            decision.arm_id,
            self._targeting_coverage(
                covered_at_start
            ),
        )

        start = EpochStart(
            decision=decision,
            target=target,
            covered_at_epoch_start=covered_at_start,
        )

        tracker = EpochRewardTracker(
            arm_id=decision.arm_id,
            target=target,
            covered_at_epoch_start=covered_at_start,
        )

        self._active = _ActiveEpoch(
            start=start,
            reward_tracker=tracker,
        )

        return start

    def register_attribution_witnesses(
        self,
        witnesses: Iterable[AttributionWitness],
    ) -> None:
        """
        Register exact intended dependencies for generated template
        instances belonging to the currently active arm.

        Registration itself does not create global Intent or reward.
        """
        if self._active is None:
            raise RuntimeError(
                "cannot register attribution witnesses "
                "without an active epoch"
            )

        witnesses = tuple(witnesses)

        selected_arm = (
            self._active.start.decision.arm_id
        )

        eligible_targets = (
            self._active.reward_tracker
            .attributable_targets
        )

        for witness in witnesses:
            if not isinstance(
                witness,
                AttributionWitness,
            ):
                raise TypeError(
                    "all witnesses must be AttributionWitness"
                )

            if witness.arm_id is not selected_arm:
                raise ValueError(
                    "attribution witness arm does not match "
                    "the active selected arm"
                )

            witness_bin = L2IntentBin(
                distance=witness.distance,
                register=witness.register,
            )

            if witness_bin not in eligible_targets:
                raise ValueError(
                    "attribution witness is outside "
                    "the active arm target set"
                )

        self._attribution.register_many(
            witnesses
        )

    def register_l2_hit(
        self,
        hit: L2Hit,
        *,
        producer: ExecutionEvent,
        consumer: ExecutionEvent,
        expectation: TimingExpectationV1,
        cycle: int,
        wall_ns: int,
    ) -> Tuple[L2ValidationOutcome, ...]:
        """
        Register one live L2 Intent hit.

        Every valid live hit updates global Intent observation.

        Adaptive reward attribution occurs only if the hit exactly
        matches a previously registered template-provenance witness.

        Validated outcome remains irrelevant to reward.
        """
        if self._active is None:
            raise RuntimeError(
                "cannot attribute an L2 hit without an active epoch"
            )

        # Validate bin representation before mutating live coverage.
        intent_bin = self._intent_bin_from_hit(
            hit
        )

        outcomes = self._live.register_hit(
            hit,
            producer=producer,
            consumer=consumer,
            expectation=expectation,
            cycle=cycle,
            wall_ns=wall_ns,
        )

        # Every live hit contributes to global Intent observation.
        self._active.reward_tracker.record_intent_hit(
            intent_bin
        )

        # Reward requires an exact producer/consumer provenance match.
        witness = self._attribution.consume_match(
            hit
        )

        if witness is not None:
            if (
                witness.arm_id
                is not self._active.start.decision.arm_id
            ):
                raise RuntimeError(
                    "matched witness belongs to a different arm"
                )

            self._active.reward_tracker.record_attributable_intent_hit(
                intent_bin
            )

        return outcomes

    def record_architectural_result(
        self,
        *,
        instruction_id: int,
        kind: str,
        passed: bool,
        cycle: int,
        wall_ns: int,
    ) -> Tuple[L2ValidationOutcome, ...]:
        """
        Forward architectural evidence to L2 validation.

        This intentionally does not modify adaptive reward.
        """
        return self._live.record_architectural_result(
            instruction_id=instruction_id,
            kind=kind,
            passed=passed,
            cycle=cycle,
            wall_ns=wall_ns,
        )

    def record_successor_pc(
        self,
        *,
        predecessor_instruction_id: int,
        expected_next_pc: int,
        successor: ExecutionEvent,
        cycle: int,
        wall_ns: int,
    ) -> Tuple[L2ValidationOutcome, ...]:
        """
        Forward next-PC evidence to L2 validation.

        This intentionally does not modify adaptive reward.
        """
        return self._live.record_successor_pc(
            predecessor_instruction_id=(
                predecessor_instruction_id
            ),
            expected_next_pc=expected_next_pc,
            successor=successor,
            cycle=cycle,
            wall_ns=wall_ns,
        )

    def prune_validation_state(
        self,
        *,
        latest_instruction_id: int,
    ) -> None:
        """
        Preserve bounded L2 validation and provenance state.

        Call after all L2 hits for latest_instruction_id have been
        processed.
        """
        self._live.prune(
            latest_instruction_id=latest_instruction_id
        )

        self._attribution.prune(
            latest_instruction_index=latest_instruction_id
        )

    def finish_epoch(
        self,
        *,
        actual_executed_instructions: int,
    ) -> EpochCompletion:
        """
        Finalize reward and update the selected bandit arm.

        The denominator is supplied by the accepted architectural
        execution stream. Nominal batch size is never substituted here.
        """
        if self._active is None:
            raise RuntimeError(
                "cannot finish an epoch when none is active"
            )

        if self._attribution.pending_count != 0:
            raise RuntimeError(
                "cannot finish epoch with unresolved "
                "attribution witnesses"
            )

        active = self._active

        reward_result = (
            active.reward_tracker.finalize(
                actual_executed_instructions=(
                    actual_executed_instructions
                )
            )
        )

        bandit_update = (
            self._decision_engine.update(
                arm_id=active.start.decision.arm_id,
                reward=reward_result.reward,
            )
        )

        completion = EpochCompletion(
            start=active.start,
            reward_result=reward_result,
            bandit_update=bandit_update,
        )

        self._active = None

        return completion
