"""Wrap-aware bounded streaming timing oracle for Week 10.

This module extends the frozen Week-9 streaming timing semantics with
bounded physical-IMEM reuse.

Execution identity remains monotonic in executed-program order, while
the DUT instruction-fetch PC is a 9-bit physical address:

    physical_pc(logical_word) =
        4 * (logical_word % IMEM_WORD_CAPACITY)

Physical slots may be reused only after their previous logical owners
have been explicitly released.

The frozen Week-9 and earlier Week-10 append-only timing oracles remain
unchanged.
"""

from __future__ import annotations

from typing import Mapping

from research.week9.benchmark.streaming_timing import (
    StreamingTimingOracleV1,
)
from research.week10.adaptive.campaign_runner import (
    IMEM_WORD_CAPACITY,
)
from research.week10.adaptive.wrap_aware_architectural_model import (
    WrapAwareRV32ArchitecturalModel,
)


INSTRUCTION_BYTES = 4
MAX_PHYSICAL_PC = (
    IMEM_WORD_CAPACITY * INSTRUCTION_BYTES
    - INSTRUCTION_BYTES
)


class WrapAwareMutableTimingOracleV1(
    StreamingTimingOracleV1
):
    """Bounded timing oracle with logical ownership of physical slots.

    Timing rules, forwarding history, cycle accounting, and instruction
    IDs are inherited from frozen StreamingTimingOracleV1.

    Week-10 additions:

      * physical fetch-PC wrap;
      * monotonic logical-word ownership;
      * explicit release before physical-slot reuse;
      * bounded resident program image.

    The resident program size is always at most IMEM_WORD_CAPACITY.
    """

    def __init__(
        self,
        program: Mapping[int, int],
    ) -> None:
        normalized = self._normalize_words(
            program
        )

        if not normalized:
            raise ValueError(
                "initial timing program must not be empty"
            )

        # The adaptive campaign always begins at logical word zero.
        self._validate_fragment(
            first_logical_word_index=0,
            words=normalized,
        )

        super().__init__(
            normalized
        )

        # Replace only the architectural fetch-PC semantics.
        # All frozen timing state remains owned by the parent oracle.
        self._model = (
            WrapAwareRV32ArchitecturalModel()
        )

        self._logical_owner_by_pc: dict[
            int,
            int,
        ] = {}

        self._instruction_by_logical_word: dict[
            int,
            int,
        ] = {}

        for offset in range(
            len(normalized)
        ):
            logical_word_index = offset

            physical_pc = (
                self.physical_pc_for_logical_word(
                    logical_word_index
                )
            )

            self._logical_owner_by_pc[
                physical_pc
            ] = logical_word_index

            self._instruction_by_logical_word[
                logical_word_index
            ] = normalized[
                physical_pc
            ]

        self._next_append_logical_word_index = (
            len(normalized)
        )

        self._next_release_logical_word_index = 0

    @staticmethod
    def physical_pc_for_logical_word(
        logical_word_index: int,
    ) -> int:
        if (
            isinstance(
                logical_word_index,
                bool,
            )
            or not isinstance(
                logical_word_index,
                int,
            )
        ):
            raise TypeError(
                "logical word index must be an integer"
            )

        if logical_word_index < 0:
            raise ValueError(
                "logical word index must be non-negative"
            )

        return (
            logical_word_index
            % IMEM_WORD_CAPACITY
        ) * INSTRUCTION_BYTES

    @property
    def program_word_count(self) -> int:
        """Number of currently resident physical program words."""

        return len(
            self._program
        )

    @property
    def resident_word_count(self) -> int:
        return self.program_word_count

    @property
    def remaining_word_capacity(self) -> int:
        return (
            IMEM_WORD_CAPACITY
            - self.program_word_count
        )

    @property
    def next_append_logical_word_index(
        self,
    ) -> int:
        return (
            self._next_append_logical_word_index
        )

    @property
    def next_release_logical_word_index(
        self,
    ) -> int:
        return (
            self._next_release_logical_word_index
        )

    def logical_owner_for_pc(
        self,
        physical_pc: int,
    ) -> int | None:
        self._validate_physical_pc(
            physical_pc
        )

        return (
            self._logical_owner_by_pc.get(
                physical_pc
            )
        )

    def generation_for_pc(
        self,
        physical_pc: int,
    ) -> int | None:
        owner = self.logical_owner_for_pc(
            physical_pc
        )

        if owner is None:
            return None

        return (
            owner
            // IMEM_WORD_CAPACITY
        )

    def append_program(
        self,
        words: Mapping[int, int],
        *,
        first_logical_word_index: int,
    ) -> None:
        """Atomically append one contiguous logical program fragment.

        `words` is keyed by physical byte PC.

        Logical order is reconstructed from
        `first_logical_word_index`, so a fragment may cross:

            504, 508, 0, 4, ...

        A physical PC may be reused only after its previous logical
        owner has been released.
        """

        normalized = self._normalize_words(
            words
        )

        if not normalized:
            raise ValueError(
                "program extension must not be empty"
            )

        self._validate_logical_word_index(
            first_logical_word_index
        )

        if (
            first_logical_word_index
            != self._next_append_logical_word_index
        ):
            raise ValueError(
                "timing logical append order violation: "
                f"expected first logical word "
                f"{self._next_append_logical_word_index}, "
                f"got {first_logical_word_index}"
            )

        self._validate_fragment(
            first_logical_word_index=(
                first_logical_word_index
            ),
            words=normalized,
        )

        additions = []

        for offset in range(
            len(normalized)
        ):
            logical_word_index = (
                first_logical_word_index
                + offset
            )

            physical_pc = (
                self.physical_pc_for_logical_word(
                    logical_word_index
                )
            )

            existing_owner = (
                self._logical_owner_by_pc.get(
                    physical_pc
                )
            )

            if existing_owner is not None:
                raise ValueError(
                    "cannot overwrite live physical "
                    "timing slot: "
                    f"pc={physical_pc:#x}, "
                    f"existing_logical_word="
                    f"{existing_owner}, "
                    f"new_logical_word="
                    f"{logical_word_index}"
                )

            additions.append(
                (
                    logical_word_index,
                    physical_pc,
                    normalized[
                        physical_pc
                    ],
                )
            )

        if (
            self.program_word_count
            + len(additions)
            > IMEM_WORD_CAPACITY
        ):
            raise ValueError(
                "wrap-aware timing program exceeds "
                f"{IMEM_WORD_CAPACITY} resident words"
            )

        # Mutation begins only after all validation succeeds.
        for (
            logical_word_index,
            physical_pc,
            instruction,
        ) in additions:
            self._program[
                physical_pc
            ] = instruction

            self._logical_owner_by_pc[
                physical_pc
            ] = logical_word_index

            self._instruction_by_logical_word[
                logical_word_index
            ] = instruction

        self._next_append_logical_word_index += (
            len(additions)
        )

    def release_logical_words(
        self,
        *,
        first_logical_word_index: int,
        word_count: int,
    ) -> None:
        """Release one contiguous logical prefix from physical backing.

        RuntimeStreamWindow remains the intended lifecycle authority.
        This method mirrors that release into the timing oracle.

        Release does not modify:

          * architectural register state;
          * architectural memory state;
          * timing writer history;
          * instruction ID;
          * cycle state.
        """

        self._validate_logical_word_index(
            first_logical_word_index
        )

        if (
            isinstance(word_count, bool)
            or not isinstance(
                word_count,
                int,
            )
        ):
            raise TypeError(
                "word_count must be an integer"
            )

        if word_count <= 0:
            raise ValueError(
                "word_count must be positive"
            )

        if (
            first_logical_word_index
            != self._next_release_logical_word_index
        ):
            raise ValueError(
                "timing logical release order violation: "
                f"expected first logical word "
                f"{self._next_release_logical_word_index}, "
                f"got {first_logical_word_index}"
            )

        releases = []

        for offset in range(
            word_count
        ):
            logical_word_index = (
                first_logical_word_index
                + offset
            )

            try:
                instruction = (
                    self
                    ._instruction_by_logical_word[
                        logical_word_index
                    ]
                )
            except KeyError as exc:
                raise ValueError(
                    "logical timing word is not "
                    "currently resident: "
                    f"logical_word_index="
                    f"{logical_word_index}"
                ) from exc

            physical_pc = (
                self.physical_pc_for_logical_word(
                    logical_word_index
                )
            )

            owner = (
                self._logical_owner_by_pc.get(
                    physical_pc
                )
            )

            if owner != logical_word_index:
                raise RuntimeError(
                    "timing slot ownership corruption: "
                    f"pc={physical_pc:#x}, "
                    f"expected_owner="
                    f"{logical_word_index}, "
                    f"observed_owner={owner}"
                )

            if (
                self._program.get(
                    physical_pc
                )
                != instruction
            ):
                raise RuntimeError(
                    "timing resident word corruption: "
                    f"pc={physical_pc:#x}"
                )

            releases.append(
                (
                    logical_word_index,
                    physical_pc,
                )
            )

        # Mutation begins only after all validation succeeds.
        for (
            logical_word_index,
            physical_pc,
        ) in releases:
            del self._program[
                physical_pc
            ]

            del self._logical_owner_by_pc[
                physical_pc
            ]

            del self._instruction_by_logical_word[
                logical_word_index
            ]

        self._next_release_logical_word_index += (
            word_count
        )

    @classmethod
    def _validate_fragment(
        cls,
        *,
        first_logical_word_index: int,
        words: Mapping[int, int],
    ) -> None:
        cls._validate_logical_word_index(
            first_logical_word_index
        )

        if len(words) > IMEM_WORD_CAPACITY:
            raise ValueError(
                "one timing fragment cannot exceed "
                f"{IMEM_WORD_CAPACITY} words"
            )

        expected_pcs = tuple(
            cls.physical_pc_for_logical_word(
                first_logical_word_index
                + offset
            )
            for offset in range(
                len(words)
            )
        )

        if (
            len(set(expected_pcs))
            != len(expected_pcs)
        ):
            raise ValueError(
                "timing fragment aliases its own "
                "physical IMEM slots"
            )

        if set(words) != set(expected_pcs):
            raise ValueError(
                "timing fragment does not match "
                "contiguous logical ownership: "
                f"expected_pcs="
                f"{expected_pcs}, "
                f"observed_pcs="
                f"{tuple(sorted(words))}"
            )

    @staticmethod
    def _validate_logical_word_index(
        logical_word_index: int,
    ) -> None:
        if (
            isinstance(
                logical_word_index,
                bool,
            )
            or not isinstance(
                logical_word_index,
                int,
            )
        ):
            raise TypeError(
                "logical word index must be an integer"
            )

        if logical_word_index < 0:
            raise ValueError(
                "logical word index must be non-negative"
            )

    @staticmethod
    def _validate_physical_pc(
        physical_pc: int,
    ) -> None:
        if (
            isinstance(physical_pc, bool)
            or not isinstance(
                physical_pc,
                int,
            )
        ):
            raise TypeError(
                "physical PC must be an integer"
            )

        if physical_pc < 0:
            raise ValueError(
                "physical PC must be non-negative"
            )

        if (
            physical_pc
            % INSTRUCTION_BYTES
            != 0
        ):
            raise ValueError(
                "physical PC must be 4-byte aligned"
            )

        if physical_pc > MAX_PHYSICAL_PC:
            raise ValueError(
                "physical PC exceeds 9-bit "
                "instruction-memory window"
            )

    @classmethod
    def _normalize_words(
        cls,
        words: Mapping[int, int],
    ) -> dict[int, int]:
        if not isinstance(
            words,
            Mapping,
        ):
            raise TypeError(
                "program words must be a mapping"
            )

        normalized: dict[int, int] = {}

        for pc, instruction in words.items():
            cls._validate_physical_pc(
                pc
            )

            if (
                isinstance(
                    instruction,
                    bool,
                )
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

            normalized[
                int(pc)
            ] = int(
                instruction
            )

        return normalized
