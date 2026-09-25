from __future__ import annotations

from dataclasses import dataclass

from research.week13.pure_random.family_sampler import (
    InstructionFamily,
)


PHYSICAL_PC_MASK = 0x1FF


@dataclass(frozen=True)
class RealizedPureRandomBlock:
    """
    One concrete M1-PR program-image block.

    This representation is intentionally independent of Adaptive-CGS
    ArmID, TargetSelection, reward, and attribution-witness semantics.
    """

    family: InstructionFamily
    mnemonic: str
    start_pc: int

    words: tuple[int, ...]
    expected_executed_word_indices: tuple[int, ...]
    structural_word_indices: tuple[int, ...]

    rd: int | None = None
    rs1: int | None = None
    rs2: int | None = None
    immediate: int | None = None
    effective_address: int | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.start_pc, bool)
            or not isinstance(self.start_pc, int)
            or not 0 <= self.start_pc <= 508
        ):
            raise ValueError(
                "start_pc must be an integer in 0..508"
            )

        if self.start_pc % 4 != 0:
            raise ValueError(
                "start_pc must be 4-byte aligned"
            )

        if not self.mnemonic:
            raise ValueError(
                "mnemonic must be non-empty"
            )

        if not self.words:
            raise ValueError(
                "block must contain at least one word"
            )

        for word in self.words:
            if not 0 <= word <= 0xFFFFFFFF:
                raise ValueError(
                    "instruction word must fit 32 bits"
                )

        self._validate_indices(
            "expected_executed_word_indices",
            self.expected_executed_word_indices,
            require_nonempty=True,
        )

        self._validate_indices(
            "structural_word_indices",
            self.structural_word_indices,
            require_nonempty=False,
        )

    def _validate_indices(
        self,
        name: str,
        values: tuple[int, ...],
        *,
        require_nonempty: bool,
    ) -> None:
        if require_nonempty and not values:
            raise ValueError(
                f"{name} must not be empty"
            )

        if tuple(sorted(set(values))) != values:
            raise ValueError(
                f"{name} must be unique and increasing"
            )

        for index in values:
            if not 0 <= index < len(self.words):
                raise ValueError(
                    f"{name} contains out-of-range index {index}"
                )

    @property
    def expected_executed_instruction_count(
        self,
    ) -> int:
        return len(
            self.expected_executed_word_indices
        )

    def physical_pc_for_word(
        self,
        word_index: int,
    ) -> int:
        if not 0 <= word_index < len(self.words):
            raise ValueError(
                "word_index is outside block"
            )

        return (
            self.start_pc
            + 4 * word_index
        ) & PHYSICAL_PC_MASK
