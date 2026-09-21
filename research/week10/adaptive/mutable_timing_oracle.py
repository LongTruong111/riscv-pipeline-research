from __future__ import annotations

from typing import Mapping

from research.week9.benchmark.streaming_timing import (
    StreamingTimingOracleV1,
)

from research.week10.adaptive.campaign_runner import (
    IMEM_WORD_CAPACITY,
)


INSTRUCTION_BYTES = 4
MAX_PHYSICAL_PC = (
    IMEM_WORD_CAPACITY * INSTRUCTION_BYTES
    - INSTRUCTION_BYTES
)


class BoundedMutableTimingOracleV1(
    StreamingTimingOracleV1
):
    """
    Week-10 bounded extension of the frozen Week-9 streaming
    Timing Oracle v1.

    The timing semantics and all retained architectural/timing state
    remain owned by StreamingTimingOracleV1.

    Week-10 adds only a controlled program-extension operation.

    T10.9e-2b contract:
      - physical IMEM contains at most 128 words;
      - program extension is append-only;
      - existing PC entries cannot be overwritten;
      - newly appended PCs must be physically contiguous;
      - PC wrap/reuse is intentionally NOT supported here.

    This is sufficient for the initial multi-epoch RTL proof while
    keeping the frozen Week-9 implementation unchanged.
    """

    def __init__(
        self,
        program: Mapping[int, int],
    ) -> None:
        normalized = self._normalize_words(
            program,
            allow_empty=False,
        )

        self._validate_capacity(
            normalized
        )

        super().__init__(
            normalized
        )

    @property
    def program_word_count(self) -> int:
        return len(self._program)

    @property
    def remaining_word_capacity(self) -> int:
        return (
            IMEM_WORD_CAPACITY
            - self.program_word_count
        )

    @property
    def highest_program_pc(self) -> int:
        return max(
            self._program
        )

    def append_program(
        self,
        words: Mapping[int, int],
    ) -> None:
        """
        Atomically append one or more new physical program words.

        Validation completes before _program is mutated.
        """
        normalized = self._normalize_words(
            words,
            allow_empty=False,
        )

        existing_pcs = set(
            self._program
        )

        duplicate_pcs = (
            existing_pcs
            & set(normalized)
        )

        if duplicate_pcs:
            raise ValueError(
                "mutable timing oracle cannot overwrite "
                "existing program PCs: "
                f"{sorted(duplicate_pcs)}"
            )

        combined_count = (
            len(existing_pcs)
            + len(normalized)
        )

        if combined_count > IMEM_WORD_CAPACITY:
            raise ValueError(
                "mutable timing program exceeds "
                f"{IMEM_WORD_CAPACITY}-word IMEM capacity"
            )

        expected_first_pc = (
            self.highest_program_pc
            + INSTRUCTION_BYTES
        )

        ordered_pcs = tuple(
            sorted(normalized)
        )

        expected_pcs = tuple(
            expected_first_pc
            + INSTRUCTION_BYTES * offset
            for offset in range(
                len(ordered_pcs)
            )
        )

        if ordered_pcs != expected_pcs:
            raise ValueError(
                "mutable timing program extension must "
                "be physically contiguous: "
                f"expected={expected_pcs}, "
                f"observed={ordered_pcs}"
            )

        # Mutation occurs only after every validation above has passed.
        self._program.update(
            normalized
        )

    @staticmethod
    def _normalize_words(
        words: Mapping[int, int],
        *,
        allow_empty: bool,
    ) -> dict[int, int]:
        if not isinstance(
            words,
            Mapping,
        ):
            raise TypeError(
                "program words must be a mapping"
            )

        if not words and not allow_empty:
            raise ValueError(
                "program words must not be empty"
            )

        normalized: dict[int, int] = {}

        for pc, instruction in words.items():
            if (
                isinstance(pc, bool)
                or not isinstance(pc, int)
            ):
                raise TypeError(
                    "program PC must be an integer"
                )

            if pc < 0:
                raise ValueError(
                    "program PC must be non-negative"
                )

            if (
                pc
                % INSTRUCTION_BYTES
                != 0
            ):
                raise ValueError(
                    "program PC must be 4-byte aligned"
                )

            if pc > MAX_PHYSICAL_PC:
                raise ValueError(
                    "program PC exceeds bounded "
                    "9-bit IMEM window"
                )

            if (
                isinstance(instruction, bool)
                or not isinstance(
                    instruction,
                    int,
                )
            ):
                raise TypeError(
                    "instruction must be an integer"
                )

            if not (
                0
                <= instruction
                <= 0xFFFFFFFF
            ):
                raise ValueError(
                    "instruction does not fit 32 bits"
                )

            normalized[pc] = instruction

        return normalized

    @staticmethod
    def _validate_capacity(
        program: Mapping[int, int],
    ) -> None:
        if len(program) > IMEM_WORD_CAPACITY:
            raise ValueError(
                "initial timing program exceeds "
                f"{IMEM_WORD_CAPACITY}-word IMEM capacity"
            )
