from dataclasses import dataclass
from typing import Optional


OP_R = 0b0110011
OP_LOAD = 0b0000011
OP_STORE = 0b0100011
OP_IMM = 0b0010011
OP_BRANCH = 0b1100011
OP_JAL = 0b1101111
OP_JALR = 0b1100111
OP_LUI = 0b0110111
OP_AUIPC = 0b0010111

def _sign_extend(value: int, bits: int) -> int:
    sign_bit = 1 << (bits - 1)
    mask = (1 << bits) - 1
    value &= mask

    if value & sign_bit:
        value -= 1 << bits

    return value


def _decode_i_imm(instruction: int) -> int:
    return _sign_extend(instruction >> 20, 12)


def _decode_b_imm(instruction: int) -> int:
    raw = (
        (((instruction >> 31) & 0x1) << 12)
        | (((instruction >> 7) & 0x1) << 11)
        | (((instruction >> 25) & 0x3F) << 5)
        | (((instruction >> 8) & 0xF) << 1)
    )

    return _sign_extend(raw, 13)

@dataclass(frozen=True, slots=True)
class DecodedInstruction:
    opcode: int

    rs1: int
    rs2: int
    rd: int

    uses_rs1: bool
    uses_rs2: bool
    writes_rd: bool

    producer_type: str
    consumer_type: str

    mnemonic: str = "UNKNOWN"
    funct3: int = 0
    funct7: int = 0
    imm: int | None = None
def decode_instruction(instruction: int) -> Optional[DecodedInstruction]:
    """
    Decode structural source/destination semantics needed by the hazard model.

    This decoder intentionally classifies the opcode families implemented by
    the frozen Controller RTL.

    Fine-grained funct3/funct7 legality remains a generator/ISA-subset
    responsibility and is not inferred here.
    """
    if not 0 <= instruction <= 0xFFFFFFFF:
        raise ValueError("instruction must fit 32 bits")

    opcode = instruction & 0x7F
    rd = (instruction >> 7) & 0x1F
    rs1 = (instruction >> 15) & 0x1F
    rs2 = (instruction >> 20) & 0x1F
    funct3 = (instruction >> 12) & 0x7
    funct7 = (instruction >> 25) & 0x7F

    if opcode == OP_R:
        if funct3 == 0b000 and funct7 == 0b0000000:
            mnemonic = "ADD"
        else:
            return None

        return DecodedInstruction(
            opcode, rs1, rs2, rd,
            True, True, True,
            "ALU_RESULT", "RS1_RS2",
            mnemonic, funct3, funct7, None,
        )
    if opcode == OP_LOAD:
        return DecodedInstruction(
            opcode, rs1, rs2, rd,
            True, False, True,
            "MEM_DATA", "RS1_ONLY",
        )

    if opcode == OP_STORE:
        return DecodedInstruction(
            opcode, rs1, rs2, rd,
            True, True, False,
            "NONE", "RS1_RS2",
        )

    if opcode == OP_IMM:
        if funct3 == 0b000:
            mnemonic = "ADDI"
        else:
            return None

        return DecodedInstruction(
            opcode, rs1, rs2, rd,
            True, False, True,
            "ALU_RESULT", "RS1_ONLY",
            mnemonic, funct3, funct7,
            _decode_i_imm(instruction),
        )

    if opcode == OP_BRANCH:
        branch_mnemonics = {
            0b000: "BEQ",
            0b001: "BNE",
            0b100: "BLT",
            0b101: "BGE",
            0b110: "BLTU",
            0b111: "BGEU",
        }

        mnemonic = branch_mnemonics.get(funct3)

        if mnemonic is None:
            return None

        return DecodedInstruction(
            opcode, rs1, rs2, rd,
            True, True, False,
            "NONE", "RS1_RS2",
            mnemonic, funct3, funct7,
            _decode_b_imm(instruction),
        )
    if opcode == OP_JAL:
        return DecodedInstruction(
            opcode, rs1, rs2, rd,
            False, False, True,
            "PC_PLUS_4", "NO_GPR_SOURCE",
        )

    if opcode == OP_JALR:
        return DecodedInstruction(
            opcode, rs1, rs2, rd,
            True, False, True,
            "PC_PLUS_4", "RS1_ONLY",
        )

    if opcode == OP_LUI:
        return DecodedInstruction(
            opcode, rs1, rs2, rd,
            False, False, True,
            "IMM", "NO_GPR_SOURCE",
        )

    if opcode == OP_AUIPC:
        return DecodedInstruction(
            opcode, rs1, rs2, rd,
            False, False, True,
            "PC_PLUS_IMM", "NO_GPR_SOURCE",
        )

    return None
