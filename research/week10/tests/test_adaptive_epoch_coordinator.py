from random import Random

import pytest

from research.week5.impl.coverage_model import (
    D1,
    D2,
    L2CoverageCollector,
    L2Hit,
    l2_bin_index,
)
from research.week5.impl.execution_event import ExecutionEvent
from research.week7.timing_oracle_v1 import TimingExpectationV1
from research.week9.coverage_collector import CoverageCollector

from research.week10.adaptive.decision_engine import (
    BanditConfig,
    BanditDecisionEngine,
)
from research.week10.adaptive.epoch_coordinator import (
    AdaptiveEpochCoordinator,
)
from research.week10.adaptive.register_policy import (
    RegisterTargetPolicy,
)
from research.week10.adaptive.template_library import (
    ArmID,
    Distance,
)
from research.week10.l2_live_coordinator import (
    L2LiveCoordinator,
)


class ControlledDecisionRandom(Random):
    """
    Deterministically selects a requested arm from epoch-zero argmax tie.
    """

    def __init__(self, arm_index):
        super().__init__(0)
        self.arm_index = arm_index

    def random(self):
        # epsilon=0.10 -> exploitation.
        return 0.99

    def choice(self, sequence):
        return sequence[
            self.arm_index % len(sequence)
        ]


def make_event(
    instruction_id,
    *,
    rd=0,
    rs1=0,
    writes_rd=False,
    uses_rs1=False,
    forward_a=0,
):
    return ExecutionEvent(
        instruction_index=instruction_id,
        cycle=instruction_id,
        pc=(instruction_id - 1) * 4,
        instruction=0x00000013,
        rs1=rs1,
        rs2=0,
        rd=rd,
        uses_rs1=uses_rs1,
        uses_rs2=False,
        writes_rd=writes_rd,
        producer_type="ALU_RESULT",
        consumer_type="ALU",
        stall_cycles_before_accept=0,
        forward_a=forward_a,
        forward_b=0,
    )


def make_live_hit(
    register,
    *,
    distance=D1,
    producer_id=1,
):
    consumer_id = producer_id + distance

    producer = make_event(
        producer_id,
        rd=register,
        writes_rd=True,
    )

    forward = (
        0b10
        if distance == D1
        else 0b01
    )

    consumer = make_event(
        consumer_id,
        rs1=register,
        uses_rs1=True,
        forward_a=forward,
    )

    hit = L2Hit(
        bin_index=l2_bin_index(
            distance,
            register,
        ),
        distance=distance,
        register=register,
        producer_instruction_index=producer_id,
        consumer_instruction_index=consumer_id,
        producer_type="ALU_RESULT",
        consumer_type="ALU",
    )

    expectation = TimingExpectationV1(
        instruction_id=consumer.instruction_index,
        pc=consumer.pc,
        instruction=consumer.instruction,
        mnemonic="ADD",
        accept_cycle=consumer.cycle,
        stall_cycles_before_accept=0,
        retire_cycle=consumer.cycle + 3,
        forward_a=forward,
        forward_b=0,
        source_a_producer_id=producer_id,
        source_b_producer_id=None,
        source_a_cycle_age=distance,
        source_b_cycle_age=None,
        redirect=False,
        redirect_bubbles=0,
    )

    return (
        producer,
        consumer,
        hit,
        expectation,
    )


def make_stack(
    *,
    arm_index=0,
    target_seed=20260921,
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

    register_policy = RegisterTargetPolicy(
        Random(target_seed)
    )

    coordinator = AdaptiveEpochCoordinator(
        decision_engine=decision_engine,
        register_policy=register_policy,
        live_coordinator=live,
    )

    return (
        coordinator,
        decision_engine,
        coverage,
        live,
    )


def register_hit(
    coordinator,
    register,
    *,
    distance=D1,
    producer_id=1,
):
    (
        producer,
        consumer,
        hit,
        expectation,
    ) = make_live_hit(
        register,
        distance=distance,
        producer_id=producer_id,
    )

    return coordinator.register_l2_hit(
        hit,
        producer=producer,
        consumer=consumer,
        expectation=expectation,
        cycle=consumer.cycle,
        wall_ns=consumer.cycle,
    )


def test_begin_epoch_selects_arm_and_target():
    coordinator, _, _, _ = make_stack(
        arm_index=0
    )

    start = coordinator.begin_epoch()

    assert coordinator.active
    assert coordinator.current_epoch == start

    assert start.decision.arm_id is ArmID.A0
    assert start.target.d1 is not None
    assert start.target.d2 is None


def test_cannot_begin_overlapping_epoch():
    coordinator, _, _, _ = make_stack()

    coordinator.begin_epoch()

    with pytest.raises(RuntimeError):
        coordinator.begin_epoch()


def test_cannot_finish_without_active_epoch():
    coordinator, _, _, _ = make_stack()

    with pytest.raises(RuntimeError):
        coordinator.finish_epoch(
            actual_executed_instructions=500
        )


def test_cannot_attribute_hit_without_active_epoch():
    coordinator, _, _, _ = make_stack()

    producer, consumer, hit, expectation = (
        make_live_hit(5)
    )

    with pytest.raises(RuntimeError):
        coordinator.register_l2_hit(
            hit,
            producer=producer,
            consumer=consumer,
            expectation=expectation,
            cycle=2,
            wall_ns=2,
        )


def test_attributable_intent_hit_updates_global_coverage_and_reward():
    (
        coordinator,
        _,
        coverage,
        _,
    ) = make_stack(
        arm_index=0
    )

    start = coordinator.begin_epoch()

    register = start.target.d1

    assert register is not None

    register_hit(
        coordinator,
        register,
        distance=D1,
    )

    assert coverage.l2_state[
        ("d1", register)
    ].intent_seen

    completion = coordinator.finish_epoch(
        actual_executed_instructions=500
    )

    assert (
        completion.reward_result
        .attributable_new_count
        == 1
    )

    assert completion.reward_result.reward == pytest.approx(
        2.0
    )


def test_validated_coverage_is_not_required_for_reward():
    (
        coordinator,
        _,
        coverage,
        _,
    ) = make_stack(
        arm_index=0
    )

    start = coordinator.begin_epoch()
    register = start.target.d1

    register_hit(
        coordinator,
        register,
        distance=D1,
    )

    # Architectural results have deliberately not been supplied.
    assert coverage.l2_state[
        ("d1", register)
    ].intent_seen

    assert not coverage.l2_state[
        ("d1", register)
    ].validated_seen

    completion = coordinator.finish_epoch(
        actual_executed_instructions=500
    )

    assert completion.reward_result.reward == pytest.approx(
        2.0
    )


def test_incidental_global_intent_hit_does_not_reward_selected_arm():
    (
        coordinator,
        _,
        coverage,
        _,
    ) = make_stack(
        arm_index=0
    )

    start = coordinator.begin_epoch()

    target = start.target.d1
    assert target is not None

    incidental = (
        1
        if target != 1
        else 2
    )

    register_hit(
        coordinator,
        incidental,
        distance=D1,
    )

    assert coverage.l2_state[
        ("d1", incidental)
    ].intent_seen

    completion = coordinator.finish_epoch(
        actual_executed_instructions=500
    )

    assert (
        completion.reward_result.global_new_count
        == 1
    )

    assert (
        completion.reward_result
        .attributable_new_count
        == 0
    )

    assert completion.reward_result.reward == 0.0


def test_reward_denominator_uses_actual_executed_count():
    coordinator, _, _, _ = make_stack(
        arm_index=0
    )

    start = coordinator.begin_epoch()
    register = start.target.d1

    register_hit(
        coordinator,
        register,
        distance=D1,
    )

    completion = coordinator.finish_epoch(
        actual_executed_instructions=503
    )

    assert completion.reward_result.reward == pytest.approx(
        1000.0 / 503.0
    )


def test_finish_epoch_updates_selected_bandit_arm():
    (
        coordinator,
        engine,
        _,
        _,
    ) = make_stack(
        arm_index=0
    )

    start = coordinator.begin_epoch()

    register_hit(
        coordinator,
        start.target.d1,
        distance=D1,
    )

    completion = coordinator.finish_epoch(
        actual_executed_instructions=500
    )

    assert completion.bandit_update.arm_id is ArmID.A0

    assert completion.bandit_update.reward == pytest.approx(
        2.0
    )

    # alpha = 0.30
    assert engine.q_values()[ArmID.A0] == pytest.approx(
        0.6
    )

    assert engine.pull_counts()[ArmID.A0] == 1

    for arm in ArmID:
        if arm is not ArmID.A0:
            assert engine.pull_counts()[arm] == 0


def test_finish_epoch_clears_active_state():
    coordinator, _, _, _ = make_stack()

    coordinator.begin_epoch()

    coordinator.finish_epoch(
        actual_executed_instructions=500
    )

    assert not coordinator.active
    assert coordinator.current_epoch is None


def test_snapshot_contains_preexisting_intent_not_validated_state():
    (
        coordinator,
        _,
        coverage,
        _,
    ) = make_stack()

    coverage.record_l2_intent(
        "d1",
        5,
        instruction_id=1,
        cycle=1,
        wall_ns=1,
    )

    assert coverage.l2_state[
        ("d1", 5)
    ].intent_seen

    assert not coverage.l2_state[
        ("d1", 5)
    ].validated_seen

    start = coordinator.begin_epoch()

    assert any(
        bin_value.distance is Distance.D1
        and bin_value.register == 5
        for bin_value
        in start.covered_at_epoch_start
    )


def test_already_covered_target_cannot_generate_novelty_reward():
    (
        coordinator,
        _,
        coverage,
        _,
    ) = make_stack(
        arm_index=0
    )

    # Saturate all d1 Intent bins before epoch start.
    for register in range(1, 32):
        coverage.record_l2_intent(
            "d1",
            register,
            instruction_id=register,
            cycle=register,
            wall_ns=register,
        )

    start = coordinator.begin_epoch()

    target = start.target.d1
    assert target is not None

    register_hit(
        coordinator,
        target,
        distance=D1,
        producer_id=100,
    )

    completion = coordinator.finish_epoch(
        actual_executed_instructions=500
    )

    assert (
        completion.reward_result.global_new_count
        == 0
    )

    assert (
        completion.reward_result
        .attributable_new_count
        == 0
    )

    assert completion.reward_result.reward == 0.0


def test_a4_can_receive_two_attributable_new_intent_bins():
    (
        coordinator,
        _,
        _,
        _,
    ) = make_stack(
        arm_index=4
    )

    start = coordinator.begin_epoch()

    assert start.decision.arm_id is ArmID.A4

    d1_register = start.target.d1
    d2_register = start.target.d2

    assert d1_register is not None
    assert d2_register is not None
    assert d1_register != d2_register

    register_hit(
        coordinator,
        d1_register,
        distance=D1,
        producer_id=1,
    )

    register_hit(
        coordinator,
        d2_register,
        distance=D2,
        producer_id=10,
    )

    completion = coordinator.finish_epoch(
        actual_executed_instructions=500
    )

    assert (
        completion.reward_result
        .attributable_new_count
        == 2
    )

    assert completion.reward_result.reward == pytest.approx(
        4.0
    )


def test_nonpositive_actual_execution_count_is_rejected():
    coordinator, _, _, _ = make_stack()

    coordinator.begin_epoch()

    with pytest.raises(ValueError):
        coordinator.finish_epoch(
            actual_executed_instructions=0
        )

    # Failed finalization must not silently start another epoch.
    assert coordinator.active


def test_architectural_evidence_does_not_modify_reward_directly():
    coordinator, _, _, _ = make_stack()

    start = coordinator.begin_epoch()

    coordinator.record_architectural_result(
        instruction_id=100,
        kind="pc",
        passed=False,
        cycle=100,
        wall_ns=100,
    )

    completion = coordinator.finish_epoch(
        actual_executed_instructions=500
    )

    assert completion.reward_result.reward == 0.0
    assert completion.reward_result.global_new_count == 0
    assert start == completion.start


def test_same_seed_and_initial_state_produce_same_epoch_start():
    stack_a = make_stack(
        arm_index=0,
        target_seed=777,
    )

    stack_b = make_stack(
        arm_index=0,
        target_seed=777,
    )

    start_a = stack_a[0].begin_epoch()
    start_b = stack_b[0].begin_epoch()

    assert start_a == start_b
