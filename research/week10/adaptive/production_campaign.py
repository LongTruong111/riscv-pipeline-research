from __future__ import annotations

from dataclasses import dataclass

from research.week5.impl.coverage_model import (
    L2CoverageCollector,
)
from research.week9.coverage_collector import (
    CoverageCheckpoint,
    CoverageCollector,
)
from research.week10.l2_live_coordinator import (
    L2LiveCoordinator,
)

from research.week10.adaptive.campaign_runner import (
    AcceptedStreamTracker,
    AdaptiveEpochStreamPlanner,
    BoundedProgramRing,
    RuntimeStreamWindow,
)
from research.week10.adaptive.campaign_seed import (
    CampaignRngs,
    build_campaign_rngs,
)
from research.week10.adaptive.campaign_telemetry import (
    CampaignTelemetryRecorder,
)
from research.week10.adaptive.decision_engine import (
    BanditConfig,
    BanditDecisionEngine,
)
from research.week10.adaptive.epoch_coordinator import (
    AdaptiveEpochCoordinator,
)
from research.week10.adaptive.filler_policy import (
    CampaignFillerScheduler,
)
from research.week10.adaptive.register_policy import (
    RegisterTargetPolicy,
)
from research.week10.adaptive.template_realizer import (
    TemplateRealizer,
)


ENGINEERING_SEED = 20260921
ENGINEERING_EPSILON = 0.10
ENGINEERING_ALPHA = 0.30
ENGINEERING_Q_FLOOR = 0.05
ENGINEERING_NOMINAL_BATCH = 500
ENGINEERING_INSTRUCTION_BUDGET = 5000
ENGINEERING_CHECKPOINT_INTERVAL = 1000


@dataclass(frozen=True)
class ProductionCampaignConfig:
    seed: int = ENGINEERING_SEED

    epsilon: float = ENGINEERING_EPSILON
    alpha: float = ENGINEERING_ALPHA
    q_floor: float = ENGINEERING_Q_FLOOR

    nominal_batch: int = ENGINEERING_NOMINAL_BATCH
    instruction_budget: int = (
        ENGINEERING_INSTRUCTION_BUDGET
    )

    checkpoint_interval: int = (
        ENGINEERING_CHECKPOINT_INTERVAL
    )

    def __post_init__(self) -> None:
        if (
            isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
        ):
            raise ValueError(
                "seed must be an integer"
            )

        if not 0.0 <= self.epsilon <= 1.0:
            raise ValueError(
                "epsilon must be in [0, 1]"
            )

        if not 0.0 < self.alpha <= 1.0:
            raise ValueError(
                "alpha must be in (0, 1]"
            )

        if self.q_floor < 0.0:
            raise ValueError(
                "q_floor must be non-negative"
            )

        for name, value in (
            (
                "nominal_batch",
                self.nominal_batch,
            ),
            (
                "instruction_budget",
                self.instruction_budget,
            ),
            (
                "checkpoint_interval",
                self.checkpoint_interval,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be a positive integer"
                )


class CheckpointTelemetryBridge:
    """
    Bridge CoverageCollector's synchronous checkpoint emission into
    CampaignTelemetryRecorder.

    A checkpoint occurs during the post-instruction consistent cut and
    therefore belongs to the adaptive epoch that is active at that
    accepted instruction.

    Retained state is O(1) with respect to campaign length.
    """

    def __init__(
        self,
        *,
        telemetry: CampaignTelemetryRecorder,
        decision_state: BanditDecisionEngine,
    ) -> None:
        self._telemetry = telemetry
        self._decision_state = decision_state

        self._active_epoch_index: int | None = None

    @property
    def active_epoch_index(
        self,
    ) -> int | None:
        return self._active_epoch_index

    def begin_epoch(
        self,
        epoch_index: int,
    ) -> None:
        if (
            isinstance(epoch_index, bool)
            or not isinstance(epoch_index, int)
            or epoch_index < 0
        ):
            raise ValueError(
                "epoch_index must be a non-negative integer"
            )

        if self._active_epoch_index is not None:
            raise RuntimeError(
                "checkpoint bridge already has an active epoch"
            )

        self._active_epoch_index = epoch_index

    def finish_epoch(
        self,
        epoch_index: int,
    ) -> None:
        if self._active_epoch_index != epoch_index:
            raise RuntimeError(
                "checkpoint bridge epoch close mismatch"
            )

        self._active_epoch_index = None

    def __call__(
        self,
        checkpoint: CoverageCheckpoint,
    ) -> None:
        if self._active_epoch_index is None:
            raise RuntimeError(
                "coverage checkpoint emitted without "
                "an active adaptive epoch"
            )

        self._telemetry.record_checkpoint(
            checkpoint,
            epoch_index=self._active_epoch_index,
            decision_state=self._decision_state,
        )


@dataclass(frozen=True)
class ProductionAdaptiveStack:
    config: ProductionCampaignConfig

    rngs: CampaignRngs

    l2_coverage: L2CoverageCollector
    coverage: CoverageCollector

    decision_engine: BanditDecisionEngine
    coordinator: AdaptiveEpochCoordinator

    planner: AdaptiveEpochStreamPlanner
    window: RuntimeStreamWindow

    telemetry: CampaignTelemetryRecorder
    checkpoint_bridge: CheckpointTelemetryBridge


def build_production_adaptive_stack(
    *,
    config: ProductionCampaignConfig | None = None,
    epoch_sink=None,
    checkpoint_sink=None,
    summary_sink=None,
) -> ProductionAdaptiveStack:
    """
    Build one independent production Adaptive-CGS campaign state.

    Frozen RNG ownership:

      decision_rng:
        epsilon draw, exploration arm, max-Q ties, q-floor fallback

      target_rng:
        register targeting and A4 pair ties

      realization_rng:
        stochastic template variants

    Filler and EBD consume no RNG state.

    Production telemetry retains no campaign-length history in RAM.
    """

    if config is None:
        config = ProductionCampaignConfig()

    if not isinstance(
        config,
        ProductionCampaignConfig,
    ):
        raise TypeError(
            "config must be ProductionCampaignConfig"
        )

    rngs = build_campaign_rngs(
        config.seed
    )

    l2_coverage = L2CoverageCollector()

    # Sink is attached after telemetry/decision state exist.
    coverage = CoverageCollector(
        checkpoint_interval=(
            config.checkpoint_interval
        ),
        retain_checkpoints=False,
    )

    live = L2LiveCoordinator(
        l2_coverage=l2_coverage,
        coverage=coverage,
    )

    decision_engine = BanditDecisionEngine(
        config=BanditConfig(
            epsilon=config.epsilon,
            alpha=config.alpha,
            q_floor=config.q_floor,
        ),
        rng=rngs.decision_rng,
    )

    coordinator = AdaptiveEpochCoordinator(
        decision_engine=decision_engine,
        register_policy=RegisterTargetPolicy(
            rngs.target_rng
        ),
        live_coordinator=live,
    )

    planner = AdaptiveEpochStreamPlanner(
        coordinator=coordinator,
        template_realizer=TemplateRealizer(
            rngs.realization_rng
        ),
        filler_scheduler=CampaignFillerScheduler(),
        nominal_epoch_instructions=(
            config.nominal_batch
        ),
        initial_logical_word_index=0,
        first_executed_instruction_index=1,
    )

    ring = BoundedProgramRing()

    accepted_tracker = AcceptedStreamTracker(
        first_expected_instruction_index=1
    )

    window = RuntimeStreamWindow(
        coordinator=coordinator,
        ring=ring,
        accepted_tracker=accepted_tracker,
    )

    telemetry = CampaignTelemetryRecorder(
        seed=config.seed,
        epsilon=config.epsilon,
        alpha=config.alpha,
        q_floor=config.q_floor,
        nominal_batch=config.nominal_batch,
        instruction_budget=(
            config.instruction_budget
        ),
        retain_records=False,
        epoch_sink=epoch_sink,
        checkpoint_sink=checkpoint_sink,
        summary_sink=summary_sink,
    )

    checkpoint_bridge = CheckpointTelemetryBridge(
        telemetry=telemetry,
        decision_state=decision_engine,
    )

    coverage.checkpoint_sink = (
        checkpoint_bridge
    )

    return ProductionAdaptiveStack(
        config=config,
        rngs=rngs,
        l2_coverage=l2_coverage,
        coverage=coverage,
        decision_engine=decision_engine,
        coordinator=coordinator,
        planner=planner,
        window=window,
        telemetry=telemetry,
        checkpoint_bridge=checkpoint_bridge,
    )
