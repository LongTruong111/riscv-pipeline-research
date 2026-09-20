from pathlib import Path
from typing import Iterable, List


OP_R = 0b0110011
OP_IMM = 0b0010011
OP_LOAD = 0b0000011
OP_STORE = 0b0100011
OP_JAL = 0b1101111
OP_JALR = 0b1100111
OP_LUI = 0b0110111
OP_AUIPC = 0b0010111
OP_BRANCH = 0b1100011

def _reg(value: int) -> int:
    if not 0 <= value <= 31:
        raise ValueError(f"register must be x0..x31, got x{value}")
    return value


def _signed_imm(value: int, bits: int, *, alignment: int = 1) -> int:
    minimum = -(1 << (bits - 1))
    maximum = (1 << (bits - 1)) - 1

    if not minimum <= value <= maximum:
        raise ValueError(
            f"{bits}-bit signed immediate out of range: {value}"
        )

    if value % alignment != 0:
        raise ValueError(
            f"immediate {value} must be aligned to {alignment}"
        )

    return value & ((1 << bits) - 1)

def _branch(
    rs1: int,
    rs2: int,
    offset: int,
    funct3: int,
) -> int:
    rs1 = _reg(rs1)
    rs2 = _reg(rs2)
    imm13 = _signed_imm(offset, 13, alignment=2)

    bit12 = (imm13 >> 12) & 0x1
    bit11 = (imm13 >> 11) & 0x1
    bits10_5 = (imm13 >> 5) & 0x3F
    bits4_1 = (imm13 >> 1) & 0xF

    return (
        (bit12 << 31)
        | (bits10_5 << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (funct3 << 12)
        | (bits4_1 << 8)
        | (bit11 << 7)
        | OP_BRANCH
    )

def add(rd: int, rs1: int, rs2: int) -> int:
    rd = _reg(rd)
    rs1 = _reg(rs1)
    rs2 = _reg(rs2)

    funct3 = 0b000
    funct7 = 0b0000000

    return (
        (funct7 << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (funct3 << 12)
        | (rd << 7)
        | OP_R
    )


def addi(rd: int, rs1: int, imm: int) -> int:
    rd = _reg(rd)
    rs1 = _reg(rs1)
    imm12 = _signed_imm(imm, 12)

    return (
        (imm12 << 20)
        | (rs1 << 15)
        | (0b000 << 12)
        | (rd << 7)
        | OP_IMM
    )


def lw(rd: int, rs1: int, imm: int) -> int:
    rd = _reg(rd)
    rs1 = _reg(rs1)
    imm12 = _signed_imm(imm, 12)

    return (
        (imm12 << 20)
        | (rs1 << 15)
        | (0b010 << 12)
        | (rd << 7)
        | OP_LOAD
    )


def sw(rs2: int, rs1: int, imm: int) -> int:
    """
    Encode: sw rs2, imm(rs1)
    """
    rs1 = _reg(rs1)
    rs2 = _reg(rs2)
    imm12 = _signed_imm(imm, 12)

    imm_hi = (imm12 >> 5) & 0x7F
    imm_lo = imm12 & 0x1F

    return (
        (imm_hi << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (0b010 << 12)
        | (imm_lo << 7)
        | OP_STORE
    )


def lui(rd: int, imm20: int) -> int:
    rd = _reg(rd)

    if not 0 <= imm20 <= 0xFFFFF:
        raise ValueError(
            f"LUI imm20 must fit 20 bits, got {imm20:#x}"
        )

    return (imm20 << 12) | (rd << 7) | OP_LUI


def auipc(rd: int, imm20: int) -> int:
    rd = _reg(rd)

    if not 0 <= imm20 <= 0xFFFFF:
        raise ValueError(
            f"AUIPC imm20 must fit 20 bits, got {imm20:#x}"
        )

    return (imm20 << 12) | (rd << 7) | OP_AUIPC


def jalr(rd: int, rs1: int, imm: int) -> int:
    rd = _reg(rd)
    rs1 = _reg(rs1)
    imm12 = _signed_imm(imm, 12)

    return (
        (imm12 << 20)
        | (rs1 << 15)
        | (0b000 << 12)
        | (rd << 7)
        | OP_JALR
    )


def jal(rd: int, offset: int) -> int:
    """
    Encode JAL with signed PC-relative byte offset.

    J-immediate is 21-bit signed and must be 2-byte aligned.
    """
    rd = _reg(rd)
    imm21 = _signed_imm(offset, 21, alignment=2)

    bit20 = (imm21 >> 20) & 0x1
    bits10_1 = (imm21 >> 1) & 0x3FF
    bit11 = (imm21 >> 11) & 0x1
    bits19_12 = (imm21 >> 12) & 0xFF

    return (
        (bit20 << 31)
        | (bits10_1 << 21)
        | (bit11 << 20)
        | (bits19_12 << 12)
        | (rd << 7)
        | OP_JAL
    )

def beq(rs1: int, rs2: int, offset: int) -> int:
    return _branch(rs1, rs2, offset, 0b000)


def bne(rs1: int, rs2: int, offset: int) -> int:
    return _branch(rs1, rs2, offset, 0b001)


def blt(rs1: int, rs2: int, offset: int) -> int:
    return _branch(rs1, rs2, offset, 0b100)


def bge(rs1: int, rs2: int, offset: int) -> int:
    return _branch(rs1, rs2, offset, 0b101)


def bltu(rs1: int, rs2: int, offset: int) -> int:
    return _branch(rs1, rs2, offset, 0b110)


def bgeu(rs1: int, rs2: int, offset: int) -> int:
    return _branch(rs1, rs2, offset, 0b111)

def nop() -> int:
    return addi(0, 0, 0)


def word_to_le_bytes(word: int) -> List[int]:
    if not 0 <= word <= 0xFFFFFFFF:
        raise ValueError(f"word must fit 32 bits, got {word:#x}")

    return [
        (word >> 0) & 0xFF,
        (word >> 8) & 0xFF,
        (word >> 16) & 0xFF,
        (word >> 24) & 0xFF,
    ]


def words_to_hex_text(words: Iterable[int]) -> str:
    lines = []

    for word in words:
        for byte in word_to_le_bytes(word):
            lines.append(f"{byte:02x}")

    return "\n".join(lines) + "\n"


def write_instruction_hex(
    path: str | Path,
    words: Iterable[int],
) -> None:
    path = Path(path)
    path.write_text(words_to_hex_text(words))
