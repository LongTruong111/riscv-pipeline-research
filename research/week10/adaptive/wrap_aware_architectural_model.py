"""Week-10 physical-PC wrapper for the frozen RV32 architectural model.

The DUT has a 9-bit instruction-fetch PC:

    physical_fetch_pc = architectural_target & 0x1ff

However, control-flow result values are computed from a zero-extended
9-bit current PC in 32-bit arithmetic. In particular, JAL/JALR executed
at PC 0x1fc write link value 0x200, while the next physical fetch wraps
according to the low 9 bits.

This module deliberately does not modify the frozen Week-5 model.
"""

from dataclasses import replace

from research.week5.impl.architectural_model import (
    ArchitecturalStep,
    RV32ArchitecturalModel,
)
from research.week5.impl.execution_event import ExecutionEvent


DEFAULT_FETCH_PC_WIDTH = 9


class WrapAwareRV32ArchitecturalModel(
    RV32ArchitecturalModel
):
    """RV32 model with DUT-accurate bounded physical fetch PC.

    Architectural register and memory semantics are inherited unchanged
    from the frozen Week-5 model.

    Only the *next instruction-fetch PC* is truncated to the configured
    physical PC width after every architectural step.
    """

    def __init__(
        self,
        *,
        pc_width: int = DEFAULT_FETCH_PC_WIDTH,
    ) -> None:
        if pc_width <= 0:
            raise ValueError(
                "pc_width must be positive"
            )

        if pc_width > 32:
            raise ValueError(
                "pc_width must not exceed 32"
            )

        super().__init__()

        self._physical_pc_width = pc_width
        self._physical_pc_mask = (
            (1 << pc_width) - 1
        )

    @property
    def physical_pc_width(self) -> int:
        return self._physical_pc_width

    @property
    def physical_pc_mask(self) -> int:
        return self._physical_pc_mask

    def normalize_fetch_pc(
        self,
        pc: int,
    ) -> int:
        if pc < 0:
            raise ValueError(
                "PC must be non-negative"
            )

        return pc & self._physical_pc_mask

    def step(
        self,
        event: ExecutionEvent,
    ) -> ArchitecturalStep:
        """Execute one instruction and normalize only next fetch PC.

        Important distinction:

        * register/memory results remain full RV32 values;
        * JAL/JALR link values therefore remain PC+4 in 32-bit form;
        * branch/JAL/JALR next fetch addresses are truncated to the
          DUT physical instruction-PC width.
        """

        if not isinstance(
            event,
            ExecutionEvent,
        ):
            raise TypeError(
                "event must be an ExecutionEvent"
            )

        if (
            event.pc
            != self.normalize_fetch_pc(
                event.pc
            )
        ):
            raise ValueError(
                "execution event PC is outside "
                "physical fetch-PC range: "
                f"pc={event.pc:#x}, "
                f"width={self._physical_pc_width}"
            )

        step = super().step(event)

        physical_next_pc = (
            self.normalize_fetch_pc(
                step.next_pc
            )
        )

        # The frozen parent model stores expected_pc internally as a
        # public scalar. Replace only that fetch-state value after its
        # full-width architectural calculations have completed.
        self.expected_pc = (
            physical_next_pc
        )

        return replace(
            step,
            next_pc=physical_next_pc,
        )
