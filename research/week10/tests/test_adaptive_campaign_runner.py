from random import Random

import pytest

from research.week5.impl.coverage_model import (
    L2CoverageCollector,
)
from research.week9.coverage_collector import (
    CoverageCollector,
)

from research.week10.adaptive.campaign_runner import (
    BoundedProgramRing,
    IMEM_WORD_CAPACITY,
    MAX_STREAM_BLOCK_WORDS,
    AdaptiveEpochStreamPlanner,
    physical_pc_for_logical_word,
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
from research.week10.adaptive.template_library import (
    ArmID,
)
from research.week10.adaptive.template_realizer import (
    TemplateRealizer,
)
from research.week10.l2_live_coordinator import (
    L2LiveCoordinator,
)


class ControlledDecisionRandom(Random):
    def __init__(self, arm_index):
        super().__init__(0)
        self.arm_index = arm_index

    def random(self):
        return 0.99

    def choice(self, sequence):
        return sequence[
            self.arm_index % len(sequence)
        ]


def make_planner(
    *,
    arm_index=0,
    nominal=500,
    decision_seed=0,
    target_seed=20260921,
    realization_seed=20260921,
    initial_logical_word_index=0,
    first_executed_instruction_index=1,
):
    frozen_l2 = L2CoverageCollector()

    coverage = CoverageCollector(
        retain_checkpoints=False
    )

    live = L2LiveCoordinator(
        l2_coverage=frozen_l2,
        coverage=coverage,
    )

    decision_engine = BanditDecisionEngine(
        config=BanditConfig(
            epsilon=0.10,
            alpha=0.30,
            q_floor=0.05,
        ),
        rng=ControlledDecisionRandom(
            arm_index
        ),
    )

    coordinator = AdaptiveEpochCoordinator(
        decision_engine=decision_engine,
        register_policy=RegisterTargetPolicy(
            Random(target_seed)
        ),
        live_coordinator=live,
    )

    planner = AdaptiveEpochStreamPlanner(
        coordinator=coordinator,
        template_realizer=TemplateRealizer(
            Random(realization_seed)
        ),
        filler_scheduler=CampaignFillerScheduler(),
        nominal_epoch_instructions=nominal,
        initial_logical_word_index=(
            initial_logical_word_index
        ),
        first_executed_instruction_index=(
            first_executed_instruction_index
        ),
    )

    return (
        planner,
        coordinator,
        coverage,
    )


def test_physical_pc_wraps_at_128_words():
    assert IMEM_WORD_CAPACITY == 128

    assert physical_pc_for_logical_word(
        0
    ) == 0

    assert physical_pc_for_logical_word(
        127
    ) == 508

    assert physical_pc_for_logical_word(
        128
    ) == 0

    assert physical_pc_for_logical_word(
        129
    ) == 4


def test_planner_requires_active_epoch():
    planner, _, _ = make_planner()

    with pytest.raises(RuntimeError):
        planner.build_next_block()


def test_a0_block_has_two_targeted_words():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=500,
    )

    start = planner.begin_epoch()

    assert start.decision.arm_id is ArmID.A0

    block = planner.build_next_block()

    assert block.arm_id is ArmID.A0
    assert block.targeted_image_word_count == 2
    assert block.template.expected_executed_instruction_count == 2

    assert (
        block.expected_executed_instruction_count
        == 2
    )

    assert block.background_filler_count == 0


def test_filler_schedule_uses_template_image_words():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=500,
    )

    planner.begin_epoch()

    first = planner.build_next_block()
    second = planner.build_next_block()

    assert first.targeted_image_word_count == 2
    assert first.background_filler_count == 0

    assert second.targeted_image_word_count == 2
    assert second.background_filler_count == 1

    assert second.expected_executed_instruction_count == 3


def test_a7_counts_flushed_words_as_targeted_but_not_executed():
    planner, _, _ = make_planner(
        arm_index=7,
        nominal=500,
    )

    start = planner.begin_epoch()

    assert start.decision.arm_id is ArmID.A7

    block = planner.build_next_block()

    assert block.template.image_word_count == 4
    assert (
        block.template.expected_executed_instruction_count
        == 2
    )

    # Four generated targeted words immediately make one background
    # filler due under the frozen cumulative 4:1 scheduler.
    assert block.background_filler_count == 1

    assert block.targeted_image_word_count == 4

    assert (
        block.expected_executed_instruction_count
        == 3
    )

    assert (
        block.expected_executed_word_offsets[:2]
        == (0, 3)
    )

    assert (
        block.expected_executed_word_offsets[-1]
        == 4
    )


def test_block_witness_indices_ignore_a7_flushed_words():
    planner, _, _ = make_planner(
        arm_index=7,
        nominal=500,
        first_executed_instruction_index=100,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    assert len(block.witnesses) == 1

    witness = block.witnesses[0]

    assert (
        witness.producer_instruction_index
        == 100
    )

    assert (
        witness.consumer_instruction_index
        == 101
    )


def test_expected_execution_indices_advance_by_accepted_order():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=500,
        first_executed_instruction_index=10,
    )

    planner.begin_epoch()

    first = planner.build_next_block()
    second = planner.build_next_block()

    assert (
        first.first_executed_instruction_index
        == 10
    )

    assert (
        second.first_executed_instruction_index
        == (
            10
            + first.expected_executed_instruction_count
        )
    )


def test_nominal_epoch_stops_only_after_complete_template_block():
    planner, _, _ = make_planner(
        arm_index=1,
        nominal=5,
    )

    planner.begin_epoch()

    first = planner.build_next_block()

    assert (
        first.expected_executed_instruction_count
        >= 3
    )

    assert not planner.epoch_plan_complete

    second = planner.build_next_block()

    assert planner.epoch_plan_complete

    assert (
        planner.planned_epoch_executed_instructions
        >= 5
    )

    # Overshoot is legal because the second template block is complete.
    assert (
        planner.planned_epoch_executed_instructions
        == (
            first.expected_executed_instruction_count
            + second.expected_executed_instruction_count
        )
    )


def test_no_additional_block_after_nominal_plan_complete():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=2,
    )

    planner.begin_epoch()

    planner.build_next_block()

    assert planner.epoch_plan_complete

    with pytest.raises(RuntimeError):
        planner.build_next_block()


def test_stream_block_wraps_physical_addresses():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=2,
        initial_logical_word_index=127,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    assert block.physical_word_addresses[:2] == (
        508,
        0,
    )


def test_program_ring_enforces_capacity():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=1000,
    )

    planner.begin_epoch()

    ring = BoundedProgramRing(
        capacity_words=MAX_STREAM_BLOCK_WORDS
    )

    first = planner.build_next_block()

    ring.append(first)

    assert ring.used_words == first.image_word_count

    second = planner.build_next_block()

    if second.image_word_count > ring.free_words:
        with pytest.raises(RuntimeError):
            ring.append(second)


def test_program_ring_release_is_fifo():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=1000,
    )

    planner.begin_epoch()

    ring = BoundedProgramRing()

    first = planner.build_next_block()
    second = planner.build_next_block()

    ring.append(first)
    ring.append(second)

    with pytest.raises(RuntimeError):
        ring.release_oldest(
            template_instance_id=(
                second.template_instance_id
            )
        )

    released = ring.release_oldest(
        template_instance_id=(
            first.template_instance_id
        )
    )

    assert released == first

    assert (
        ring.used_words
        == second.image_word_count
    )


def test_registering_committed_block_witnesses_is_explicit():
    planner, coordinator, _ = make_planner(
        arm_index=0,
        nominal=2,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    assert (
        coordinator.pending_attribution_witness_count
        == 0
    )

    planner.register_block_witnesses(
        block
    )

    assert (
        coordinator.pending_attribution_witness_count
        == len(block.witnesses)
    )


def test_same_seed_produces_same_stream_blocks():
    planner_a, _, _ = make_planner(
        arm_index=5,
        nominal=20,
        target_seed=777,
        realization_seed=888,
    )

    planner_b, _, _ = make_planner(
        arm_index=5,
        nominal=20,
        target_seed=777,
        realization_seed=888,
    )

    assert (
        planner_a.begin_epoch()
        == planner_b.begin_epoch()
    )

    blocks_a = []
    blocks_b = []

    while not planner_a.epoch_plan_complete:
        blocks_a.append(
            planner_a.build_next_block()
        )

    while not planner_b.epoch_plan_complete:
        blocks_b.append(
            planner_b.build_next_block()
        )

    assert blocks_a == blocks_b


def test_stream_block_never_exceeds_bounded_maximum():
    for arm_index in range(10):
        planner, _, _ = make_planner(
            arm_index=arm_index,
            nominal=20,
        )

        planner.begin_epoch()

        while not planner.epoch_plan_complete:
            block = planner.build_next_block()

            assert (
                block.image_word_count
                <= MAX_STREAM_BLOCK_WORDS
            )
