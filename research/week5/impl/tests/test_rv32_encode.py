import pytest

from research.week5.impl.rv32_encode import (
    add,
    addi,
    auipc,
    jal,
    jalr,
    lui,
    lw,
    sw,
    word_to_le_bytes,
    words_to_hex_text,
)


def test_addi_x1_x0_1():
    assert addi(1, 0, 1) == 0x00100093


def test_addi_x6_x5_1():
    assert addi(6, 5, 1) == 0x00128313


def test_add_x6_x5_x1():
    assert add(6, 5, 1) == 0x00128333


def test_lw_x5_0_x0():
    assert lw(5, 0, 0) == 0x00002283


def test_sw_x5_0_x1():
    assert sw(5, 1, 0) == 0x0050A023


def test_lui():
    assert lui(5, 0x12345) == 0x123452B7


def test_auipc():
    assert auipc(5, 0x12345) == 0x12345297


def test_jalr_x5_x0_16():
    assert jalr(5, 0, 16) == 0x010002E7


def test_jal_x5_plus_8():
    assert jal(5, 8) == 0x008002EF


def test_negative_addi():
    assert addi(5, 0, -1) == 0xFFF00293


def test_little_endian_word_bytes():
    assert word_to_le_bytes(0x00100093) == [
        0x93,
        0x00,
        0x10,
        0x00,
    ]


def test_instruction_hex_format():
    text = words_to_hex_text([
        0x00100093,
        0x00002283,
    ])

    assert text == (
        "93\n"
        "00\n"
        "10\n"
        "00\n"
        "83\n"
        "22\n"
        "00\n"
        "00\n"
    )


@pytest.mark.parametrize(
    "imm",
    [-2049, 2048],
)
def test_i_immediate_range_rejected(imm):
    with pytest.raises(ValueError):
        addi(1, 0, imm)


def test_jal_requires_two_byte_alignment():
    with pytest.raises(ValueError):
        jal(1, 3)


def test_invalid_register_rejected():
    with pytest.raises(ValueError):
        addi(32, 0, 1)
