import pytest

from research.week5.impl.rv32_encode import (
    beq,
    bne,
    blt,
    bge,
    bltu,
    bgeu,
)
from research.week5.impl.isa_decode import decode_instruction


@pytest.mark.parametrize(
    ("encoder", "mnemonic"),
    [
        (beq, "BEQ"),
        (bne, "BNE"),
        (blt, "BLT"),
        (bge, "BGE"),
        (bltu, "BLTU"),
        (bgeu, "BGEU"),
    ],
)
def test_branch_encode_decode_round_trip(encoder, mnemonic):
    instruction = encoder(1, 2, 8)

    d = decode_instruction(instruction)

    assert d is not None
    assert d.mnemonic == mnemonic
    assert d.rs1 == 1
    assert d.rs2 == 2
    assert d.imm == 8


@pytest.mark.parametrize(
    "offset",
    [-4096, -2, 0, 2, 4094],
)
def test_branch_boundary_offsets(offset):
    instruction = beq(1, 2, offset)

    d = decode_instruction(instruction)

    assert d is not None
    assert d.imm == offset


@pytest.mark.parametrize(
    "offset",
    [-4098, 4096],
)
def test_branch_range_rejected(offset):
    with pytest.raises(ValueError):
        beq(1, 2, offset)


def test_branch_alignment_rejected():
    with pytest.raises(ValueError):
        beq(1, 2, 3)
