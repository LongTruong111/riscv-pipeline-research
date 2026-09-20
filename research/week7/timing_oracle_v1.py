from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week5.impl.execution_event import ExecutionEvent
from research.week5.impl.isa_decode import (
    DecodedInstruction,
    decode_instruction,
)
from research.week6.timing_oracle import (
    FORWARD_EX_MEM,
    FORWARD_MEM_WB,
    FORWARD_RF,
)


MASK32 = 0xFFFFFFFF

REDIRECT_BUBBLES = 2
RETIRE_LATENCY = 3

_T6_MNEMONICS = {
    "ADD",
    "ADDI",
    "LW",
    "SW",
    "LUI",
    "AUIPC",
    "JAL",
    "JALR",
    "BEQ",
    "BNE",
    "BLT",
    "BGE",
    "BLTU",
    "BGEU",
}

_BRANCH_MNEMONICS = {
    "BEQ",
    "BNE",
    "BLT",
    "BGE",
    "BLTU",
    "BGEU",
}

_UNCONDITIONAL_REDIRECT = {
    "JAL",
    "JALR",
}


class UnsupportedTimingInstructionV1(ValueError):
    pass


class TimingProgramError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _Producer:
    instruction_id: int
    accept_cycle: int
    decoded: DecodedInstruction


@dataclass(frozen=True, slots=True)
class TimingExpectationV1:
    instruction_id: int
    pc: int
    instruction: int
    mnemonic: str

    accept_cycle: int
    stall_cycles_before_accept: int
    retire_cycle: int

    forward_a: int
    forward_b: int

    source_a_producer_id: Optional[int]
    source_b_producer_id: Optional[int]

    source_a_cycle_age: Optional[int]
    source_b_cycle_age: Optional[int]

    redirect: bool
    redirect_bubbles: int


@dataclass(frozen=True, slots=True)
class TimingScheduleV1:
    expectations: Tuple[TimingExpectationV1, ...]

    @property
    def instruction_count(self) -> int:
        return len(self.expectations)

    @property
    def first_accept_cycle(self) -> Optional[int]:
        if not self.expectations:
            return None
        return self.expectations[0].accept_cycle

    @property
    def first_retire_cycle(self) -> Optional[int]:
        if not self.expectations:
            return None
        return self.expectations[0].retire_cycle

    @property
    def drain_cycle(self) -> Optional[int]:
        if not self.expectations:
            return None
        return self.expectations[-1].retire_cycle

    @property
    def total_stall_cycles(self) -> int:
        return sum(
            item.stall_cycles_before_accept
            for item in self.expectations
        )

    @property
    def total_redirect_bubbles(self) -> int:
        return sum(
            item.redirect_bubbles
            for item in self.expectations
        )


def _signed32(value: int) -> int:
    value &= MASK32
    if value & 0x80000000:
        return value - (1 << 32)
    return value


def _decode_checked(instruction: int) -> DecodedInstruction:
    decoded = decode_instruction(instruction)

    if decoded is None:
        raise UnsupportedTimingInstructionV1(
            f"unsupported instruction 0x{instruction:08x}"
        )

    if decoded.mnemonic not in _T6_MNEMONICS:
        raise UnsupportedTimingInstructionV1(
            "instruction is outside exact T6 timing subset: "
            f"0x{instruction:08x} -> {decoded.mnemonic}"
        )

    return decoded


def _branch_taken(
    decoded: DecodedInstruction,
    model: RV32ArchitecturalModel,
) -> bool:
    if decoded.mnemonic not in _BRANCH_MNEMONICS:
        return False

    lhs = model.read_register(decoded.rs1) & MASK32
    rhs = model.read_register(decoded.rs2) & MASK32

    if decoded.mnemonic == "BEQ":
        return lhs == rhs

    if decoded.mnemonic == "BNE":
        return lhs != rhs

    if decoded.mnemonic == "BLT":
        return _signed32(lhs) < _signed32(rhs)

    if decoded.mnemonic == "BGE":
        return _signed32(lhs) >= _signed32(rhs)

    if decoded.mnemonic == "BLTU":
        return lhs < rhs

    if decoded.mnemonic == "BGEU":
        return lhs >= rhs

    raise AssertionError(
        f"unreachable branch mnemonic {decoded.mnemonic}"
    )


def _forward_for_age(age: Optional[int]) -> int:
    if age is None:
        return FORWARD_RF

    if age <= 0:
        raise TimingProgramError(
            f"producer cycle age must be positive, got {age}"
        )

    if age == 1:
        return FORWARD_EX_MEM

    if age == 2:
        return FORWARD_MEM_WB

    return FORWARD_RF


def _execution_event(
    *,
    instruction_id: int,
    cycle: int,
    pc: int,
    instruction: int,
    decoded: DecodedInstruction,
) -> ExecutionEvent:
    return ExecutionEvent(
        instruction_index=instruction_id,
        cycle=cycle,
        pc=pc,
        instruction=instruction,
        rs1=decoded.rs1,
        rs2=decoded.rs2,
        rd=decoded.rd,
        uses_rs1=decoded.uses_rs1,
        uses_rs2=decoded.uses_rs2,
        writes_rd=decoded.writes_rd,
        producer_type=decoded.producer_type,
        consumer_type=decoded.consumer_type,
    )


def build_timing_schedule_v1(
    program: Mapping[int, int],
    *,
    max_instructions: int = 256,
) -> TimingScheduleV1:
    """
    Build expected admission/forwarding/redirect/retire timing.

    Program keys are architectural byte PCs.

    The oracle is independent from DUT-observed stall, forwarding and
    flush signals.

    Timing contract:
        first accepted instruction     : cycle 1
        normal next admission          : previous accept + 1
        load-use d1                    : exactly one extra stall cycle
        taken redirect/JAL/JALR        : two extra admission bubbles
        logical retirement             : accept cycle + 3

    Forwarding is determined by cycle age:

        age 1 -> EX/MEM
        age 2 -> MEM/WB
        age 3+ -> Register File

    A load consumer that would see load age 1 is delayed one cycle,
    therefore it is accepted at age 2 and expects MEM/WB forwarding.
    """

    if max_instructions <= 0:
        raise ValueError("max_instructions must be positive")

    normalized: Dict[int, int] = {}

    for pc, instruction in program.items():
        if pc < 0:
            raise ValueError("program PC must be non-negative")

        if pc & 0x3:
            raise ValueError(
                f"program PC must be 4-byte aligned, got {pc:#x}"
            )

        if not 0 <= instruction <= MASK32:
            raise ValueError(
                f"instruction at PC {pc:#x} does not fit 32 bits"
            )

        normalized[int(pc)] = int(instruction)

    if not normalized:
        return TimingScheduleV1(expectations=())

    if 0 not in normalized:
        raise TimingProgramError(
            "Timing Oracle v1 currently requires entry PC 0"
        )

    model = RV32ArchitecturalModel()

    # Latest architectural writer for each register.
    last_writer: Dict[int, _Producer] = {}

    expectations = []

    pc = 0
    instruction_id = 1
    next_accept_cycle = 1

    while pc in normalized:
        if instruction_id > max_instructions:
            raise TimingProgramError(
                "max_instructions reached; possible control-flow loop"
            )

        instruction = normalized[pc]
        decoded = _decode_checked(instruction)

        # ----------------------------------------------------------
        # Resolve semantic RAW dependencies.
        # ----------------------------------------------------------
        producer_a = None
        producer_b = None

        if decoded.uses_rs1 and decoded.rs1 != 0:
            producer_a = last_writer.get(decoded.rs1)

        if decoded.uses_rs2 and decoded.rs2 != 0:
            producer_b = last_writer.get(decoded.rs2)

        candidate_cycle = next_accept_cycle

        # ----------------------------------------------------------
        # Load-use interlock.
        #
        # Stall is required only if a semantic source would consume a
        # LOAD result one cycle after that LOAD was accepted.
        # ----------------------------------------------------------
        needs_load_stall = False

        for producer in (producer_a, producer_b):
            if producer is None:
                continue

            age_before_stall = (
                candidate_cycle - producer.accept_cycle
            )

            if (
                producer.decoded.producer_type == "MEM_DATA"
                and age_before_stall == 1
            ):
                needs_load_stall = True

        stall_cycles = 1 if needs_load_stall else 0
        accept_cycle = candidate_cycle + stall_cycles

        source_a_age = (
            None
            if producer_a is None
            else accept_cycle - producer_a.accept_cycle
        )

        source_b_age = (
            None
            if producer_b is None
            else accept_cycle - producer_b.accept_cycle
        )

        forward_a = _forward_for_age(source_a_age)
        forward_b = _forward_for_age(source_b_age)

        # A LOAD result must never be consumed at age 1.
        for role, producer, age in (
            ("RS1", producer_a, source_a_age),
            ("RS2", producer_b, source_b_age),
        ):
            if (
                producer is not None
                and producer.decoded.producer_type == "MEM_DATA"
                and age == 1
            ):
                raise TimingProgramError(
                    f"{role}: unresolved load-use hazard"
                )

        # ----------------------------------------------------------
        # Compute control-flow intent from independent architectural
        # state BEFORE stepping the instruction.
        # ----------------------------------------------------------
        if decoded.mnemonic in _UNCONDITIONAL_REDIRECT:
            redirect = True
        elif decoded.mnemonic in _BRANCH_MNEMONICS:
            redirect = _branch_taken(decoded, model)
        else:
            redirect = False

        redirect_bubbles = (
            REDIRECT_BUBBLES
            if redirect
            else 0
        )

        # ----------------------------------------------------------
        # Independent functional model advances architectural state
        # and determines the next executed PC.
        # ----------------------------------------------------------
        event = _execution_event(
            instruction_id=instruction_id,
            cycle=accept_cycle,
            pc=pc,
            instruction=instruction,
            decoded=decoded,
        )

        model.step(event)

        expectations.append(
            TimingExpectationV1(
                instruction_id=instruction_id,
                pc=pc,
                instruction=instruction,
                mnemonic=decoded.mnemonic,
                accept_cycle=accept_cycle,
                stall_cycles_before_accept=stall_cycles,
                retire_cycle=accept_cycle + RETIRE_LATENCY,
                forward_a=forward_a,
                forward_b=forward_b,
                source_a_producer_id=(
                    None
                    if producer_a is None
                    else producer_a.instruction_id
                ),
                source_b_producer_id=(
                    None
                    if producer_b is None
                    else producer_b.instruction_id
                ),
                source_a_cycle_age=source_a_age,
                source_b_cycle_age=source_b_age,
                redirect=redirect,
                redirect_bubbles=redirect_bubbles,
            )
        )

        # Writer becomes visible to subsequent timing analysis only
        # after current dependency resolution is complete.
        if decoded.writes_rd and decoded.rd != 0:
            last_writer[decoded.rd] = _Producer(
                instruction_id=instruction_id,
                accept_cycle=accept_cycle,
                decoded=decoded,
            )

        pc = model.expected_pc

        next_accept_cycle = (
            accept_cycle
            + 1
            + redirect_bubbles
        )

        instruction_id += 1

    return TimingScheduleV1(
        expectations=tuple(expectations)
    )
