from random import Random

import pytest

from research.week5.impl.execution_event import (
    ExecutionEvent,
)
from research.week5.impl.coverage_model import (
    L2CoverageCollector,
)
from research.week9.coverage_collector import (
    CoverageCollector,
)
from research.week10.adaptive.campaign_runner import (
    AcceptedStreamTracker,
    AdaptiveEpochStreamPlanner,
    BoundedProgramRing,
    IMEM_WORD_CAPACITY,
    MAX_STREAM_BLOCK_WORDS,
    StreamExecutionMismatch,
    physical_pc_for_logical_word,
    ReleasedStreamBlock,
    RuntimeStreamWindow,
    EBD_WORD,
    PlannedBoundaryDelimiter,
    StreamEntry,
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

def test_ebd_encoding_is_frozen():
    assert EBD_WORD == 0x00001263


def test_planned_ebd_has_exact_single_word_semantics():
    delimiter = PlannedBoundaryDelimiter(
        epoch_index=3,
        logical_word_index=129,
        first_executed_instruction_index=700,
    )

    assert delimiter.epoch_index == 3
    assert delimiter.word == EBD_WORD

    assert delimiter.logical_word_start == 129
    assert delimiter.logical_word_end_exclusive == 130

    assert delimiter.image_words == (
        EBD_WORD,
    )

    assert delimiter.image_word_count == 1

    # Logical word 129 wraps physically to word 1 -> PC 4.
    assert delimiter.physical_word_addresses == (
        4,
    )

    assert delimiter.expected_executed_word_offsets == (
        0,
    )

    assert delimiter.expected_executed_pcs == (
        4,
    )

    assert delimiter.expected_executed_words == (
        EBD_WORD,
    )

    assert (
        delimiter.expected_executed_instruction_count
        == 1
    )

    assert delimiter.witnesses == ()


@pytest.mark.parametrize(
    "kwargs",
    (
        {
            "epoch_index": -1,
            "logical_word_index": 0,
            "first_executed_instruction_index": 1,
        },
        {
            "epoch_index": 0,
            "logical_word_index": -1,
            "first_executed_instruction_index": 1,
        },
        {
            "epoch_index": 0,
            "logical_word_index": 0,
            "first_executed_instruction_index": 0,
        },
    ),
)
def test_planned_ebd_rejects_invalid_indices(
    kwargs,
):
    with pytest.raises(ValueError):
        PlannedBoundaryDelimiter(
            **kwargs
        )


def test_planned_ebd_rejects_nonfrozen_word():
    with pytest.raises(ValueError):
        PlannedBoundaryDelimiter(
            epoch_index=0,
            logical_word_index=0,
            first_executed_instruction_index=1,
            word=0x00000013,
        )


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
def test_ebd_stream_entry_key_is_namespaced():
    delimiter = PlannedBoundaryDelimiter(
        epoch_index=4,
        logical_word_index=20,
        first_executed_instruction_index=30,
    )

    assert delimiter.stream_entry_key == (
        "EBD",
        4,
    )


def test_template_stream_entry_key_is_namespaced():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=2,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    assert block.stream_entry_key == (
        "TEMPLATE",
        block.template_instance_id,
    )


def test_ebd_and_template_keys_cannot_alias():
    delimiter = PlannedBoundaryDelimiter(
        epoch_index=1,
        logical_word_index=0,
        first_executed_instruction_index=1,
    )

    planner, _, _ = make_planner(
        arm_index=0,
        nominal=2,
        initial_logical_word_index=1,
        first_executed_instruction_index=2,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    assert (
        delimiter.stream_entry_key
        != block.stream_entry_key
    )
def make_execution_event(
    *,
    instruction_index,
    pc,
    instruction,
):
    return ExecutionEvent(
        instruction_index=instruction_index,
        cycle=instruction_index,
        pc=pc,
        instruction=instruction,
        rs1=0,
        rs2=0,
        rd=0,
        uses_rs1=False,
        uses_rs2=False,
        writes_rd=False,
        producer_type="NONE",
        consumer_type="NONE",
        stall_cycles_before_accept=0,
        forward_a=0,
        forward_b=0,
    )
def test_program_ring_accepts_ebd_then_template():
    delimiter = PlannedBoundaryDelimiter(
        epoch_index=0,
        logical_word_index=0,
        first_executed_instruction_index=1,
    )

    planner, _, _ = make_planner(
        arm_index=0,
        nominal=2,
        initial_logical_word_index=1,
        first_executed_instruction_index=2,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    ring = BoundedProgramRing()

    ring.append(
        delimiter
    )

    ring.append(
        block
    )

    assert ring.used_words == (
        1
        + block.image_word_count
    )

    assert ring.entries == (
        delimiter,
        block,
    )

    released = ring.release_oldest(
        stream_entry_key=(
            delimiter.stream_entry_key
        )
    )

    assert released == delimiter

    assert ring.used_words == (
        block.image_word_count
    )

    assert ring.entries == (
        block,
    )
def test_accepted_tracker_consumes_ebd_then_template():
    delimiter = PlannedBoundaryDelimiter(
        epoch_index=0,
        logical_word_index=0,
        first_executed_instruction_index=1,
    )

    planner, _, _ = make_planner(
        arm_index=0,
        nominal=2,
        initial_logical_word_index=1,
        first_executed_instruction_index=2,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    tracker = AcceptedStreamTracker(
        first_expected_instruction_index=1
    )

    tracker.enqueue(
        delimiter
    )

    tracker.enqueue(
        block
    )

    completed = tracker.observe(
        make_execution_event(
            instruction_index=1,
            pc=delimiter.expected_executed_pcs[0],
            instruction=EBD_WORD,
        )
    )

    assert completed is not None

    assert (
        completed.stream_entry_key
        == delimiter.stream_entry_key
    )

    assert tracker.accepted_count == 1

    next_index = 2
    completed = None

    for pc, word in zip(
        block.expected_executed_pcs,
        block.expected_executed_words,
    ):
        completed = tracker.observe(
            make_execution_event(
                instruction_index=next_index,
                pc=pc,
                instruction=word,
            )
        )

        next_index += 1

    assert completed is not None

    assert (
        completed.stream_entry_key
        == block.stream_entry_key
    )

    assert (
        completed.template_instance_id
        == block.template_instance_id
    )

    assert tracker.pending_block_count == 0
def test_runtime_window_ebd_has_zero_attribution_witnesses():
    delimiter = PlannedBoundaryDelimiter(
        epoch_index=0,
        logical_word_index=0,
        first_executed_instruction_index=1,
    )

    planner, coordinator, _ = make_planner(
        arm_index=0,
        nominal=2,
        initial_logical_word_index=1,
        first_executed_instruction_index=2,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    window = RuntimeStreamWindow(
        coordinator=coordinator,
        ring=BoundedProgramRing(),
        accepted_tracker=AcceptedStreamTracker(
            first_expected_instruction_index=1
        ),
    )

    assert (
        coordinator.pending_attribution_witness_count
        == 0
    )

    window.commit_patched_block(
        delimiter
    )

    assert (
        coordinator.pending_attribution_witness_count
        == 0
    )

    window.commit_patched_block(
        block
    )

    assert (
        coordinator.pending_attribution_witness_count
        == len(block.witnesses)
    )

    assert window.pending_block_count == 2

    assert window.used_words == (
        1
        + block.image_word_count
    )

    released = window.finalize_accepted_event(
        make_execution_event(
            instruction_index=1,
            pc=delimiter.expected_executed_pcs[0],
            instruction=EBD_WORD,
        )
    )

    assert released is not None

    assert released.block == delimiter

    assert (
        released.accepted.stream_entry_key
        == delimiter.stream_entry_key
    )

    assert window.pending_block_count == 1

    assert window.used_words == (
        block.image_word_count
    )
def test_accepted_tracker_consumes_exact_block():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=2,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    tracker = AcceptedStreamTracker(
        first_expected_instruction_index=1
    )

    tracker.enqueue(block)

    for offset, (
        pc,
        word,
    ) in enumerate(
        zip(
            block.expected_executed_pcs,
            block.expected_executed_words,
        )
    ):
        result = tracker.observe(
            make_execution_event(
                instruction_index=1 + offset,
                pc=pc,
                instruction=word,
            )
        )

        if (
            offset
            < block.expected_executed_instruction_count - 1
        ):
            assert result is None

    assert result is not None

    assert (
        result.template_instance_id
        == block.template_instance_id
    )

    assert (
        result.accepted_instruction_count
        == block.expected_executed_instruction_count
    )

    assert tracker.accepted_count == 2
    assert tracker.pending_block_count == 0


def test_accepted_tracker_rejects_wrong_instruction_index():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=2,
    )

    planner.begin_epoch()
    block = planner.build_next_block()

    tracker = AcceptedStreamTracker()
    tracker.enqueue(block)

    with pytest.raises(
        StreamExecutionMismatch
    ):
        tracker.observe(
            make_execution_event(
                instruction_index=2,
                pc=block.expected_executed_pcs[0],
                instruction=(
                    block.expected_executed_words[0]
                ),
            )
        )


def test_accepted_tracker_rejects_wrong_pc():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=2,
    )

    planner.begin_epoch()
    block = planner.build_next_block()

    tracker = AcceptedStreamTracker()
    tracker.enqueue(block)

    with pytest.raises(
        StreamExecutionMismatch
    ):
        tracker.observe(
            make_execution_event(
                instruction_index=1,
                pc=4,
                instruction=(
                    block.expected_executed_words[0]
                ),
            )
        )


def test_accepted_tracker_rejects_wrong_word():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=2,
    )

    planner.begin_epoch()
    block = planner.build_next_block()

    tracker = AcceptedStreamTracker()
    tracker.enqueue(block)

    with pytest.raises(
        StreamExecutionMismatch
    ):
        tracker.observe(
            make_execution_event(
                instruction_index=1,
                pc=block.expected_executed_pcs[0],
                instruction=0xFFFFFFFF,
            )
        )


def test_a7_tracker_skips_flushed_image_words():
    planner, _, _ = make_planner(
        arm_index=7,
        nominal=3,
        first_executed_instruction_index=10,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    assert (
        block.expected_executed_word_offsets
        == (0, 3, 4)
    )

    tracker = AcceptedStreamTracker(
        first_expected_instruction_index=10
    )

    tracker.enqueue(block)

    events = [
        make_execution_event(
            instruction_index=10 + offset,
            pc=pc,
            instruction=word,
        )
        for offset, (
            pc,
            word,
        ) in enumerate(
            zip(
                block.expected_executed_pcs,
                block.expected_executed_words,
            )
        )
    ]

    assert tracker.observe(events[0]) is None
    assert tracker.observe(events[1]) is None

    completed = tracker.observe(
        events[2]
    )

    assert completed is not None
    assert completed.accepted_instruction_count == 3

    assert tracker.accepted_count == 3


def test_tracker_handles_physical_pc_wrap():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=2,
        initial_logical_word_index=127,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    assert block.expected_executed_pcs == (
        508,
        0,
    )

    tracker = AcceptedStreamTracker()
    tracker.enqueue(block)

    assert tracker.observe(
        make_execution_event(
            instruction_index=1,
            pc=508,
            instruction=(
                block.expected_executed_words[0]
            ),
        )
    ) is None

    completed = tracker.observe(
        make_execution_event(
            instruction_index=2,
            pc=0,
            instruction=(
                block.expected_executed_words[1]
            ),
        )
    )

    assert completed is not None


def test_tracker_consumes_multiple_blocks_contiguously():
    planner, _, _ = make_planner(
        arm_index=0,
        nominal=5,
    )

    planner.begin_epoch()

    first = planner.build_next_block()
    second = planner.build_next_block()

    tracker = AcceptedStreamTracker()

    tracker.enqueue(first)
    tracker.enqueue(second)

    next_index = 1
    completed_ids = []

    for block in (
        first,
        second,
    ):
        for pc, word in zip(
            block.expected_executed_pcs,
            block.expected_executed_words,
        ):
            completed = tracker.observe(
                make_execution_event(
                    instruction_index=next_index,
                    pc=pc,
                    instruction=word,
                )
            )

            next_index += 1

            if completed is not None:
                completed_ids.append(
                    completed.template_instance_id
                )

    assert completed_ids == [
        first.template_instance_id,
        second.template_instance_id,
    ]

    assert (
        tracker.accepted_count
        == (
            first.expected_executed_instruction_count
            + second.expected_executed_instruction_count
        )
    )

    assert tracker.pending_block_count == 0

def test_runtime_window_commit_registers_block_and_witnesses():
    planner, coordinator, _ = make_planner(
        arm_index=0,
        nominal=2,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    ring = BoundedProgramRing()

    tracker = AcceptedStreamTracker()

    window = RuntimeStreamWindow(
        coordinator=coordinator,
        ring=ring,
        accepted_tracker=tracker,
    )

    assert (
        coordinator.pending_attribution_witness_count
        == 0
    )

    window.commit_patched_block(
        block
    )

    assert window.pending_block_count == 1

    assert (
        window.used_words
        == block.image_word_count
    )

    assert (
        coordinator.pending_attribution_witness_count
        == len(block.witnesses)
    )


def test_runtime_window_releases_only_after_complete_block():
    planner, coordinator, _ = make_planner(
        arm_index=0,
        nominal=2,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    window = RuntimeStreamWindow(
        coordinator=coordinator,
        ring=BoundedProgramRing(),
        accepted_tracker=AcceptedStreamTracker(),
    )

    window.commit_patched_block(
        block
    )

    first = make_execution_event(
        instruction_index=1,
        pc=block.expected_executed_pcs[0],
        instruction=(
            block.expected_executed_words[0]
        ),
    )

    second = make_execution_event(
        instruction_index=2,
        pc=block.expected_executed_pcs[1],
        instruction=(
            block.expected_executed_words[1]
        ),
    )

    released = window.finalize_accepted_event(
        first
    )

    assert released is None
    assert window.pending_block_count == 1

    released = window.finalize_accepted_event(
        second
    )

    assert isinstance(
        released,
        ReleasedStreamBlock,
    )

    assert (
        released.block.template_instance_id
        == block.template_instance_id
    )

    assert window.pending_block_count == 0
    assert window.used_words == 0


def test_runtime_window_prunes_unmatched_witness_on_consumer():
    planner, coordinator, _ = make_planner(
        arm_index=0,
        nominal=2,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    window = RuntimeStreamWindow(
        coordinator=coordinator,
        ring=BoundedProgramRing(),
        accepted_tracker=AcceptedStreamTracker(),
    )

    window.commit_patched_block(
        block
    )

    assert (
        coordinator.pending_attribution_witness_count
        == 1
    )

    for index, (
        pc,
        word,
    ) in enumerate(
        zip(
            block.expected_executed_pcs,
            block.expected_executed_words,
        ),
        start=1,
    ):
        window.finalize_accepted_event(
            make_execution_event(
                instruction_index=index,
                pc=pc,
                instruction=word,
            )
        )

    # No L2 hit was registered, so the witness becomes stale when the
    # consumer instruction has been completely processed.
    assert (
        coordinator.pending_attribution_witness_count
        == 0
    )


def test_runtime_window_a7_release_ignores_flushed_words():
    planner, coordinator, _ = make_planner(
        arm_index=7,
        nominal=3,
    )

    planner.begin_epoch()

    block = planner.build_next_block()

    assert (
        block.expected_executed_word_offsets
        == (0, 3, 4)
    )

    window = RuntimeStreamWindow(
        coordinator=coordinator,
        ring=BoundedProgramRing(),
        accepted_tracker=AcceptedStreamTracker(),
    )

    window.commit_patched_block(
        block
    )

    released = None

    for instruction_index, (
        pc,
        word,
    ) in enumerate(
        zip(
            block.expected_executed_pcs,
            block.expected_executed_words,
        ),
        start=1,
    ):
        released = (
            window.finalize_accepted_event(
                make_execution_event(
                    instruction_index=(
                        instruction_index
                    ),
                    pc=pc,
                    instruction=word,
                )
            )
        )

    assert released is not None

    assert (
        released.accepted.accepted_instruction_count
        == 3
    )

    assert window.pending_block_count == 0


def test_runtime_window_capacity_failure_does_not_register_witnesses():
    planner, coordinator, _ = make_planner(
        arm_index=0,
        nominal=5,
    )

    planner.begin_epoch()

    first = planner.build_next_block()
    second = planner.build_next_block()

    ring = BoundedProgramRing(
        capacity_words=(
            first.image_word_count
        )
    )

    window = RuntimeStreamWindow(
        coordinator=coordinator,
        ring=ring,
        accepted_tracker=AcceptedStreamTracker(),
    )

    window.commit_patched_block(
        first
    )

    witness_count_before = (
        coordinator
        .pending_attribution_witness_count
    )

    with pytest.raises(RuntimeError):
        window.commit_patched_block(
            second
        )

    assert (
        coordinator.pending_attribution_witness_count
        == witness_count_before
    )

    assert window.pending_block_count == 1


def test_runtime_window_refill_after_release():
    planner, coordinator, _ = make_planner(
        arm_index=0,
        nominal=5,
    )

    planner.begin_epoch()

    first = planner.build_next_block()
    second = planner.build_next_block()

    ring = BoundedProgramRing(
        capacity_words=max(
            first.image_word_count,
            second.image_word_count,
        )
    )

    window = RuntimeStreamWindow(
        coordinator=coordinator,
        ring=ring,
        accepted_tracker=AcceptedStreamTracker(),
    )

    window.commit_patched_block(
        first
    )

    with pytest.raises(RuntimeError):
        window.commit_patched_block(
            second
        )

    next_index = (
        first.first_executed_instruction_index
    )

    released = None

    for pc, word in zip(
        first.expected_executed_pcs,
        first.expected_executed_words,
    ):
        released = (
            window.finalize_accepted_event(
                make_execution_event(
                    instruction_index=next_index,
                    pc=pc,
                    instruction=word,
                )
            )
        )

        next_index += 1

    assert released is not None

    assert window.used_words == 0

    # The same physical capacity is now reclaimable.
    window.commit_patched_block(
        second
    )

    assert window.pending_block_count == 1

    assert (
        window.used_words
        == second.image_word_count
    )
