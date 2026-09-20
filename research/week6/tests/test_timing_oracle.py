import pytest

from research.week5.impl.rv32_encode import (
    add,
    addi,
    beq,
    lui,
    lw,
)
from research.week6.timing_oracle import (
    FORWARD_EX_MEM,
    FORWARD_MEM_WB,
    FORWARD_RF,
    UnsupportedTimingScenario,
    build_timing_expectations,
)


def final_expectation(words):
    return build_timing_expectations(words)[-1]


def test_no_hazard_uses_register_file():
    exp = final_expectation(
        [
            addi(1, 0, 1),
            addi(2, 0, 2),
        ]
    )

    assert exp.stall_cycles_before_accept == 0
    assert exp.forward_a == FORWARD_RF
    assert exp.forward_b == FORWARD_RF
    assert exp.reason == "NO_HAZARD"


def test_alu_d1_rs1_uses_ex_mem():
    exp = final_expectation(
        [
            addi(5, 0, 7),
            addi(6, 5, 1),
        ]
    )

    assert exp.stall_cycles_before_accept == 0
    assert exp.forward_a == FORWARD_EX_MEM
    assert exp.forward_b == FORWARD_RF
    assert exp.source_a_distance == 1


def test_alu_d1_rs2_uses_ex_mem():
    exp = final_expectation(
        [
            addi(5, 0, 7),
            add(6, 0, 5),
        ]
    )

    assert exp.stall_cycles_before_accept == 0
    assert exp.forward_a == FORWARD_RF
    assert exp.forward_b == FORWARD_EX_MEM
    assert exp.source_b_distance == 1


def test_alu_d2_rs1_uses_mem_wb():
    exp = final_expectation(
        [
            addi(5, 0, 7),
            addi(9, 0, 0),
            addi(6, 5, 1),
        ]
    )

    assert exp.stall_cycles_before_accept == 0
    assert exp.forward_a == FORWARD_MEM_WB
    assert exp.source_a_distance == 2


def test_alu_d2_rs2_uses_mem_wb():
    exp = final_expectation(
        [
            addi(5, 0, 7),
            addi(9, 0, 0),
            add(6, 0, 5),
        ]
    )

    assert exp.stall_cycles_before_accept == 0
    assert exp.forward_b == FORWARD_MEM_WB
    assert exp.source_b_distance == 2


def test_load_d1_rs1_requires_one_stall_then_mem_wb():
    exp = final_expectation(
        [
            lw(5, 0, 0),
            addi(6, 5, 1),
        ]
    )

    assert exp.stall_cycles_before_accept == 1
    assert exp.forward_a == FORWARD_MEM_WB
    assert exp.forward_b == FORWARD_RF
    assert exp.reason == "LOAD_D1"


def test_load_d1_rs2_requires_one_stall_then_mem_wb():
    exp = final_expectation(
        [
            lw(5, 0, 0),
            add(6, 0, 5),
        ]
    )

    assert exp.stall_cycles_before_accept == 1
    assert exp.forward_a == FORWARD_RF
    assert exp.forward_b == FORWARD_MEM_WB
    assert exp.reason == "LOAD_D1"


def test_load_d2_rs1_requires_no_stall():
    exp = final_expectation(
        [
            lw(5, 0, 0),
            addi(9, 0, 0),
            addi(6, 5, 1),
        ]
    )

    assert exp.stall_cycles_before_accept == 0
    assert exp.forward_a == FORWARD_MEM_WB
    assert exp.source_a_distance == 2
    assert exp.reason == "LOAD_D2"


def test_load_d2_rs2_requires_no_stall():
    exp = final_expectation(
        [
            lw(5, 0, 0),
            addi(9, 0, 0),
            add(6, 0, 5),
        ]
    )

    assert exp.stall_cycles_before_accept == 0
    assert exp.forward_b == FORWARD_MEM_WB
    assert exp.source_b_distance == 2


def test_rd_x0_never_creates_dependency():
    exp = final_expectation(
        [
            addi(0, 1, 7),
            addi(6, 0, 1),
        ]
    )

    assert exp.stall_cycles_before_accept == 0
    assert exp.forward_a == FORWARD_RF
    assert exp.forward_b == FORWARD_RF
    assert exp.reason == "NO_HAZARD"


def test_unused_raw_rs2_never_creates_false_load_use():
    # ADDI uses rs1=x2 only.
    # imm=5 makes raw instruction bits [24:20] equal x5.
    exp = final_expectation(
        [
            lw(5, 1, 0),
            addi(6, 2, 5),
        ]
    )

    assert exp.stall_cycles_before_accept == 0
    assert exp.forward_a == FORWARD_RF
    assert exp.forward_b == FORWARD_RF
    assert exp.reason == "NO_HAZARD"


def test_newest_writer_has_priority_over_shadowed_d2_writer():
    exp = final_expectation(
        [
            addi(5, 0, 1),
            addi(5, 0, 2),
            addi(6, 5, 0),
        ]
    )

    assert exp.stall_cycles_before_accept == 0
    assert exp.forward_a == FORWARD_EX_MEM
    assert exp.source_a_distance == 1


def test_dual_alu_forwarding_d1_and_d2():
    exp = final_expectation(
        [
            addi(1, 0, 10),
            addi(2, 1, 5),
            add(3, 2, 1),
        ]
    )

    assert exp.stall_cycles_before_accept == 0
    assert exp.forward_a == FORWARD_EX_MEM
    assert exp.forward_b == FORWARD_MEM_WB
    assert exp.source_a_distance == 1
    assert exp.source_b_distance == 2
    assert exp.reason == "MULTI_FORWARD"


def test_composite_load_use_with_second_dependency_is_deferred():
    with pytest.raises(
        UnsupportedTimingScenario,
        match="composite load-use",
    ):
        build_timing_expectations(
            [
                addi(1, 0, 10),
                lw(2, 0, 0),
                add(3, 2, 1),
            ]
        )


def test_control_flow_timing_is_deferred_to_v1():
    with pytest.raises(
        UnsupportedTimingScenario,
        match="deferred to Timing Oracle v1",
    ):
        build_timing_expectations(
            [
                beq(1, 2, 8),
            ]
        )


def test_special_writeback_producer_is_outside_v0():
    with pytest.raises(
        UnsupportedTimingScenario,
        match="producer type is outside",
    ):
        build_timing_expectations(
            [
                lui(5, 0x12345),
                addi(6, 5, 1),
            ]
        )
