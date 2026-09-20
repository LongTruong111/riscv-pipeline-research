from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from research.week5.impl.architectural_model import (
    ArchitecturalStep,
    RV32ArchitecturalModel,
)
from research.week5.impl.execution_event import ExecutionEvent


@dataclass(frozen=True, slots=True)
class ExpectedRetire:
    """
    Architectural retire expectation.

    This object intentionally contains no cycle timing information.
    Timing prediction is owned by the Timing Oracle.
    """

    instruction_id: int
    pc: int
    instruction: int
    next_pc: int

    regwrite: bool
    rd: Optional[int]
    wdata: Optional[int]

    store_address: Optional[int]
    store_data: Optional[int]
    store_width_bytes: Optional[int]

    @classmethod
    def from_architectural_step(
        cls,
        step: ArchitecturalStep,
    ) -> "ExpectedRetire":
        reg = step.register_write
        store = step.store

        return cls(
            instruction_id=step.instruction_index,
            pc=step.pc,
            instruction=step.instruction,
            next_pc=step.next_pc,

            regwrite=reg is not None,
            rd=None if reg is None else reg.rd,
            wdata=None if reg is None else reg.value,

            store_address=None if store is None else store.address,
            store_data=None if store is None else store.data,
            store_width_bytes=(
                None if store is None else store.width_bytes
            ),
        )


def build_expected_retire_log(
    events: Iterable[ExecutionEvent],
) -> Tuple[ExpectedRetire, ...]:
    """
    Execute events through the Golden Functional Model and produce
    their expected in-order retire log.

    A PC mismatch is rejected because such an event stream is not a
    self-consistent architectural execution trace.
    """

    model = RV32ArchitecturalModel()
    result = []

    for event in events:
        step = model.step(event)

        if not step.pc_match:
            raise ValueError(
                "architectural PC mismatch while building retire log: "
                f"instruction_id={event.instruction_index}, "
                f"expected_pc={step.expected_pc:#x}, "
                f"observed_pc={event.pc:#x}"
            )

        result.append(
            ExpectedRetire.from_architectural_step(step)
        )

    return tuple(result)
