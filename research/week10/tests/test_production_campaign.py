import pytest

from research.week9.coverage_collector import (
    CoverageCheckpoint,
)
from research.week10.adaptive.production_campaign import (
    ENGINEERING_ALPHA,
    ENGINEERING_CHECKPOINT_INTERVAL,
    ENGINEERING_EPSILON,
    ENGINEERING_INSTRUCTION_BUDGET,
    ENGINEERING_NOMINAL_BATCH,
    ENGINEERING_Q_FLOOR,
    ENGINEERING_SEED,
    ProductionCampaignConfig,
    build_production_adaptive_stack,
)


def test_engineering_config_is_frozen():
    config = ProductionCampaignConfig()

    assert config.seed == 20260921
    assert config.epsilon == 0.10
    assert config.alpha == 0.30
    assert config.q_floor == 0.05

    assert config.nominal_batch == 500
    assert config.instruction_budget == 5000
    assert config.checkpoint_interval == 1000

    assert config.seed == ENGINEERING_SEED
    assert config.epsilon == ENGINEERING_EPSILON
    assert config.alpha == ENGINEERING_ALPHA
    assert config.q_floor == ENGINEERING_Q_FLOOR

    assert (
        config.nominal_batch
        == ENGINEERING_NOMINAL_BATCH
    )

    assert (
        config.instruction_budget
        == ENGINEERING_INSTRUCTION_BUDGET
    )

    assert (
        config.checkpoint_interval
        == ENGINEERING_CHECKPOINT_INTERVAL
    )


def test_production_stack_uses_frozen_seed_partition():
    stack = build_production_adaptive_stack()

    assert (
        stack.rngs.seeds.root_seed
        == 20260921
    )

    assert (
        stack.rngs.seeds.decision_seed
        == 16680843080276206783
    )

    assert (
        stack.rngs.seeds.target_seed
        == 1163466188706097826
    )

    assert (
        stack.rngs.seeds.realization_seed
        == 7717841318315519387
    )

    assert (
        stack.rngs.decision_rng
        is not stack.rngs.target_rng
    )

    assert (
        stack.rngs.decision_rng
        is not stack.rngs.realization_rng
    )

    assert (
        stack.rngs.target_rng
        is not stack.rngs.realization_rng
    )


def test_production_stack_uses_o1_telemetry_retention():
    stack = build_production_adaptive_stack()

    assert not stack.coverage.retain_checkpoints
    assert not stack.telemetry.retain_records

    assert stack.coverage.checkpoints == []

    assert stack.telemetry.epoch_records == ()
    assert stack.telemetry.checkpoint_records == ()
    assert stack.telemetry.summary is None


def test_checkpoint_bridge_requires_active_epoch():
    stack = build_production_adaptive_stack()

    checkpoint = CoverageCheckpoint(
        executed_instructions=1000,
        cycle=1200,
        l1_intent_count=0,
        l1_validated_count=0,
        l2_intent_count=0,
        l2_validated_count=0,
    )

    with pytest.raises(
        RuntimeError,
        match="without an active adaptive epoch",
    ):
        stack.checkpoint_bridge(
            checkpoint
        )


def test_checkpoint_bridge_streams_without_retention():
    streamed = []

    stack = build_production_adaptive_stack(
        checkpoint_sink=streamed.append,
    )

    start = stack.planner.begin_epoch()

    epoch_index = (
        start.decision.epoch_index
    )

    stack.checkpoint_bridge.begin_epoch(
        epoch_index
    )

    checkpoint = CoverageCheckpoint(
        executed_instructions=1000,
        cycle=1234,
        l1_intent_count=3,
        l1_validated_count=2,
        l2_intent_count=7,
        l2_validated_count=6,
    )

    stack.checkpoint_bridge(
        checkpoint
    )

    assert len(streamed) == 1

    record = streamed[0]

    assert (
        record.executed_instructions
        == 1000
    )

    assert record.cycle == 1234
    assert record.epoch_index == epoch_index

    assert record.l1_intent_count == 3
    assert record.l1_validated_count == 2

    assert record.l2_intent_count == 7
    assert record.l2_validated_count == 6

    assert (
        stack.telemetry.checkpoint_records
        == ()
    )

    stack.checkpoint_bridge.finish_epoch(
        epoch_index
    )


def test_same_root_seed_reproduces_initial_epoch_and_block():
    first = build_production_adaptive_stack()
    second = build_production_adaptive_stack()

    first_start = (
        first.planner.begin_epoch()
    )

    second_start = (
        second.planner.begin_epoch()
    )

    assert (
        first_start.decision
        == second_start.decision
    )

    assert (
        first_start.target
        == second_start.target
    )

    first_block = (
        first.planner.build_next_block()
    )

    second_block = (
        second.planner.build_next_block()
    )

    assert first_block == second_block


@pytest.mark.parametrize(
    "field,value",
    (
        ("nominal_batch", 0),
        ("instruction_budget", 0),
        ("checkpoint_interval", 0),
    ),
)
def test_production_config_rejects_nonpositive_counts(
    field,
    value,
):
    kwargs = {
        field: value,
    }

    with pytest.raises(
        ValueError,
        match="must be a positive integer",
    ):
        ProductionCampaignConfig(
            **kwargs
        )
