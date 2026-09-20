from dataclasses import dataclass
from typing import Optional, Tuple

from .execution_event import ExecutionEvent
from .isa_decode import DecodedInstruction, decode_instruction


@dataclass(frozen=True, slots=True)
class PreEdgeSnapshot:
    """
    Stable IF/ID + control state sampled before the active edge.

    Intended sampling point:

        FallingEdge(clk)
        -> ReadOnly()
    """

    cycle: int
    reset: bool
    stall: bool
    flush_redirect: bool

    pc: int
    instruction: int


@dataclass(frozen=True, slots=True)
class PendingAdmission:
    """
    Instruction determined to be accepted into ID/EX at the next rising edge.
    """

    cycle: int
    pc: int
    instruction: int
    decoded: DecodedInstruction
    stall_cycles_before_accept: int


class ExecutionEventAdapter:
    """
    Reconstruct the executed instruction stream from IF/ID admission.

    Admission rule:

        reset == 0
        AND stall == 0
        AND flush_redirect == 0
        AND instruction belongs to the supported structural ISA domain

    A stall cycle does not create an ExecutionEvent.
    A flushed instruction never creates an ExecutionEvent.
    """

    def __init__(self) -> None:
        self._instruction_index = 0

        # Track the instruction retained in IF/ID across stall cycles.
        self._stalled_identity: Optional[Tuple[int, int]] = None
        self._stall_count = 0

    @property
    def instruction_count(self) -> int:
        return self._instruction_index

    def reset(self) -> None:
        self._instruction_index = 0
        self._stalled_identity = None
        self._stall_count = 0

    def observe_pre_edge(
        self,
        snapshot: PreEdgeSnapshot,
    ) -> Optional[PendingAdmission]:
        """
        Process settled pre-edge control state.

        Return PendingAdmission only when the IF/ID instruction is allowed
        to enter ID/EX on the upcoming rising edge.
        """

        if snapshot.cycle < 0:
            raise ValueError("cycle must be non-negative")

        if not 0 <= snapshot.pc <= 0x1FF:
            raise ValueError("pc must fit the frozen 9-bit PC")

        if not 0 <= snapshot.instruction <= 0xFFFFFFFF:
            raise ValueError("instruction must fit 32 bits")

        # Reset invalidates current IF/ID contents.
        if snapshot.reset:
            self._clear_stall_history()
            return None

        # PcSel causes IF/ID flush and ID/EX bubble injection.
        if snapshot.flush_redirect:
            self._clear_stall_history()
            return None

        decoded = decode_instruction(snapshot.instruction)

        # Unsupported opcode is not part of the frozen generated ISA stream.
        if decoded is None:
            self._clear_stall_history()
            return None

        identity = (snapshot.pc, snapshot.instruction)

        if snapshot.stall:
            if self._stalled_identity == identity:
                self._stall_count += 1
            else:
                self._stalled_identity = identity
                self._stall_count = 1

            return None

        stall_count = 0

        if self._stalled_identity == identity:
            stall_count = self._stall_count

        self._clear_stall_history()

        return PendingAdmission(
            cycle=snapshot.cycle,
            pc=snapshot.pc,
            instruction=snapshot.instruction,
            decoded=decoded,
            stall_cycles_before_accept=stall_count,
        )

    def finalize_post_edge(
        self,
        pending: PendingAdmission,
        *,
        forward_a: int,
        forward_b: int,
    ) -> ExecutionEvent:
        """
        Finalize the accepted instruction after the active edge.

        Intended sampling point:

            RisingEdge(clk)
            -> ReadOnly()

        At this point ID/EX contains the accepted instruction and the
        forwarding selects are settled for that instruction's EX inputs.
        """

        if not 0 <= forward_a <= 0b11:
            raise ValueError("forward_a must be a 2-bit value")

        if not 0 <= forward_b <= 0b11:
            raise ValueError("forward_b must be a 2-bit value")

        self._instruction_index += 1

        decoded = pending.decoded

        return ExecutionEvent(
            instruction_index=self._instruction_index,
            cycle=pending.cycle,
            pc=pending.pc,
            instruction=pending.instruction,
            rs1=decoded.rs1,
            rs2=decoded.rs2,
            rd=decoded.rd,
            uses_rs1=decoded.uses_rs1,
            uses_rs2=decoded.uses_rs2,
            writes_rd=decoded.writes_rd,
            producer_type=decoded.producer_type,
            consumer_type=decoded.consumer_type,
            stall_cycles_before_accept=pending.stall_cycles_before_accept,
            forward_a=forward_a,
            forward_b=forward_b,
        )

    def _clear_stall_history(self) -> None:
        self._stalled_identity = None
        self._stall_count = 0
