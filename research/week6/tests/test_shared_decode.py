import pytest

from research.week5.impl.isa_decode import (
    OP_BRANCH,
    OP_IMM,
    OP_R,
    decode_instruction,
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
