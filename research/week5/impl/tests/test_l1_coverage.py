import pytest

from research.week5.impl.execution_event import ExecutionEvent
from research.week5.impl.isa_decode import (
    OP_AUIPC,
    OP_IMM,
    OP_JAL,
    OP_LOAD,
    OP_LUI,
    OP_R,
    OP_STORE,
)
from research.week5.impl.l1_coverage import (
    L1_BIN_COUNT,
    L1CoverageCollector,
)


def event(
    index,
    *,
    opcode,
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
):
    instruction = (
        opcode
        | ((rd & 0x1F) << 7)
        | ((rs1 & 0x1F) << 15)
        | ((rs2 & 0x1F) << 20)
    )

    return ExecutionEvent(
        instruction_index=index,
        cycle=index,
        pc=((index - 1) * 4) & 0x1FF,
        instruction=instruction,
        rs1=rs1,
        rs2=rs2,
        rd=rd,
        uses_rs1=uses_rs1,
        uses_rs2=uses_rs2,
        writes_rd=writes_rd,
        producer_type=producer_type,
        consumer_type=consumer_type,
        stall_cycles_before_accept=stall_cycles_before_accept,
        forward_a=forward_a,
        forward_b=forward_b,
    )


def alu_writer(index, rd):
    return event(
        index,
        opcode=OP_IMM,
        rs1=0,
        rd=rd,
        uses_rs1=True,
        writes_rd=True,
        producer_type="ALU_RESULT",
        consumer_type="RS1_ONLY",
    )


def load_writer(index, rd):
    return event(
        index,
        opcode=OP_LOAD,
        rs1=1,
        rd=rd,
        uses_rs1=True,
        writes_rd=True,
        producer_type="MEM_DATA",
        consumer_type="RS1_ONLY",
    )


def lui_writer(index, rd):
    return event(
        index,
        opcode=OP_LUI,
        rd=rd,
        writes_rd=True,
        producer_type="IMM",
        consumer_type="NO_GPR_SOURCE",
    )


def auipc_writer(index, rd):
    return event(
        index,
        opcode=OP_AUIPC,
        rd=rd,
        writes_rd=True,
        producer_type="PC_PLUS_IMM",
        consumer_type="NO_GPR_SOURCE",
    )


def link_writer(index, rd):
    return event(
        index,
        opcode=OP_JAL,
        rd=rd,
        writes_rd=True,
        producer_type="PC_PLUS_4",
        consumer_type="NO_GPR_SOURCE",
    )


def rs1_consumer(index, rs1, *, raw_rs2=0):
    return event(
        index,
        opcode=OP_IMM,
        rs1=rs1,
        rs2=raw_rs2,
        rd=20,
        uses_rs1=True,
        uses_rs2=False,
        writes_rd=True,
        producer_type="ALU_RESULT",
        consumer_type="RS1_ONLY",
    )


def rs2_consumer(index, rs2, *, rs1=0):
    return event(
        index,
        opcode=OP_R,
        rs1=rs1,
        rs2=rs2,
        rd=20,
        uses_rs1=True,
        uses_rs2=True,
        writes_rd=True,
        producer_type="ALU_RESULT",
        consumer_type="RS1_RS2",
    )


def dual_consumer(index, rs1, rs2):
    return event(
        index,
        opcode=OP_R,
        rs1=rs1,
        rs2=rs2,
        rd=20,
        uses_rs1=True,
        uses_rs2=True,
        writes_rd=True,
        producer_type="ALU_RESULT",
        consumer_type="RS1_RS2",
    )


def store_consumer(index, rs1, rs2):
    return event(
        index,
        opcode=OP_STORE,
        rs1=rs1,
        rs2=rs2,
        rd=0,
        uses_rs1=True,
        uses_rs2=True,
        writes_rd=False,
        producer_type="NONE",
        consumer_type="RS1_RS2",
    )


def independent(index, rd):
    return alu_writer(index, rd)


def hit_ids(hits):
    return {hit.bin_id for hit in hits}


def test_h01_alu_d1_rs1():
    cov = L1CoverageCollector()

    cov.observe(alu_writer(1, 5))
    hits = cov.observe(rs1_consumer(2, 5))

    assert "H01" in hit_ids(hits)


def test_h02_alu_d1_rs2():
    cov = L1CoverageCollector()

    cov.observe(alu_writer(1, 5))
    hits = cov.observe(rs2_consumer(2, 5))

    assert "H02" in hit_ids(hits)


def test_h03_alu_d2_rs1():
    cov = L1CoverageCollector()

    cov.observe(alu_writer(1, 5))
    cov.observe(independent(2, 9))
    hits = cov.observe(rs1_consumer(3, 5))

    assert "H03" in hit_ids(hits)


def test_h04_alu_d2_rs2():
    cov = L1CoverageCollector()

    cov.observe(alu_writer(1, 5))
    cov.observe(independent(2, 9))
    hits = cov.observe(rs2_consumer(3, 5))

    assert "H04" in hit_ids(hits)


def test_h05_d3_rf_boundary():
    cov = L1CoverageCollector()

    cov.observe(load_writer(1, 5))
    cov.observe(independent(2, 9))
    cov.observe(independent(3, 10))
    hits = cov.observe(rs1_consumer(4, 5))

    assert "H05" in hit_ids(hits)


def test_h06_load_d1_rs1_intent_does_not_require_correct_stall():
    cov = L1CoverageCollector()

    cov.observe(load_writer(1, 5))

    hits = cov.observe(
        rs1_consumer(
            2,
            5,
        )
    )

    assert "H06" in hit_ids(hits)


def test_h07_load_d1_rs2():
    cov = L1CoverageCollector()

    cov.observe(load_writer(1, 5))
    hits = cov.observe(rs2_consumer(2, 5))

    assert "H07" in hit_ids(hits)


def test_h08_load_d2_rs1():
    cov = L1CoverageCollector()

    cov.observe(load_writer(1, 5))
    cov.observe(independent(2, 9))
    hits = cov.observe(rs1_consumer(3, 5))

    assert "H08" in hit_ids(hits)


def test_h09_load_d2_rs2():
    cov = L1CoverageCollector()

    cov.observe(load_writer(1, 5))
    cov.observe(independent(2, 9))
    hits = cov.observe(rs2_consumer(3, 5))

    assert "H09" in hit_ids(hits)


def test_h10_dual_d1_d2():
    cov = L1CoverageCollector()

    cov.observe(alu_writer(1, 1))
    cov.observe(alu_writer(2, 2))

    hits = cov.observe(
        dual_consumer(
            3,
            rs1=2,
            rs2=1,
        )
    )

    assert "H10" in hit_ids(hits)


def test_h10_accepts_reversed_source_orientation():
    cov = L1CoverageCollector()

    cov.observe(alu_writer(1, 1))
    cov.observe(alu_writer(2, 2))

    hits = cov.observe(
        dual_consumer(
            3,
            rs1=1,
            rs2=2,
        )
    )

    assert "H10" in hit_ids(hits)


def test_h11_lui_d1():
    cov = L1CoverageCollector()

    cov.observe(lui_writer(1, 5))
    hits = cov.observe(rs1_consumer(2, 5))

    assert "H11" in hit_ids(hits)


def test_h12_lui_d2():
    cov = L1CoverageCollector()

    cov.observe(lui_writer(1, 5))
    cov.observe(independent(2, 9))
    hits = cov.observe(rs1_consumer(3, 5))

    assert "H12" in hit_ids(hits)


def test_h13_auipc_d1():
    cov = L1CoverageCollector()

    cov.observe(auipc_writer(1, 5))
    hits = cov.observe(rs1_consumer(2, 5))

    assert "H13" in hit_ids(hits)


def test_h14_auipc_d2():
    cov = L1CoverageCollector()

    cov.observe(auipc_writer(1, 5))
    cov.observe(independent(2, 9))
    hits = cov.observe(rs1_consumer(3, 5))

    assert "H14" in hit_ids(hits)


def test_h15_link_next_executed_target_consumer():
    cov = L1CoverageCollector()

    cov.observe(link_writer(1, 5))
    hits = cov.observe(rs1_consumer(2, 5))

    assert "H15" in hit_ids(hits)


def test_h16_store_data_forwarding_scenario():
    cov = L1CoverageCollector()

    cov.observe(alu_writer(1, 5))

    hits = cov.observe(
        store_consumer(
            2,
            rs1=1,
            rs2=5,
        )
    )

    assert "H16" in hit_ids(hits)


def test_h17_newest_writer_priority():
    cov = L1CoverageCollector()

    cov.observe(alu_writer(1, 5))
    cov.observe(alu_writer(2, 5))

    hits = cov.observe(rs1_consumer(3, 5))

    assert "H17" in hit_ids(hits)

    h17 = next(hit for hit in hits if hit.bin_id == "H17")

    assert h17.producer_instruction_indices == (1, 2)


def test_h18_x0_forwarding_exclusion():
    cov = L1CoverageCollector()

    cov.observe(
        event(
            1,
            opcode=OP_IMM,
            rs1=1,
            rd=0,
            uses_rs1=True,
            writes_rd=True,
            producer_type="ALU_RESULT",
            consumer_type="RS1_ONLY",
        )
    )

    hits = cov.observe(rs1_consumer(2, 0))

    assert "H18" in hit_ids(hits)


def test_h19_load_to_x0_negative_case():
    cov = L1CoverageCollector()

    cov.observe(load_writer(1, 0))

    consumer = event(
        2,
        opcode=OP_IMM,
        rs1=0,
        rs2=1,
        rd=6,
        uses_rs1=True,
        uses_rs2=False,
        writes_rd=True,
        producer_type="ALU_RESULT",
        consumer_type="RS1_ONLY",
        # Even if RTL falsely stalled, Intent must still be recorded.
        stall_cycles_before_accept=1,
    )

    hits = cov.observe(consumer)

    assert "H19" in hit_ids(hits)


def test_h20_unused_raw_rs2_negative_case():
    cov = L1CoverageCollector()

    cov.observe(load_writer(1, 5))

    # OP-IMM uses rs1=x2 only.
    # Raw instruction bits [24:20] are immediate bits and equal 5.
    consumer = rs1_consumer(
        2,
        rs1=2,
        raw_rs2=5,
    )

    hits = cov.observe(consumer)

    assert "H20" in hit_ids(hits)


def test_h20_not_hit_when_real_rs1_dependency_exists():
    cov = L1CoverageCollector()

    cov.observe(load_writer(1, 5))

    consumer = rs1_consumer(
        2,
        rs1=5,
        raw_rs2=5,
    )

    hits = cov.observe(consumer)

    assert "H20" not in hit_ids(hits)
    assert "H06" in hit_ids(hits)


def test_d2_producer_is_not_counted_when_shadowed():
    cov = L1CoverageCollector()

    cov.observe(alu_writer(1, 5))
    cov.observe(alu_writer(2, 5))

    hits = cov.observe(rs1_consumer(3, 5))

    assert "H03" not in hit_ids(hits)
    assert "H01" in hit_ids(hits)
    assert "H17" in hit_ids(hits)


def test_d3_producer_is_not_counted_when_shadowed():
    cov = L1CoverageCollector()

    cov.observe(load_writer(1, 5))
    cov.observe(alu_writer(2, 5))
    cov.observe(independent(3, 9))

    hits = cov.observe(rs1_consumer(4, 5))

    assert "H05" not in hit_ids(hits)


def test_repeated_hits_do_not_increase_unique_bin_count():
    cov = L1CoverageCollector()

    cov.observe(alu_writer(1, 5))
    cov.observe(rs1_consumer(2, 5))

    first_unique = cov.intent_bins

    cov.observe(alu_writer(3, 6))
    cov.observe(rs1_consumer(4, 6))

    assert cov.intent_bins == first_unique
    assert cov.intent_hit_count["H01"] == 2


def test_all_20_bin_identifiers_exist():
    cov = L1CoverageCollector()

    assert len(cov.intent_seen) == L1_BIN_COUNT
    assert set(cov.intent_seen) == {
        f"H{i:02d}" for i in range(1, 21)
    }


def test_non_contiguous_execution_stream_is_rejected():
    cov = L1CoverageCollector()

    cov.observe(alu_writer(1, 5))

    with pytest.raises(ValueError):
        cov.observe(rs1_consumer(3, 5))
