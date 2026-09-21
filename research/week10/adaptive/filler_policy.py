from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from research.week5.impl.rv32_encode import lui


POSITIVE_REGISTERS: tuple[int, ...] = tuple(range(1, 32))

# Fixed, nontrivial U-immediate.
# Filler selection must not become another tunable/random policy.
FILLER_LUI_IMM20 = 0x13579

# Frozen campaign ratio:
#     80% targeted-template instructions
#     20% campaign filler instructions
#
# Equivalent deterministic ratio:
#     4 targeted : 1 filler
TARGETED_INSTRUCTIONS_PER_FILLER = 4


class FillerKind(str, Enum):
    STRUCTURAL_D2 = "structural_d2"
    CAMPAIGN_BACKGROUND = "campaign_background"


class FillerConstructionError(RuntimeError):
    """Raised when no legal filler instruction can be constructed."""


@dataclass(frozen=True)
class FillerInstruction:
    """
    One semantically independent filler instruction.

    Week10 uses a source-independent LUI so the filler:
      - never reads the target dependency register;
      - never reads x0;
      - never redirects control flow;
      - writes only an explicitly selected auxiliary register.
    """

    kind: FillerKind
    word: int
    rd: int

    def __post_init__(self) -> None:
        if self.rd not in POSITIVE_REGISTERS:
            raise ValueError(
                f"filler destination must be x1..x31, got x{self.rd}"
            )

        if not 0 <= self.word <= 0xFFFFFFFF:
            raise ValueError(
                f"instruction word must fit 32 bits, got {self.word:#x}"
            )

    @property
    def reads(self) -> tuple[int, ...]:
        """LUI has no architectural source-register dependency."""
        return ()

    @property
    def writes(self) -> tuple[int, ...]:
        return (self.rd,)


def _validate_protected_registers(
    protected_registers: Iterable[int],
) -> frozenset[int]:
    protected = frozenset(protected_registers)

    invalid = {
        register
        for register in protected
        if not 0 <= register <= 31
    }

    if invalid:
        raise ValueError(
            "protected register set contains invalid registers: "
            f"{sorted(invalid)}"
        )

    return protected


def select_auxiliary_register(
    protected_registers: Iterable[int] = (),
) -> int:
    """
    Select a legal filler destination deterministically.

    Selection is deliberately coverage-independent and RNG-independent.
    The lowest positive architectural register not currently protected
    is chosen.
    """
    protected = _validate_protected_registers(protected_registers)

    for register in POSITIVE_REGISTERS:
        if register not in protected:
            return register

    raise FillerConstructionError(
        "no legal positive auxiliary register remains for filler"
    )


def build_filler_instruction(
    *,
    kind: FillerKind,
    protected_registers: Iterable[int] = (),
) -> FillerInstruction:
    """
    Construct one source-independent legal filler instruction.

    LUI is used instead of the encoder's NOP because NOP is encoded as
    ADDI x0,x0,0. Adaptive filler must not write x0.
    """
    rd = select_auxiliary_register(protected_registers)

    return FillerInstruction(
        kind=kind,
        word=lui(rd, FILLER_LUI_IMM20),
        rd=rd,
    )


@dataclass
class CampaignFillerScheduler:
    """
    Deterministic cumulative 80:20 campaign mix scheduler.

    Structural instructions inside a template are included in
    targeted_instruction_count by the caller.

    Campaign filler is scheduled only after a complete template
    instance. This object does not decide placement inside templates.
    """

    targeted_instruction_count: int = 0
    scheduled_filler_count: int = 0

    def __post_init__(self) -> None:
        if self.targeted_instruction_count < 0:
            raise ValueError(
                "targeted_instruction_count must be non-negative"
            )

        if self.scheduled_filler_count < 0:
            raise ValueError(
                "scheduled_filler_count must be non-negative"
            )

        maximum_valid_fillers = (
            self.targeted_instruction_count
            // TARGETED_INSTRUCTIONS_PER_FILLER
        )

        if self.scheduled_filler_count > maximum_valid_fillers:
            raise ValueError(
                "scheduled filler count exceeds deterministic "
                "80:20 schedule"
            )

    def schedule_after_template(
        self,
        targeted_instructions: int,
    ) -> int:
        """
        Record one complete template instance and return the number of
        campaign filler instructions now due.

        Returned filler instructions are immediately accounted as
        scheduled. The caller must emit exactly that many fillers before
        recording the next scheduling boundary.
        """
        if targeted_instructions <= 0:
            raise ValueError(
                "targeted_instructions must be positive"
            )

        self.targeted_instruction_count += targeted_instructions

        required_total_fillers = (
            self.targeted_instruction_count
            // TARGETED_INSTRUCTIONS_PER_FILLER
        )

        due = (
            required_total_fillers
            - self.scheduled_filler_count
        )

        if due < 0:
            raise RuntimeError(
                "campaign filler accounting became inconsistent"
            )

        self.scheduled_filler_count += due

        return due

    @property
    def total_scheduled_instructions(self) -> int:
        return (
            self.targeted_instruction_count
            + self.scheduled_filler_count
        )

    @property
    def filler_fraction(self) -> float:
        total = self.total_scheduled_instructions

        if total == 0:
            return 0.0

        return self.scheduled_filler_count / total
