from __future__ import annotations

from dataclasses import dataclass

from research.week5.impl.execution_event import ExecutionEvent
from research.week13.pure_random.stream_planner import (
    PlannedPureRandomBlock,
    PureRandomPlan,
)


INSTRUCTION_BYTES = 4
IMEM_WORD_CAPACITY = 128
IMEM_PC_MASK = 0x1FF


class PureRandomStreamPlanningError(RuntimeError):
    pass


class PureRandomStreamExecutionMismatch(RuntimeError):
    pass


def physical_pc_for_logical_word(
    logical_word_index: int,
) -> int:
    if (
        isinstance(logical_word_index, bool)
        or not isinstance(logical_word_index, int)
        or logical_word_index < 0
    ):
        raise ValueError(
            "logical_word_index must be non-negative"
        )

    return (
        logical_word_index
        * INSTRUCTION_BYTES
    ) & IMEM_PC_MASK


@dataclass(frozen=True)
class PureRandomRuntimeEntry:
    """
    Runtime representation of one complete M1-PR image block.

    Important:
      * image_words always retains the complete block image;
      * expected_executed_word_offsets retains the complete architectural
        execution path of that block;
      * the offline plan may intentionally consume only a prefix of that
        path in the final block because the hard cap has priority.

    Thus a partial final block remains resident until exact-N termination
    discards its unexecuted suffix.
    """

    logical_word_start: int
    planned: PlannedPureRandomBlock

    def __post_init__(self) -> None:
        if (
            isinstance(self.logical_word_start, bool)
            or not isinstance(self.logical_word_start, int)
            or self.logical_word_start < 0
        ):
            raise ValueError(
                "logical_word_start must be non-negative"
            )

        if (
            self.physical_word_addresses[0]
            != self.planned.realized.start_pc
        ):
            raise ValueError(
                "runtime physical start does not match "
                "offline planned start PC"
            )

        if self.image_word_count > IMEM_WORD_CAPACITY:
            raise ValueError(
                "one runtime block exceeds IMEM capacity"
            )

    @property
    def block_index(self) -> int:
        return self.planned.block_index

    @property
    def stream_entry_key(
        self,
    ) -> tuple[str, int]:
        return (
            "M1",
            self.block_index,
        )

    @property
    def first_executed_instruction_index(
        self,
    ) -> int:
        return (
            self.planned
            .first_accepted_instruction_index
        )

    @property
    def image_words(
        self,
    ) -> tuple[int, ...]:
        return self.planned.realized.words

    @property
    def image_word_count(self) -> int:
        return len(self.image_words)

    @property
    def logical_word_end_exclusive(
        self,
    ) -> int:
        return (
            self.logical_word_start
            + self.image_word_count
        )

    @property
    def expected_executed_word_offsets(
        self,
    ) -> tuple[int, ...]:
        # Deliberately FULL expected path, not the hard-cap prefix.
        return (
            self.planned.realized
            .expected_executed_word_indices
        )

    @property
    def planned_accepted_word_offsets(
        self,
    ) -> tuple[int, ...]:
        return self.planned.accepted_word_indices

    @property
    def expected_executed_instruction_count(
        self,
    ) -> int:
        return len(
            self.expected_executed_word_offsets
        )

    @property
    def physical_word_addresses(
        self,
    ) -> tuple[int, ...]:
        return tuple(
            physical_pc_for_logical_word(
                self.logical_word_start + offset
            )
            for offset in range(
                self.image_word_count
            )
        )

    @property
    def expected_executed_pcs(
        self,
    ) -> tuple[int, ...]:
        return tuple(
            physical_pc_for_logical_word(
                self.logical_word_start + offset
            )
            for offset
            in self.expected_executed_word_offsets
        )

    @property
    def expected_executed_words(
        self,
    ) -> tuple[int, ...]:
        return tuple(
            self.image_words[offset]
            for offset
            in self.expected_executed_word_offsets
        )


def build_runtime_entries(
    plan: PureRandomPlan,
) -> tuple[PureRandomRuntimeEntry, ...]:
    if not isinstance(
        plan,
        PureRandomPlan,
    ):
        raise TypeError(
            "plan must be PureRandomPlan"
        )

    result: list[
        PureRandomRuntimeEntry
    ] = []

    logical_word_start = 0

    for block in plan.blocks:
        entry = PureRandomRuntimeEntry(
            logical_word_start=(
                logical_word_start
            ),
            planned=block,
        )

        result.append(
            entry
        )

        logical_word_start = (
            entry.logical_word_end_exclusive
        )

    return tuple(result)


class PureRandomProgramRing:
    """
    FIFO ownership model of the 128-word physical runtime IMEM.

    Contiguous logical allocation plus a <=128-word resident window
    guarantees that newly reused physical slots belong only to words
    whose previous logical owners have already been released.
    """

    def __init__(
        self,
        *,
        capacity_words: int = IMEM_WORD_CAPACITY,
    ) -> None:
        if (
            isinstance(capacity_words, bool)
            or not isinstance(capacity_words, int)
            or not 1 <= capacity_words <= IMEM_WORD_CAPACITY
        ):
            raise ValueError(
                "capacity_words must be in 1..128"
            )

        self._capacity_words = (
            capacity_words
        )

        self._entries: list[
            PureRandomRuntimeEntry
        ] = []

        self._used_words = 0

    @property
    def entries(
        self,
    ) -> tuple[
        PureRandomRuntimeEntry,
        ...
    ]:
        return tuple(self._entries)

    @property
    def used_words(self) -> int:
        return self._used_words

    @property
    def free_words(self) -> int:
        return (
            self._capacity_words
            - self._used_words
        )

    @property
    def pending_entry_count(self) -> int:
        return len(self._entries)

    def can_append(
        self,
        entry: PureRandomRuntimeEntry,
    ) -> bool:
        if not isinstance(
            entry,
            PureRandomRuntimeEntry,
        ):
            raise TypeError(
                "entry must be PureRandomRuntimeEntry"
            )

        return (
            entry.image_word_count
            <= self.free_words
        )

    def append(
        self,
        entry: PureRandomRuntimeEntry,
    ) -> None:
        if not self.can_append(
            entry
        ):
            raise PureRandomStreamPlanningError(
                "runtime IMEM ring has insufficient free space"
            )

        if self._entries:
            expected_start = (
                self._entries[-1]
                .logical_word_end_exclusive
            )

            if (
                entry.logical_word_start
                != expected_start
            ):
                raise PureRandomStreamPlanningError(
                    "runtime logical layout is not contiguous"
                )

        self._entries.append(
            entry
        )

        self._used_words += (
            entry.image_word_count
        )

    def release_oldest(
        self,
        *,
        stream_entry_key: tuple[str, int],
    ) -> PureRandomRuntimeEntry:
        if not self._entries:
            raise PureRandomStreamPlanningError(
                "cannot release empty ring"
            )

        oldest = self._entries[0]

        if (
            oldest.stream_entry_key
            != stream_entry_key
        ):
            raise PureRandomStreamPlanningError(
                "runtime release must preserve FIFO order"
            )

        self._entries.pop(0)

        self._used_words -= (
            oldest.image_word_count
        )

        if self._used_words < 0:
            raise RuntimeError(
                "runtime ring accounting underflow"
            )

        return oldest

    def discard_all_for_termination(
        self,
    ) -> tuple[
        PureRandomRuntimeEntry,
        ...
    ]:
        if not self._entries:
            raise PureRandomStreamPlanningError(
                "cannot discard from empty ring"
            )

        entries = tuple(
            self._entries
        )

        expected_words = sum(
            entry.image_word_count
            for entry in entries
        )

        if (
            expected_words
            != self._used_words
        ):
            raise RuntimeError(
                "runtime ring accounting mismatch "
                "before termination"
            )

        self._entries.clear()
        self._used_words = 0

        return entries


@dataclass(frozen=True)
class CompletedPureRandomEntry:
    entry: PureRandomRuntimeEntry
    first_instruction_index: int
    last_instruction_index: int
    accepted_instruction_count: int


class PureRandomAcceptedTracker:
    """
    Validate DUT accepted-program order against M1-PR runtime entries.

    Only architecturally accepted ExecutionEvents advance this tracker.
    Stalls, bubbles, and flushed wrong-path words do not.
    """

    def __init__(
        self,
        *,
        first_expected_instruction_index: int = 1,
    ) -> None:
        if (
            isinstance(
                first_expected_instruction_index,
                bool,
            )
            or not isinstance(
                first_expected_instruction_index,
                int,
            )
            or first_expected_instruction_index <= 0
        ):
            raise ValueError(
                "first_expected_instruction_index "
                "must be positive"
            )

        self._entries: list[
            PureRandomRuntimeEntry
        ] = []

        self._entry_progress = 0

        self._next_expected_instruction_index = (
            first_expected_instruction_index
        )

        self._accepted_count = 0

    @property
    def pending_entries(
        self,
    ) -> tuple[
        PureRandomRuntimeEntry,
        ...
    ]:
        return tuple(self._entries)

    @property
    def accepted_count(self) -> int:
        return self._accepted_count

    @property
    def next_expected_instruction_index(
        self,
    ) -> int:
        return (
            self._next_expected_instruction_index
        )

    @property
    def current_entry_progress(
        self,
    ) -> int:
        return self._entry_progress

    @property
    def pending_entry_count(self) -> int:
        return len(self._entries)

    def enqueue(
        self,
        entry: PureRandomRuntimeEntry,
    ) -> None:
        if not isinstance(
            entry,
            PureRandomRuntimeEntry,
        ):
            raise TypeError(
                "entry must be PureRandomRuntimeEntry"
            )

        if self._entries:
            expected_logical_start = (
                self._entries[-1]
                .logical_word_end_exclusive
            )

            if (
                entry.logical_word_start
                != expected_logical_start
            ):
                raise PureRandomStreamExecutionMismatch(
                    "tracker entries are not "
                    "logically contiguous"
                )

        expected_first_index = (
            self._next_expected_instruction_index
            + sum(
                pending
                .expected_executed_instruction_count
                for pending in self._entries
            )
        )

        if (
            entry.first_executed_instruction_index
            != expected_first_index
        ):
            raise PureRandomStreamExecutionMismatch(
                "runtime executed-index layout "
                "is not contiguous"
            )

        self._entries.append(
            entry
        )

    def observe(
        self,
        event: ExecutionEvent,
    ) -> CompletedPureRandomEntry | None:
        if not isinstance(
            event,
            ExecutionEvent,
        ):
            raise TypeError(
                "event must be ExecutionEvent"
            )

        if not self._entries:
            raise PureRandomStreamExecutionMismatch(
                "accepted event arrived with no "
                "runtime entry"
            )

        if (
            event.instruction_index
            != self._next_expected_instruction_index
        ):
            raise PureRandomStreamExecutionMismatch(
                "accepted instruction-index mismatch"
            )

        entry = self._entries[0]

        expected_pc = (
            entry.expected_executed_pcs[
                self._entry_progress
            ]
        )

        expected_word = (
            entry.expected_executed_words[
                self._entry_progress
            ]
        )

        if event.pc != expected_pc:
            raise PureRandomStreamExecutionMismatch(
                "accepted PC diverged from M1 plan: "
                f"instruction_index={event.instruction_index}, "
                f"expected_pc=0x{expected_pc:03x}, "
                f"observed_pc=0x{event.pc:03x}"
            )

        if event.instruction != expected_word:
            raise PureRandomStreamExecutionMismatch(
                "accepted instruction diverged from M1 plan: "
                f"instruction_index={event.instruction_index}, "
                f"pc=0x{event.pc:03x}, "
                f"expected=0x{expected_word:08x}, "
                f"observed=0x{event.instruction:08x}"
            )

        self._accepted_count += 1
        self._next_expected_instruction_index += 1
        self._entry_progress += 1

        if (
            self._entry_progress
            != entry.expected_executed_instruction_count
        ):
            return None

        completed = self._entries.pop(0)

        first_index = (
            completed
            .first_executed_instruction_index
        )

        count = (
            completed
            .expected_executed_instruction_count
        )

        self._entry_progress = 0

        return CompletedPureRandomEntry(
            entry=completed,
            first_instruction_index=(
                first_index
            ),
            last_instruction_index=(
                first_index
                + count
                - 1
            ),
            accepted_instruction_count=(
                count
            ),
        )

    def discard_pending_for_termination(
        self,
    ) -> tuple[
        PureRandomRuntimeEntry,
        ...
    ]:
        if not self._entries:
            raise PureRandomStreamExecutionMismatch(
                "no pending suffix at termination"
            )

        head = self._entries[0]

        if (
            self._entry_progress < 0
            or self._entry_progress
            >= head.expected_executed_instruction_count
        ):
            raise RuntimeError(
                "invalid partial head progress"
            )

        entries = tuple(
            self._entries
        )

        accepted_before = (
            self._accepted_count
        )

        next_before = (
            self._next_expected_instruction_index
        )

        self._entries.clear()
        self._entry_progress = 0

        if (
            self._accepted_count
            != accepted_before
            or self._next_expected_instruction_index
            != next_before
        ):
            raise RuntimeError(
                "termination cleanup changed "
                "accepted execution state"
            )

        return entries


@dataclass(frozen=True)
class PureRandomDiscardedSuffix:
    entries: tuple[
        PureRandomRuntimeEntry,
        ...
    ]

    accepted_count_at_termination: int
    head_accepted_instruction_count: int
    discarded_expected_instruction_count: int
    reclaimed_resident_word_count: int


class PureRandomRuntimeWindow:
    """
    Keep runtime ring ownership and accepted-stream tracking atomic.
    """

    def __init__(self) -> None:
        self._ring = (
            PureRandomProgramRing()
        )

        self._tracker = (
            PureRandomAcceptedTracker()
        )

        self._terminated = False

    @property
    def used_words(self) -> int:
        return self._ring.used_words

    @property
    def free_words(self) -> int:
        return self._ring.free_words

    @property
    def pending_entry_count(self) -> int:
        return self._ring.pending_entry_count

    @property
    def pending_entries(
        self,
    ) -> tuple[
        PureRandomRuntimeEntry,
        ...
    ]:
        """
        Read-only view of currently resident runtime entries.

        Exposed for ownership/invariant checking without allowing
        callers to mutate the underlying FIFO ring.
        """
        return self._ring.entries

    @property
    def accepted_count(self) -> int:
        return self._tracker.accepted_count

    def can_commit(
        self,
        entry: PureRandomRuntimeEntry,
    ) -> bool:
        return self._ring.can_append(
            entry
        )

    def commit_patched_entry(
        self,
        entry: PureRandomRuntimeEntry,
    ) -> None:
        if self._terminated:
            raise RuntimeError(
                "runtime window is terminated"
            )

        # Both validate before either state machine mutates.
        if not self._ring.can_append(
            entry
        ):
            raise PureRandomStreamPlanningError(
                "runtime IMEM ring has insufficient space"
            )

        self._tracker.enqueue(
            entry
        )

        try:
            self._ring.append(
                entry
            )
        except Exception:
            raise RuntimeError(
                "ring append failed after tracker enqueue"
            )

    def finalize_accepted_event(
        self,
        event: ExecutionEvent,
    ) -> CompletedPureRandomEntry | None:
        completed = (
            self._tracker.observe(
                event
            )
        )

        if completed is None:
            return None

        released = (
            self._ring.release_oldest(
                stream_entry_key=(
                    completed
                    .entry
                    .stream_entry_key
                )
            )
        )

        if released != completed.entry:
            raise RuntimeError(
                "runtime release identity mismatch"
            )

        return completed

    def discard_unexecuted_suffix(
        self,
    ) -> PureRandomDiscardedSuffix:
        if self._terminated:
            raise RuntimeError(
                "runtime window already terminated"
            )

        ring_entries = (
            self._ring.entries
        )

        tracker_entries = (
            self._tracker.pending_entries
        )

        if not ring_entries:
            raise RuntimeError(
                "no resident suffix exists"
            )

        if ring_entries != tracker_entries:
            raise RuntimeError(
                "ring/tracker disagreement before termination"
            )

        head_progress = (
            self._tracker
            .current_entry_progress
        )

        discarded_expected = (
            sum(
                entry
                .expected_executed_instruction_count
                for entry in tracker_entries
            )
            - head_progress
        )

        reclaimed_words = sum(
            entry.image_word_count
            for entry in ring_entries
        )

        accepted_before = (
            self._tracker.accepted_count
        )

        tracker_discarded = (
            self._tracker
            .discard_pending_for_termination()
        )

        ring_discarded = (
            self._ring
            .discard_all_for_termination()
        )

        if (
            tracker_discarded
            != ring_entries
            or ring_discarded
            != ring_entries
        ):
            raise RuntimeError(
                "termination changed resident identity"
            )

        if (
            self._tracker.accepted_count
            != accepted_before
        ):
            raise RuntimeError(
                "termination changed accepted count"
            )

        if (
            self._ring.used_words != 0
            or self._ring.pending_entry_count != 0
            or self._tracker.pending_entry_count != 0
        ):
            raise RuntimeError(
                "termination left resident runtime state"
            )

        self._terminated = True

        return PureRandomDiscardedSuffix(
            entries=ring_entries,
            accepted_count_at_termination=(
                accepted_before
            ),
            head_accepted_instruction_count=(
                head_progress
            ),
            discarded_expected_instruction_count=(
                discarded_expected
            ),
            reclaimed_resident_word_count=(
                reclaimed_words
            ),
        )
