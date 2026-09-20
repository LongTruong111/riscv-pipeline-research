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

    if opcode == OP_R:
        return DecodedInstruction(
            opcode, rs1, rs2, rd,
            True, True, True,
            "ALU_RESULT", "RS1_RS2",
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
        return DecodedInstruction(
            opcode, rs1, rs2, rd,
            True, False, True,
            "ALU_RESULT", "RS1_ONLY",
        )

    if opcode == OP_BRANCH:
        return DecodedInstruction(
            opcode, rs1, rs2, rd,
            True, True, False,
            "NONE", "RS1_RS2",
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
