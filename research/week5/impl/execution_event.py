from dataclasses import dataclass
from typing import Tuple


def _check_reg(name: str, value: int) -> None:
    if not 0 <= value <= 31:
        raise ValueError(f"{name} must be in [0, 31], got {value}")


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    """
    One accepted architectural instruction in executed-program order.

    An event exists only after an instruction is accepted from IF/ID (A)
    into ID/EX (B).

    A stalled instruction creates no event until it is eventually accepted.
    A flushed instruction creates no event at all.
    """

    instruction_index: int
    cycle: int

    pc: int
    instruction: int

    rs1: int
    rs2: int
    rd: int

    uses_rs1: bool
    uses_rs2: bool
    writes_rd: bool

    producer_type: str
    consumer_type: str

    # Number of immediately preceding stall cycles experienced by this
    # instruction while resident in IF/ID before acceptance.
    stall_cycles_before_accept: int = 0

    # Settled EX forwarding controls after this instruction enters ID/EX.
    forward_a: int = 0
    forward_b: int = 0

    def __post_init__(self) -> None:
        if self.instruction_index <= 0:
            raise ValueError(
                f"instruction_index must be positive, "
                f"got {self.instruction_index}"
            )

        if self.cycle < 0:
            raise ValueError(f"cycle must be non-negative, got {self.cycle}")

        if not 0 <= self.pc <= 0x1FF:
            raise ValueError(f"pc must fit 9 bits, got {self.pc:#x}")

        if not 0 <= self.instruction <= 0xFFFFFFFF:
            raise ValueError(
                f"instruction must fit 32 bits, got {self.instruction:#x}"
            )

        _check_reg("rs1", self.rs1)
        _check_reg("rs2", self.rs2)
        _check_reg("rd", self.rd)

        if self.stall_cycles_before_accept < 0:
            raise ValueError("stall_cycles_before_accept must be >= 0")

        if not 0 <= self.forward_a <= 0b11:
            raise ValueError("forward_a must be a 2-bit value")

        if not 0 <= self.forward_b <= 0b11:
            raise ValueError("forward_b must be a 2-bit value")

    def architectural_sources(self) -> Tuple[int, ...]:
        sources = []

        if self.uses_rs1:
            sources.append(self.rs1)

        if self.uses_rs2 and self.rs2 not in sources:
            sources.append(self.rs2)

        return tuple(sources)
