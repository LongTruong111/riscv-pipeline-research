from research.week5.impl.isa_decode import (
    OP_AUIPC,
    OP_BRANCH,
    OP_IMM,
    OP_JAL,
    OP_JALR,
    OP_LOAD,
    OP_LUI,
    OP_R,
    OP_STORE,
    decode_instruction,
)


def encode(opcode, *, rd=0, rs1=0, rs2=0):
    return (
        opcode
        | (rd << 7)
        | (rs1 << 15)
        | (rs2 << 20)
    )


def test_r_type_uses_both_sources_and_writes_rd():
    d = decode_instruction(
        encode(OP_R, rd=5, rs1=1, rs2=2)
    )

    assert d is not None
    assert d.rs1 == 1
    assert d.rs2 == 2
    assert d.rd == 5
    assert d.uses_rs1
    assert d.uses_rs2
    assert d.writes_rd
    assert d.producer_type == "ALU_RESULT"
    assert d.consumer_type == "RS1_RS2"


def test_op_imm_ignores_raw_rs2_field():
    d = decode_instruction(
        encode(OP_IMM, rd=6, rs1=2, rs2=5)
    )

    assert d is not None

    # Raw [24:20] bits are still decoded for observability,
    # but they are not an architectural source for OP-IMM.
    assert d.rs2 == 5
    assert d.uses_rs1
    assert not d.uses_rs2
    assert d.writes_rd
    assert d.producer_type == "ALU_RESULT"
    assert d.consumer_type == "RS1_ONLY"


def test_load_is_mem_data_rs1_only():
    d = decode_instruction(
        encode(OP_LOAD, rd=5, rs1=1, rs2=7)
    )

    assert d is not None
    assert d.uses_rs1
    assert not d.uses_rs2
    assert d.writes_rd
    assert d.producer_type == "MEM_DATA"
    assert d.consumer_type == "RS1_ONLY"


def test_store_uses_both_sources_and_does_not_write_rd():
    d = decode_instruction(
        encode(OP_STORE, rs1=1, rs2=5)
    )

    assert d is not None
    assert d.uses_rs1
    assert d.uses_rs2
    assert not d.writes_rd
    assert d.producer_type == "NONE"
    assert d.consumer_type == "RS1_RS2"


def test_branch_uses_both_sources():
    d = decode_instruction(
        encode(OP_BRANCH, rs1=3, rs2=4)
    )

    assert d is not None
    assert d.uses_rs1
    assert d.uses_rs2
    assert not d.writes_rd
    assert d.consumer_type == "RS1_RS2"


def test_jal_has_no_gpr_source():
    d = decode_instruction(
        encode(OP_JAL, rd=5)
    )

    assert d is not None
    assert not d.uses_rs1
    assert not d.uses_rs2
    assert d.writes_rd
    assert d.producer_type == "PC_PLUS_4"
    assert d.consumer_type == "NO_GPR_SOURCE"


def test_jalr_uses_rs1_only():
    d = decode_instruction(
        encode(OP_JALR, rd=5, rs1=2, rs2=9)
    )

    assert d is not None
    assert d.uses_rs1
    assert not d.uses_rs2
    assert d.writes_rd
    assert d.producer_type == "PC_PLUS_4"
    assert d.consumer_type == "RS1_ONLY"


def test_lui_has_no_gpr_source():
    d = decode_instruction(
        encode(OP_LUI, rd=5, rs1=7, rs2=8)
    )

    assert d is not None
    assert not d.uses_rs1
    assert not d.uses_rs2
    assert d.writes_rd
    assert d.producer_type == "IMM"
    assert d.consumer_type == "NO_GPR_SOURCE"


def test_auipc_has_no_gpr_source():
    d = decode_instruction(
        encode(OP_AUIPC, rd=5, rs1=7, rs2=8)
    )

    assert d is not None
    assert not d.uses_rs1
    assert not d.uses_rs2
    assert d.writes_rd
    assert d.producer_type == "PC_PLUS_IMM"
    assert d.consumer_type == "NO_GPR_SOURCE"


def test_unknown_opcode_returns_none():
    assert decode_instruction(0x00000000) is None


def test_rejects_values_wider_than_32_bits():
    try:
        decode_instruction(0x1_00000000)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
