from research.week5.impl.rv32_encode import (
    add,
    addi,
    auipc,
    beq,
    jal,
    lui,
    lw,
    sw,
)
from research.week6.timing_oracle import (
    FORWARD_EX_MEM,
    FORWARD_MEM_WB,
    FORWARD_RF,
)
from research.week7.timing_oracle_v1 import (
    REDIRECT_BUBBLES,
    RETIRE_LATENCY,
    build_timing_schedule_v1,
)


def program(*words):
    return {
        index * 4: word
        for index, word in enumerate(words)
    }


def test_pipeline_fill_and_drain():
    schedule = build_timing_schedule_v1(
        program(
            addi(1, 0, 1),
            addi(2, 0, 2),
        )
    )

    assert [
        item.accept_cycle
        for item in schedule.expectations
    ] == [1, 2]

    assert [
        item.retire_cycle
        for item in schedule.expectations
    ] == [4, 5]

    assert schedule.first_accept_cycle == 1
    assert schedule.first_retire_cycle == 1 + RETIRE_LATENCY
    assert schedule.drain_cycle == 5


def test_alu_d1_rs1_uses_ex_mem():
    schedule = build_timing_schedule_v1(
        program(
            addi(5, 0, 7),
            addi(6, 5, 1),
        )
    )

    consumer = schedule.expectations[1]

    assert consumer.stall_cycles_before_accept == 0
    assert consumer.forward_a == FORWARD_EX_MEM
    assert consumer.source_a_cycle_age == 1


def test_alu_d1_rs2_uses_ex_mem():
    schedule = build_timing_schedule_v1(
        program(
            addi(5, 0, 7),
            add(6, 0, 5),
        )
    )

    consumer = schedule.expectations[1]

    assert consumer.forward_b == FORWARD_EX_MEM
    assert consumer.source_b_cycle_age == 1


def test_alu_d2_uses_mem_wb():
    schedule = build_timing_schedule_v1(
        program(
            addi(5, 0, 7),
            addi(9, 0, 0),
            addi(6, 5, 1),
        )
    )

    consumer = schedule.expectations[2]

    assert consumer.forward_a == FORWARD_MEM_WB
    assert consumer.source_a_cycle_age == 2


def test_load_d1_stalls_exactly_once():
    schedule = build_timing_schedule_v1(
        program(
            lw(5, 0, 0),
            addi(6, 5, 1),
        )
    )

    producer, consumer = schedule.expectations

    assert producer.accept_cycle == 1
    assert consumer.accept_cycle == 3
    assert consumer.stall_cycles_before_accept == 1
    assert consumer.forward_a == FORWARD_MEM_WB
    assert consumer.source_a_cycle_age == 2

    assert schedule.total_stall_cycles == 1


def test_load_d2_does_not_stall():
    schedule = build_timing_schedule_v1(
        program(
            lw(5, 0, 0),
            addi(9, 0, 0),
            addi(6, 5, 1),
        )
    )

    consumer = schedule.expectations[2]

    assert consumer.accept_cycle == 3
    assert consumer.stall_cycles_before_accept == 0
    assert consumer.forward_a == FORWARD_MEM_WB


def test_consecutive_alu_hazards():
    schedule = build_timing_schedule_v1(
        program(
            addi(1, 0, 1),
            addi(2, 1, 1),
            addi(3, 2, 1),
        )
    )

    first, second, third = schedule.expectations

    assert [
        first.accept_cycle,
        second.accept_cycle,
        third.accept_cycle,
    ] == [1, 2, 3]

    assert second.forward_a == FORWARD_EX_MEM
    assert third.forward_a == FORWARD_EX_MEM

    assert second.source_a_producer_id == 1
    assert third.source_a_producer_id == 2


def test_dual_d1_d2_forwarding():
    schedule = build_timing_schedule_v1(
        program(
            addi(1, 0, 10),
            addi(2, 1, 5),
            add(3, 2, 1),
        )
    )

    consumer = schedule.expectations[2]

    assert consumer.forward_a == FORWARD_EX_MEM
    assert consumer.forward_b == FORWARD_MEM_WB

    assert consumer.source_a_producer_id == 2
    assert consumer.source_b_producer_id == 1


def test_newest_writer_priority():
    schedule = build_timing_schedule_v1(
        program(
            addi(5, 0, 1),
            addi(5, 0, 2),
            addi(6, 5, 0),
        )
    )

    consumer = schedule.expectations[2]

    assert consumer.source_a_producer_id == 2
    assert consumer.source_a_cycle_age == 1
    assert consumer.forward_a == FORWARD_EX_MEM


def test_x0_writer_creates_no_dependency():
    schedule = build_timing_schedule_v1(
        program(
            addi(0, 1, 7),
            addi(6, 0, 1),
        )
    )

    consumer = schedule.expectations[1]

    assert consumer.source_a_producer_id is None
    assert consumer.forward_a == FORWARD_RF
    assert consumer.stall_cycles_before_accept == 0


def test_unused_raw_rs2_does_not_create_load_stall():
    # imm=5 puts raw instruction bits [24:20] equal to x5,
    # but ADDI semantically uses only rs1.
    schedule = build_timing_schedule_v1(
        program(
            lw(5, 1, 0),
            addi(6, 2, 5),
        )
    )

    consumer = schedule.expectations[1]

    assert consumer.stall_cycles_before_accept == 0
    assert consumer.source_b_producer_id is None


def test_lui_d1_timing_is_ex_mem():
    schedule = build_timing_schedule_v1(
        program(
            lui(5, 0x12345),
            addi(6, 5, 1),
        )
    )

    consumer = schedule.expectations[1]

    # Timing expectation is independent from the known DUT
    # functional defect for H11.
    assert consumer.forward_a == FORWARD_EX_MEM


def test_auipc_d2_timing_is_mem_wb():
    schedule = build_timing_schedule_v1(
        program(
            auipc(5, 0x12345),
            addi(9, 0, 0),
            addi(6, 5, 1),
        )
    )

    consumer = schedule.expectations[2]

    assert consumer.forward_a == FORWARD_MEM_WB


def test_store_data_dependency_uses_forward_b():
    schedule = build_timing_schedule_v1(
        program(
            addi(5, 0, 42),
            sw(5, 0, 0),
        )
    )

    store = schedule.expectations[1]

    assert store.forward_b == FORWARD_EX_MEM
    assert store.source_b_producer_id == 1


def test_jal_redirect_inserts_two_bubbles():
    image = {
        0x00: jal(5, 12),
        0x04: addi(9, 0, 9),    # flushed
        0x08: addi(10, 0, 10),  # flushed
        0x0C: addi(6, 5, 1),
    }

    schedule = build_timing_schedule_v1(image)

    jump, target = schedule.expectations

    assert schedule.instruction_count == 2

    assert jump.pc == 0x00
    assert jump.redirect
    assert jump.redirect_bubbles == REDIRECT_BUBBLES

    assert target.pc == 0x0C

    assert [
        jump.accept_cycle,
        target.accept_cycle,
    ] == [1, 4]

    # Redirect bubbles make the link producer old enough to be read
    # from the register file at the target consumer.
    assert target.source_a_cycle_age == 3
    assert target.forward_a == FORWARD_RF

    assert [
        jump.retire_cycle,
        target.retire_cycle,
    ] == [4, 7]


def test_taken_branch_consumer_and_redirect():
    image = {
        0x00: addi(1, 0, 1),
        0x04: beq(1, 1, 12),
        0x08: addi(9, 0, 9),    # flushed
        0x0C: addi(10, 0, 10),  # flushed
        0x10: addi(2, 0, 2),
    }

    schedule = build_timing_schedule_v1(image)

    producer, branch, target = schedule.expectations

    assert producer.accept_cycle == 1

    assert branch.accept_cycle == 2
    assert branch.forward_a == FORWARD_EX_MEM
    assert branch.forward_b == FORWARD_EX_MEM
    assert branch.redirect

    # branch accepted at cycle 2; target accepted at 5.
    assert target.accept_cycle == 5
    assert target.pc == 0x10


def test_load_to_branch_stalls_then_redirects():
    image = {
        0x00: lw(1, 0, 0),
        0x04: beq(1, 1, 12),
        0x08: addi(9, 0, 9),
        0x0C: addi(10, 0, 10),
        0x10: addi(2, 0, 2),
    }

    schedule = build_timing_schedule_v1(image)

    load, branch, target = schedule.expectations

    assert load.accept_cycle == 1

    assert branch.stall_cycles_before_accept == 1
    assert branch.accept_cycle == 3

    assert branch.forward_a == FORWARD_MEM_WB
    assert branch.forward_b == FORWARD_MEM_WB
    assert branch.redirect

    assert target.accept_cycle == 6


def test_not_taken_branch_has_no_redirect_penalty():
    image = {
        0x00: addi(1, 0, 1),
        0x04: beq(1, 0, 8),
        0x08: addi(2, 0, 2),
        0x0C: addi(3, 0, 3),
    }

    schedule = build_timing_schedule_v1(image)

    _, branch, sequential, final = schedule.expectations

    assert branch.forward_a == FORWARD_EX_MEM
    assert not branch.redirect
    assert branch.redirect_bubbles == 0

    assert branch.accept_cycle == 2
    assert sequential.pc == 0x08
    assert sequential.accept_cycle == 3
    assert final.accept_cycle == 4


def test_fresh_schedule_restarts_reset_boundary():
    image = program(
        addi(1, 0, 1),
        addi(2, 1, 1),
    )

    first = build_timing_schedule_v1(image)
    second = build_timing_schedule_v1(image)

    assert first.expectations == second.expectations

    assert first.expectations[0].instruction_id == 1
    assert first.expectations[0].accept_cycle == 1
