from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .execution_event import ExecutionEvent


MASK32 = 0xFFFFFFFF

OP_R = 0b0110011
OP_IMM = 0b0010011
OP_LOAD = 0b0000011
OP_STORE = 0b0100011
OP_BRANCH = 0b1100011
OP_JAL = 0b1101111
OP_JALR = 0b1100111
OP_LUI = 0b0110111
OP_AUIPC = 0b0010111


class UnsupportedArchitecturalInstruction(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExpectedRegisterWrite:
    instruction_index: int
    rd: int
    value: int


@dataclass(frozen=True, slots=True)
class ExpectedStore:
    instruction_index: int
    address: int
    data: int
    width_bytes: int = 4


@dataclass(frozen=True, slots=True)
class ArchitecturalStep:
    instruction_index: int
    pc: int
    instruction: int

    expected_pc: int
    pc_match: bool
    next_pc: int

    register_write: Optional[ExpectedRegisterWrite]
    store: Optional[ExpectedStore]


def _sign_extend(value: int, bits: int) -> int:
    sign_bit = 1 << (bits - 1)
    mask = (1 << bits) - 1

    value &= mask

    if value & sign_bit:
        value -= 1 << bits

    return value

def _signed32(value: int) -> int:
    return _sign_extend(value & MASK32, 32)

def _decode_i_imm(instruction: int) -> int:
    return _sign_extend(
        instruction >> 20,
        12,
    )

def _decode_b_imm(instruction: int) -> int:
    raw = (
        (((instruction >> 31) & 0x1) << 12)
        | (((instruction >> 7) & 0x1) << 11)
        | (((instruction >> 25) & 0x3F) << 5)
        | (((instruction >> 8) & 0xF) << 1)
    )

    return _sign_extend(raw, 13)

def _decode_s_imm(instruction: int) -> int:
    raw = (
        ((instruction >> 25) & 0x7F) << 5
    ) | (
        (instruction >> 7) & 0x1F
    )

    return _sign_extend(raw, 12)


def _decode_u_imm(instruction: int) -> int:
    return instruction & 0xFFFFF000


def _decode_j_imm(instruction: int) -> int:
    raw = (
        (((instruction >> 31) & 0x1) << 20)
        | (((instruction >> 12) & 0xFF) << 12)
        | (((instruction >> 20) & 0x1) << 11)
        | (((instruction >> 21) & 0x3FF) << 1)
    )

    return _sign_extend(raw, 21)


class RV32ArchitecturalModel:
    """
    Independent sequential architectural oracle for the instruction subset
    required by the frozen Week-5 H01-H20 directed campaign.

    Supported semantics:
      - ADD
      - ADDI
      - LW
      - SW
      - LUI
      - AUIPC
      - JAL
      - JALR

    Architectural x0 is permanently zero.

    Memory is byte-addressed and initially zero, matching the frozen
    ramOnChipData initialization contract.
    """

    def __init__(self) -> None:
        self._registers = [0] * 32
        self._memory: Dict[int, int] = {}

        self.expected_pc = 0
        self._last_instruction_index = 0

    def reset(self) -> None:
        self._registers = [0] * 32
        self._memory.clear()

        self.expected_pc = 0
        self._last_instruction_index = 0

    def read_register(self, register: int) -> int:
        if not 0 <= register <= 31:
            raise ValueError(
                f"register must be x0..x31, got x{register}"
            )

        if register == 0:
            return 0

        return self._registers[register] & MASK32

    def registers(self) -> Tuple[int, ...]:
        result = list(self._registers)
        result[0] = 0
        return tuple(value & MASK32 for value in result)

    def _write_register(
        self,
        register: int,
        value: int,
    ) -> None:
        if not 0 <= register <= 31:
            raise ValueError(
                f"register must be x0..x31, got x{register}"
            )

        if register == 0:
            return

        self._registers[register] = value & MASK32

    def _read_byte(self, address: int) -> int:
        return self._memory.get(
            address & MASK32,
            0,
        )

    def _write_byte(
        self,
        address: int,
        value: int,
    ) -> None:
        self._memory[address & MASK32] = value & 0xFF

    def read_word(self, address: int) -> int:
        address &= MASK32

        return (
            self._read_byte(address)
            | (self._read_byte(address + 1) << 8)
            | (self._read_byte(address + 2) << 16)
            | (self._read_byte(address + 3) << 24)
        ) & MASK32

    def _write_word(
        self,
        address: int,
        value: int,
    ) -> None:
        address &= MASK32
        value &= MASK32

        self._write_byte(address + 0, value >> 0)
        self._write_byte(address + 1, value >> 8)
        self._write_byte(address + 2, value >> 16)
        self._write_byte(address + 3, value >> 24)

    def _check_event_order(
        self,
        event: ExecutionEvent,
    ) -> None:
        expected_index = self._last_instruction_index + 1

        if event.instruction_index != expected_index:
            raise ValueError(
                "Architectural model requires contiguous executed "
                f"instruction order: expected {expected_index}, "
                f"got {event.instruction_index}"
            )

    def step(
        self,
        event: ExecutionEvent,
    ) -> ArchitecturalStep:
        self._check_event_order(event)

        instruction = event.instruction
        opcode = instruction & 0x7F

        rd = (instruction >> 7) & 0x1F
        funct3 = (instruction >> 12) & 0x7
        rs1 = (instruction >> 15) & 0x1F
        rs2 = (instruction >> 20) & 0x1F
        funct7 = (instruction >> 25) & 0x7F

        current_expected_pc = self.expected_pc
        pc_match = event.pc == current_expected_pc

        next_pc = (event.pc + 4) & MASK32

        expected_reg_write: Optional[
            ExpectedRegisterWrite
        ] = None

        expected_store: Optional[
            ExpectedStore
        ] = None

        result_value: Optional[int] = None

        # ----------------------------------------------------------
        # R-type ADD
        # ----------------------------------------------------------
        if opcode == OP_R:
            if funct3 != 0b000 or funct7 != 0b0000000:
                raise UnsupportedArchitecturalInstruction(
                    "Week-5 architectural model currently supports "
                    "only ADD for R-type instructions"
                )

            result_value = (
                self.read_register(rs1)
                + self.read_register(rs2)
            ) & MASK32

        # ----------------------------------------------------------
        # ADDI
        # ----------------------------------------------------------
        elif opcode == OP_IMM:
            if funct3 != 0b000:
                raise UnsupportedArchitecturalInstruction(
                    "Week-5 architectural model currently supports "
                    "only ADDI for OP-IMM instructions"
                )

            immediate = _decode_i_imm(instruction)

            result_value = (
                self.read_register(rs1)
                + immediate
            ) & MASK32

        # ----------------------------------------------------------
        # LW
        # ----------------------------------------------------------
        elif opcode == OP_LOAD:
            if funct3 != 0b010:
                raise UnsupportedArchitecturalInstruction(
                    "Week-5 architectural model currently supports "
                    "only LW"
                )

            address = (
                self.read_register(rs1)
                + _decode_i_imm(instruction)
            ) & MASK32

            result_value = self.read_word(address)

        # ----------------------------------------------------------
        # SW
        # ----------------------------------------------------------
        elif opcode == OP_STORE:
            if funct3 != 0b010:
                raise UnsupportedArchitecturalInstruction(
                    "Week-5 architectural model currently supports "
                    "only SW"
                )

            address = (
                self.read_register(rs1)
                + _decode_s_imm(instruction)
            ) & MASK32

            data = self.read_register(rs2)

            self._write_word(
                address,
                data,
            )

            expected_store = ExpectedStore(
                instruction_index=event.instruction_index,
                address=address,
                data=data,
            )

        # ----------------------------------------------------------
        # BRANCH
        # ----------------------------------------------------------
        elif opcode == OP_BRANCH:
            lhs = self.read_register(rs1)
            rhs = self.read_register(rs2)

            if funct3 == 0b000:      # BEQ
                taken = lhs == rhs

            elif funct3 == 0b001:    # BNE
                taken = lhs != rhs

            elif funct3 == 0b100:    # BLT
                taken = _signed32(lhs) < _signed32(rhs)

            elif funct3 == 0b101:    # BGE
                taken = _signed32(lhs) >= _signed32(rhs)

            elif funct3 == 0b110:    # BLTU
                taken = lhs < rhs

            elif funct3 == 0b111:    # BGEU
                taken = lhs >= rhs

            else:
                raise UnsupportedArchitecturalInstruction(
                    f"unsupported BRANCH funct3 {funct3:#05b}"
                )

            if taken:
                next_pc = (
                    event.pc
                    + _decode_b_imm(instruction)
                ) & MASK32

        # ----------------------------------------------------------
        # LUI
        # ----------------------------------------------------------
        elif opcode == OP_LUI:
            result_value = _decode_u_imm(
                instruction
            )

        # ----------------------------------------------------------
        # AUIPC
        # ----------------------------------------------------------
        elif opcode == OP_AUIPC:
            result_value = (
                event.pc
                + _decode_u_imm(instruction)
            ) & MASK32

        # ----------------------------------------------------------
        # JAL
        # ----------------------------------------------------------
        elif opcode == OP_JAL:
            result_value = (
                event.pc + 4
            ) & MASK32

            next_pc = (
                event.pc
                + _decode_j_imm(instruction)
            ) & MASK32

        # ----------------------------------------------------------
        # JALR
        # ----------------------------------------------------------
        elif opcode == OP_JALR:
            if funct3 != 0b000:
                raise UnsupportedArchitecturalInstruction(
                    "JALR funct3 must be 000"
                )

            result_value = (
                event.pc + 4
            ) & MASK32

            target = (
                self.read_register(rs1)
                + _decode_i_imm(instruction)
            ) & MASK32

            # RV32 architectural rule:
            # target address bit 0 is always cleared.
            next_pc = target & ~1

        else:
            raise UnsupportedArchitecturalInstruction(
                f"unsupported opcode {opcode:#04x}"
            )

        # ----------------------------------------------------------
        # Architectural register write
        # ----------------------------------------------------------
        if result_value is not None:
            result_value &= MASK32

            self._write_register(
                rd,
                result_value,
            )

            if rd != 0:
                expected_reg_write = ExpectedRegisterWrite(
                    instruction_index=event.instruction_index,
                    rd=rd,
                    value=result_value,
                )

        # Architectural x0 invariant.
        self._registers[0] = 0

        self.expected_pc = next_pc
        self._last_instruction_index = event.instruction_index

        return ArchitecturalStep(
            instruction_index=event.instruction_index,
            pc=event.pc,
            instruction=instruction,
            expected_pc=current_expected_pc,
            pc_match=pc_match,
            next_pc=next_pc,
            register_write=expected_reg_write,
            store=expected_store,
        )
