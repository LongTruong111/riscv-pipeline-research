from research.week5.impl.coverage_model import (
    L2CoverageCollector,
)
from research.week5.impl.execution_event import ExecutionEvent
from research.week7.timing_oracle_v1 import TimingExpectationV1
from research.week9.coverage_collector import CoverageCollector
from research.week10.l2_live_coordinator import L2LiveCoordinator


def event(
    instruction_id,
    *,
    pc,
    rs1=0,
    rd=0,
    uses_rs1=False,
    writes_rd=False,
    fwd_a=0,
):
    return ExecutionEvent(
        instruction_index=instruction_id,
        cycle=instruction_id,
        pc=pc,
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
        forward_a=fwd_a,
        forward_b=0,
    )


def expectation(consumer):
    return TimingExpectationV1(
        instruction_id=consumer.instruction_index,
        pc=consumer.pc,
        instruction=consumer.instruction,
        mnemonic="ADD",
        accept_cycle=consumer.cycle,
        stall_cycles_before_accept=0,
        retire_cycle=consumer.cycle + 3,
        forward_a=0b10,
        forward_b=0,
        source_a_producer_id=1,
        source_b_producer_id=None,
        source_a_cycle_age=1,
        source_b_cycle_age=None,
        redirect=False,
        redirect_bubbles=0,
    )


def setup_hit():
    frozen = L2CoverageCollector()
    coverage = CoverageCollector(
        retain_checkpoints=False
    )

    producer = event(
        1,
        pc=0,
        rd=5,
        writes_rd=True,
    )

    consumer = event(
        2,
        pc=4,
        rs1=5,
        uses_rs1=True,
        fwd_a=0b10,
    )

    assert frozen.observe(producer) == ()

    hits = frozen.observe(consumer)
    assert len(hits) == 1

    coordinator = L2LiveCoordinator(
        l2_coverage=frozen,
        coverage=coverage,
    )

    return (
        coordinator,
        frozen,
        coverage,
        producer,
        consumer,
        hits[0],
    )


def record_base(
    coordinator,
    instruction_id,
    *,
    cycle,
):
    for kind in (
        "pc",
        "store",
        "writeback",
    ):
        coordinator.record_architectural_result(
            instruction_id=instruction_id,
            kind=kind,
            passed=True,
            cycle=cycle,
            wall_ns=cycle,
        )


def test_validated_hit_promotes_both_collectors():
    (
        coordinator,
        frozen,
        coverage,
        producer,
        consumer,
        hit,
    ) = setup_hit()

    coordinator.register_hit(
        hit,
        producer=producer,
        consumer=consumer,
        expectation=expectation(consumer),
        cycle=2,
        wall_ns=2,
    )

    record_base(coordinator, 1, cycle=3)
    record_base(coordinator, 2, cycle=4)

    coordinator.record_architectural_result(
        instruction_id=1,
        kind="next_pc",
        passed=True,
        cycle=4,
        wall_ns=4,
    )

    outcomes = (
        coordinator.record_architectural_result(
            instruction_id=2,
            kind="next_pc",
            passed=True,
            cycle=5,
            wall_ns=5,
        )
    )

    assert len(outcomes) == 1
    assert outcomes[0].validated

    assert frozen.validated_bins == 1

    state = coverage.l2_state[
        ("d1", 5)
    ]

    assert state.intent_seen
    assert state.validated_seen


def test_failed_architecture_does_not_promote():
    (
        coordinator,
        frozen,
        coverage,
        producer,
        consumer,
        hit,
    ) = setup_hit()

    coordinator.register_hit(
        hit,
        producer=producer,
        consumer=consumer,
        expectation=expectation(consumer),
        cycle=2,
        wall_ns=2,
    )

    record_base(coordinator, 1, cycle=3)

    coordinator.record_architectural_result(
        instruction_id=2,
        kind="pc",
        passed=True,
        cycle=4,
        wall_ns=4,
    )

    coordinator.record_architectural_result(
        instruction_id=2,
        kind="store",
        passed=True,
        cycle=4,
        wall_ns=4,
    )

    coordinator.record_architectural_result(
        instruction_id=2,
        kind="writeback",
        passed=False,
        cycle=4,
        wall_ns=4,
    )

    coordinator.record_architectural_result(
        instruction_id=1,
        kind="next_pc",
        passed=True,
        cycle=4,
        wall_ns=4,
    )

    outcomes = (
        coordinator.record_architectural_result(
            instruction_id=2,
            kind="next_pc",
            passed=True,
            cycle=5,
            wall_ns=5,
        )
    )

    assert len(outcomes) == 1
    assert not outcomes[0].validated
    assert frozen.validated_bins == 0

    assert not coverage.l2_state[
        ("d1", 5)
    ].validated_seen


def test_successor_pc_is_not_truncated():
    (
        coordinator,
        _,
        _,
        _,
        _,
        _,
    ) = setup_hit()

    successor = event(
        2,
        pc=0,
    )

    outcomes = coordinator.record_successor_pc(
        predecessor_instruction_id=1,
        expected_next_pc=0x200,
        successor=successor,
        cycle=2,
        wall_ns=2,
    )

    assert outcomes == ()


def test_pending_state_prunes_to_constant_window():
    coordinator, *_ = setup_hit()

    for instruction_id in range(1, 100):
        coordinator.record_architectural_result(
            instruction_id=instruction_id,
            kind="pc",
            passed=True,
            cycle=instruction_id,
            wall_ns=instruction_id,
        )

        coordinator.prune(
            latest_instruction_id=instruction_id
        )

    assert (
        coordinator.architectural_cache_entries
        <= 6
    )
