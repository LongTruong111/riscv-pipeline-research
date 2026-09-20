import pytest

from research.week5.impl.isa_decode import (
    OP_BRANCH,
    OP_IMM,
    OP_R,
    decode_instruction,
    OP_AUIPC,
    OP_JAL,
    OP_JALR,
    OP_LOAD,
    OP_LUI,
    OP_STORE,
)


def test_add_decodes_mnemonic_and_fields():
    # add x5, x1, x2
    instruction = (
        (0b0000000 << 25)
        | (2 << 20)
        | (1 << 15)
        | (0b000 << 12)
        | (5 << 7)
        | OP_R
    )

    d = decode_instruction(instruction)

    assert d is not None
    assert d.mnemonic == "ADD"
    assert d.funct3 == 0b000
    assert d.funct7 == 0b0000000
    assert d.rd == 5
    assert d.rs1 == 1
    assert d.rs2 == 2


def test_addi_decodes_signed_immediate():
    # addi x5, x1, -1
    instruction = (
        (0xFFF << 20)
        | (1 << 15)
        | (0b000 << 12)
        | (5 << 7)
        | OP_IMM
    )

    d = decode_instruction(instruction)

    assert d is not None
    assert d.mnemonic == "ADDI"
    assert d.imm == -1
    assert d.uses_rs1
    assert not d.uses_rs2


@pytest.mark.parametrize(
    ("funct3", "mnemonic"),
    [
        (0b000, "BEQ"),
        (0b001, "BNE"),
        (0b100, "BLT"),
        (0b101, "BGE"),
        (0b110, "BLTU"),
        (0b111, "BGEU"),
    ],
)
def test_branch_mnemonics(funct3, mnemonic):
    instruction = (
        (2 << 20)
        | (1 << 15)
        | (funct3 << 12)
        | OP_BRANCH
    )

    d = decode_instruction(instruction)

    assert d is not None
    assert d.mnemonic == mnemonic
    assert d.uses_rs1
    assert d.uses_rs2
    assert not d.writes_rd

def test_lw_decodes_signed_immediate():
    instruction = (
        (0xFFC << 20)       # -4
        | (1 << 15)
        | (0b010 << 12)
        | (5 << 7)
        | OP_LOAD
    )

    d = decode_instruction(instruction)

    assert d is not None
    assert d.mnemonic == "LW"
    assert d.imm == -4
    assert d.rs1 == 1
    assert d.rd == 5
    assert d.uses_rs1
    assert not d.uses_rs2
    assert d.writes_rd


def test_sw_decodes_signed_immediate():
    imm = (-8) & 0xFFF

    instruction = (
        (((imm >> 5) & 0x7F) << 25)
        | (5 << 20)
        | (1 << 15)
        | (0b010 << 12)
        | ((imm & 0x1F) << 7)
        | OP_STORE
    )

    d = decode_instruction(instruction)

    assert d is not None
    assert d.mnemonic == "SW"
    assert d.imm == -8
    assert d.rs1 == 1
    assert d.rs2 == 5
    assert d.uses_rs1
    assert d.uses_rs2
    assert not d.writes_rd


def test_lui_decodes_u_immediate():
    instruction = (
        (0x12345 << 12)
        | (5 << 7)
        | OP_LUI
    )

    d = decode_instruction(instruction)

    assert d is not None
    assert d.mnemonic == "LUI"
    assert d.imm == 0x12345000
    assert d.rd == 5
    assert not d.uses_rs1
    assert not d.uses_rs2
    assert d.writes_rd


def test_auipc_decodes_u_immediate():
    instruction = (
        (0xABCDE << 12)
        | (6 << 7)
        | OP_AUIPC
    )

    d = decode_instruction(instruction)

    assert d is not None
    assert d.mnemonic == "AUIPC"
    assert d.imm == 0xABCDE000
    assert d.rd == 6


def test_jalr_decodes_signed_immediate():
    instruction = (
        (((-16) & 0xFFF) << 20)
        | (2 << 15)
        | (0b000 << 12)
        | (5 << 7)
        | OP_JALR
    )

    d = decode_instruction(instruction)

    assert d is not None
    assert d.mnemonic == "JALR"
    assert d.imm == -16
    assert d.rs1 == 2
    assert d.rd == 5
    assert d.uses_rs1
    assert not d.uses_rs2


def test_jal_decodes_positive_offset():
    # jal x5, +8
    instruction = (
        (0x004 << 21)
        | (5 << 7)
        | OP_JAL
    )

    d = decode_instruction(instruction)

    assert d is not None
    assert d.mnemonic == "JAL"
    assert d.imm == 8
    assert d.rd == 5
    assert not d.uses_rs1
    assert not d.uses_rs2
