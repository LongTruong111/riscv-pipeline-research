import pytest

from research.week5.impl.coverage_model import (
    L2Hit,
    l2_bin_index,
)
from research.week5.impl.execution_event import ExecutionEvent
from research.week7.timing_oracle_v1 import TimingExpectationV1
from research.week10.l2_realization import (
    L2ValidatedCoverageChecker,
    check_l2_source_control,
)


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


def hit(
    *,
    producer_id=1,
    consumer_id=2,
    distance=1,
    register=5,
):
    return L2Hit(
        bin_index=l2_bin_index(distance, register),
        distance=distance,
        register=register,
        producer_instruction_index=producer_id,
        consumer_instruction_index=consumer_id,
        producer_type="ALU_RESULT",
        consumer_type="ALU",
    )


def expectation(
    consumer,
    *,
    instruction_id=None,
    source_a=1,
):
    if instruction_id is None:
        instruction_id = consumer.instruction_index

    return TimingExpectationV1(
        instruction_id=instruction_id,
        pc=consumer.pc,
        instruction=consumer.instruction,
        mnemonic="ADD",
        accept_cycle=consumer.cycle,
        stall_cycles_before_accept=0,
        retire_cycle=consumer.cycle + 3,
        forward_a=0b10,
        forward_b=0,
        source_a_producer_id=source_a,
        source_b_producer_id=None,
        source_a_cycle_age=1,
        source_b_cycle_age=None,
        redirect=False,
        redirect_bubbles=0,
    )


def canonical_pair():
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

    h = hit()
    exp = expectation(consumer)

    return producer, consumer, h, exp


def test_a5_producer_execution_event_identity_mismatch_rejected():
    _, consumer, h, exp = canonical_pair()

    control = check_l2_source_control(
        h,
        consumer,
        exp,
    )

    assert control.passed

    bad_producer = event(
        3,
        pc=8,
        rd=5,
        writes_rd=True,
    )

    checker = L2ValidatedCoverageChecker()

    with pytest.raises(
        ValueError,
        match="producer event does not match L2Hit",
    ):
        checker.register_hit(
            h,
            control=control,
            producer=bad_producer,
            consumer=consumer,
        )


def test_a6a_inconsistent_dependency_distance_rejected():
    consumer = event(
        2,
        pc=4,
        rs1=5,
        uses_rs1=True,
        fwd_a=0b10,
    )

    bad_hit = hit(
        producer_id=1,
        consumer_id=2,
        distance=2,
        register=5,
    )

    exp = expectation(consumer)

    with pytest.raises(
        ValueError,
        match="distance is inconsistent",
    ):
        check_l2_source_control(
            bad_hit,
            consumer,
            exp,
        )


def test_a6b_register_not_architectural_source_rejected():
    consumer = event(
        2,
        pc=4,
        rs1=5,
        uses_rs1=True,
        fwd_a=0b10,
    )

    bad_hit = hit(
        register=6,
    )

    exp = expectation(consumer)

    with pytest.raises(
        ValueError,
        match="not an architectural consumer source",
    ):
        check_l2_source_control(
            bad_hit,
            consumer,
            exp,
        )


def test_a6c_producer_rd_mismatch_rejected():
    _, consumer, h, exp = canonical_pair()

    control = check_l2_source_control(
        h,
        consumer,
        exp,
    )

    assert control.passed

    bad_producer = event(
        1,
        pc=0,
        rd=6,
        writes_rd=True,
    )

    checker = L2ValidatedCoverageChecker()

    with pytest.raises(
        ValueError,
        match="producer rd does not match L2 register",
    ):
        checker.register_hit(
            h,
            control=control,
            producer=bad_producer,
            consumer=consumer,
        )


def test_a6d_x0_cannot_be_positive_l2_register():
    consumer = event(
        2,
        pc=4,
        rs1=0,
        uses_rs1=True,
        fwd_a=0,
    )

    bad_hit = L2Hit(
        bin_index=0,
        distance=1,
        register=0,
        producer_instruction_index=1,
        consumer_instruction_index=2,
        producer_type="ALU_RESULT",
        consumer_type="ALU",
    )

    exp = expectation(
        consumer,
        source_a=1,
    )

    with pytest.raises(
        ValueError,
        match="positive L2 register must be x1..x31",
    ):
        check_l2_source_control(
            bad_hit,
            consumer,
            exp,
        )


def test_a6e_timing_expectation_consumer_identity_rejected():
    _, consumer, h, _ = canonical_pair()

    bad_exp = expectation(
        consumer,
        instruction_id=3,
    )

    with pytest.raises(
        ValueError,
        match="TimingExpectation consumer identity mismatch",
    ):
        check_l2_source_control(
            h,
            consumer,
            bad_exp,
        )
