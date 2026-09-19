import pytest

from research.week5.impl.execution_event import ExecutionEvent
from research.week5.impl.l1_coverage import L1Hit
from research.week5.impl.realization_checker import (
    L1ControlRealizationChecker,
)


def ev(
    index,
    *,
    rs1=0,
    rs2=0,
    rd=0,
    uses_rs1=True,
    uses_rs2=False,
    stall=0,
    fwd_a=0,
    fwd_b=0,
):
    return ExecutionEvent(
        instruction_index=index,
        cycle=index,
        pc=((index - 1) * 4) & 0x1FF,
        instruction=0,
        rs1=rs1,
        rs2=rs2,
        rd=rd,
        uses_rs1=uses_rs1,
        uses_rs2=uses_rs2,
        writes_rd=(rd != 0),
        producer_type="ALU_RESULT",
        consumer_type=(
            "RS1_RS2"
            if uses_rs2
            else "RS1_ONLY"
        ),
        stall_cycles_before_accept=stall,
        forward_a=fwd_a,
        forward_b=fwd_b,
    )


def hit(
    bin_id,
    consumer_index=2,
    producers=(1,),
    sources=("RS1",),
):
    return L1Hit(
        bin_id=bin_id,
        consumer_instruction_index=consumer_index,
        producer_instruction_indices=producers,
        matched_sources=sources,
    )


@pytest.mark.parametrize(
    "bin_id,role,forward_value,stall",
    [
        ("H01", "RS1", 0b10, 0),
        ("H02", "RS2", 0b10, 0),
        ("H03", "RS1", 0b01, 0),
        ("H04", "RS2", 0b01, 0),

        ("H06", "RS1", 0b01, 1),
        ("H07", "RS2", 0b01, 1),
        ("H08", "RS1", 0b01, 0),
        ("H09", "RS2", 0b01, 0),

        ("H11", "RS1", 0b10, 0),
        ("H12", "RS1", 0b01, 0),
        ("H13", "RS1", 0b10, 0),
        ("H14", "RS1", 0b01, 0),

        ("H16", "RS2", 0b10, 0),
    ],
)
def test_fixed_forwarding_rules_pass(
    bin_id,
    role,
    forward_value,
    stall,
):
    checker = L1ControlRealizationChecker()

    consumer = ev(
        2,
        rs1=5,
        rs2=5,
        uses_rs1=True,
        uses_rs2=(role == "RS2"),
        stall=stall,
        fwd_a=(
            forward_value
            if role == "RS1"
            else 0
        ),
        fwd_b=(
            forward_value
            if role == "RS2"
            else 0
        ),
    )

    result = checker.check(
        hit(
            bin_id,
            sources=(role,),
        ),
        consumer,
        {1: ev(1, rd=5)},
    )

    assert result.passed
    assert result.failed_checks == ()


def test_wrong_forwarding_fails():
    checker = L1ControlRealizationChecker()

    consumer = ev(
        2,
        rs1=5,
        fwd_a=0b01,
    )

    result = checker.check(
        hit("H01"),
        consumer,
        {1: ev(1, rd=5)},
    )

    assert not result.passed

    assert any(
        check.name == "forward_rs1"
        for check in result.failed_checks
    )


def test_h06_requires_exactly_one_stall():
    checker = L1ControlRealizationChecker()

    consumer = ev(
        2,
        rs1=5,
        stall=0,
        fwd_a=0b01,
    )

    result = checker.check(
        hit("H06"),
        consumer,
        {1: ev(1, rd=5)},
    )

    assert not result.passed

    failed = {
        check.name
        for check in result.failed_checks
    }

    assert "stall_cycles_before_accept" in failed


def test_h05_rf_boundary_requires_no_forwarding():
    checker = L1ControlRealizationChecker()

    consumer = ev(
        4,
        rs1=5,
        fwd_a=0b00,
    )

    result = checker.check(
        hit(
            "H05",
            consumer_index=4,
            producers=(1,),
            sources=("RS1",),
        ),
        consumer,
        {
            1: ev(1, rd=5),
            2: ev(2, rd=9),
            3: ev(3, rd=10),
        },
    )

    assert result.passed


def test_h10_canonical_orientation():
    checker = L1ControlRealizationChecker()

    older = ev(1, rd=1)
    newer = ev(2, rd=2)

    consumer = ev(
        3,
        rs1=2,
        rs2=1,
        uses_rs1=True,
        uses_rs2=True,
        fwd_a=0b10,
        fwd_b=0b01,
    )

    result = checker.check(
        hit(
            "H10",
            consumer_index=3,
            producers=(1, 2),
            sources=("RS1", "RS2"),
        ),
        consumer,
        {
            1: older,
            2: newer,
        },
    )

    assert result.passed


def test_h10_reversed_orientation():
    checker = L1ControlRealizationChecker()

    older = ev(1, rd=1)
    newer = ev(2, rd=2)

    consumer = ev(
        3,
        rs1=1,
        rs2=2,
        uses_rs1=True,
        uses_rs2=True,
        fwd_a=0b01,
        fwd_b=0b10,
    )

    result = checker.check(
        hit(
            "H10",
            consumer_index=3,
            producers=(1, 2),
            sources=("RS1", "RS2"),
        ),
        consumer,
        {
            1: older,
            2: newer,
        },
    )

    assert result.passed


def test_h15_requires_rf_visibility():
    checker = L1ControlRealizationChecker()

    consumer = ev(
        2,
        rs1=5,
        fwd_a=0b00,
    )

    result = checker.check(
        hit(
            "H15",
            sources=("RS1",),
        ),
        consumer,
        {1: ev(1, rd=5)},
    )

    assert result.passed


def test_h17_newest_writer_requires_ex_mem():
    checker = L1ControlRealizationChecker()

    consumer = ev(
        3,
        rs1=5,
        fwd_a=0b10,
    )

    result = checker.check(
        hit(
            "H17",
            consumer_index=3,
            producers=(1, 2),
            sources=("RS1",),
        ),
        consumer,
        {
            1: ev(1, rd=5),
            2: ev(2, rd=5),
        },
    )

    assert result.passed


def test_h18_x0_requires_no_forwarding():
    checker = L1ControlRealizationChecker()

    consumer = ev(
        2,
        rs1=0,
        fwd_a=0b00,
    )

    result = checker.check(
        hit(
            "H18",
            sources=("RS1",),
        ),
        consumer,
        {1: ev(1, rd=0)},
    )

    assert result.passed


@pytest.mark.parametrize(
    "bin_id",
    ["H19", "H20"],
)
def test_negative_false_stall_bins_fail_if_stalled(
    bin_id,
):
    checker = L1ControlRealizationChecker()

    consumer = ev(
        2,
        rs1=0,
        stall=1,
    )

    result = checker.check(
        hit(bin_id),
        consumer,
        {1: ev(1, rd=5)},
    )

    assert not result.passed

    assert result.failed_checks[0].name == (
        "stall_cycles_before_accept"
    )


@pytest.mark.parametrize(
    "bin_id",
    ["H19", "H20"],
)
def test_negative_false_stall_bins_pass_without_stall(
    bin_id,
):
    checker = L1ControlRealizationChecker()

    consumer = ev(
        2,
        rs1=0,
        stall=0,
    )

    result = checker.check(
        hit(bin_id),
        consumer,
        {1: ev(1, rd=5)},
    )

    assert result.passed


def test_consumer_index_mismatch_rejected():
    checker = L1ControlRealizationChecker()

    with pytest.raises(ValueError):
        checker.check(
            hit(
                "H01",
                consumer_index=3,
            ),
            ev(
                2,
                rs1=5,
                fwd_a=0b10,
            ),
            {1: ev(1, rd=5)},
        )
