from dataclasses import dataclass
from typing import Optional, Tuple

from research.week5.impl.execution_event import ExecutionEvent


MASK32 = 0xFFFFFFFF


class RetireProtocolError(RuntimeError):
    """Raised when the observed retire stream violates its protocol."""


@dataclass(frozen=True, slots=True)
class RetireTag:
    """
    Verification-side identity carried through B/C/D.

    This is not a DUT signal and does not alter DUT behavior.
    """

    instruction_id: int
    pc: int
    instruction: int

    def __post_init__(self) -> None:
        if self.instruction_id <= 0:
            raise ValueError("instruction_id must be positive")

        if self.pc < 0:
            raise ValueError("pc must be non-negative")

        if not 0 <= self.instruction <= MASK32:
            raise ValueError("instruction must fit 32 bits")

    @classmethod
    def from_execution_event(
        cls,
        event: ExecutionEvent,
    ) -> "RetireTag":
        return cls(
            instruction_id=event.instruction_index,
            pc=event.pc,
            instruction=event.instruction,
        )


@dataclass(frozen=True, slots=True)
class RetireEvent:
    """
    One logically retired instruction.

    cycle:
        Falling-edge observation cycle.

    valid:
        Always True for an emitted RetireEvent. Bubbles do not emit events.

    regwrite / rd / wdata:
        Observed MEM/WB writeback state. regwrite=False remains valid for
        instructions such as stores and branches.

    instruction_id:
        Executed-program-order identity propagated by verification-side tags.
    """

    cycle: int
    valid: bool

    regwrite: bool
    rd: int
    wdata: int

    instruction_id: int

    def __post_init__(self) -> None:
        if self.cycle < 0:
            raise ValueError("cycle must be non-negative")

        if not self.valid:
            raise ValueError(
                "RetireEvent represents only valid retirement"
            )

        if not 0 <= self.rd <= 31:
            raise ValueError("rd must be in [0, 31]")

        if not 0 <= self.wdata <= MASK32:
            raise ValueError("wdata must fit 32 bits")

        if self.instruction_id <= 0:
            raise ValueError("instruction_id must be positive")


class RetireMonitor:
    """
    Verification-side retire monitor for the frozen five-stage DUT.

    Pipeline tag movement at RisingEdge:

        old C -> new D
        old B -> new C
        accepted A -> new B

    Retirement observation occurs at FallingEdge using the current D tag.

    Important:
        - RegWrite is NOT a valid bit.
        - Curr_Instr is NOT a valid bit.
        - A stall/flush injects no accepted tag.
        - Stores/branches may retire with regwrite=False.
    """

    def __init__(self) -> None:
        self._b_tag: Optional[RetireTag] = None
        self._c_tag: Optional[RetireTag] = None
        self._d_tag: Optional[RetireTag] = None

        self._last_retired_instruction_id = 0
        self._retired_count = 0

    def reset(self) -> None:
        self._b_tag = None
        self._c_tag = None
        self._d_tag = None

        self._last_retired_instruction_id = 0
        self._retired_count = 0

    @property
    def retired_count(self) -> int:
        return self._retired_count

    @property
    def b_tag(self) -> Optional[RetireTag]:
        return self._b_tag

    @property
    def c_tag(self) -> Optional[RetireTag]:
        return self._c_tag

    @property
    def d_tag(self) -> Optional[RetireTag]:
        return self._d_tag

    @property
    def stage_instruction_ids(
        self,
    ) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        def tag_id(tag: Optional[RetireTag]) -> Optional[int]:
            return None if tag is None else tag.instruction_id

        return (
            tag_id(self._b_tag),
            tag_id(self._c_tag),
            tag_id(self._d_tag),
        )

    def advance_pipeline(
        self,
        accepted: Optional[RetireTag],
    ) -> None:
        """
        Advance verification-side identity after RisingEdge + ReadOnly.

        accepted=None represents no newly accepted instruction:
        stall, flush, reset bubble, unsupported instruction, or ordinary
        pipeline bubble.
        """

        self._d_tag = self._c_tag
        self._c_tag = self._b_tag
        self._b_tag = accepted

    def observe_falling_edge(
        self,
        *,
        cycle: int,
        regwrite: bool,
        rd: int,
        wdata: int,
    ) -> Optional[RetireEvent]:
        """
        Observe the architectural retirement point.

        A valid D tag emits exactly one RetireEvent.

        If no D tag exists, RegWrite must not be asserted. rd/wdata may
        contain irrelevant or stale datapath values and are ignored.
        """

        if cycle < 0:
            raise ValueError("cycle must be non-negative")

        if not 0 <= rd <= 31:
            raise ValueError("rd must be in [0, 31]")

        if not 0 <= wdata <= MASK32:
            raise ValueError("wdata must fit 32 bits")

        tag = self._d_tag

        if tag is None:
            if regwrite:
                raise RetireProtocolError(
                    "register write observed without a valid D-stage "
                    "retire tag"
                )

            return None

        expected_id = self._last_retired_instruction_id + 1

        if tag.instruction_id != expected_id:
            raise RetireProtocolError(
                "retire instruction order violation: "
                f"expected instruction_id={expected_id}, "
                f"got {tag.instruction_id}"
            )

        event = RetireEvent(
            cycle=cycle,
            valid=True,
            regwrite=bool(regwrite),
            rd=rd,
            wdata=wdata,
            instruction_id=tag.instruction_id,
        )

        self._last_retired_instruction_id = tag.instruction_id
        self._retired_count += 1

        # Prevent accidental duplicate observation if the caller invokes
        # observe_falling_edge twice before the next pipeline advance.
        self._d_tag = None

        return event
