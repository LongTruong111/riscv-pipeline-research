from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

from research.week5.impl.execution_event import (
    ExecutionEvent,
)
from research.week10.adaptive.epoch_coordinator import (
    AdaptiveEpochCoordinator,
    EpochStart,
)
from research.week10.adaptive.filler_policy import (
    CampaignFillerScheduler,
    FillerInstruction,
    FillerKind,
    build_filler_instruction,
)
from research.week10.adaptive.provenance import (
    AttributionWitness,
    build_template_witnesses,
)
from research.week10.adaptive.register_policy import (
    TargetSelection,
)
from research.week10.adaptive.template_library import (
    ArmID,
)
from research.week10.adaptive.template_realizer import (
    RealizedTemplate,
    TemplateRealizer,
)


IMEM_PC_BITS = 9
IMEM_BYTES = 1 << IMEM_PC_BITS
INSTRUCTION_BYTES = 4
IMEM_WORD_CAPACITY = IMEM_BYTES // INSTRUCTION_BYTES

MAX_TEMPLATE_IMAGE_WORDS = 4
MAX_BACKGROUND_FILLERS_PER_TEMPLATE = 1
MAX_STREAM_BLOCK_WORDS = (
    MAX_TEMPLATE_IMAGE_WORDS
    + MAX_BACKGROUND_FILLERS_PER_TEMPLATE
)


def _positive_targets(
    target: TargetSelection,
) -> frozenset[int]:
    registers = set()

    if target.d1 is not None:
        registers.add(target.d1)

    if target.d2 is not None:
        registers.add(target.d2)

    return frozenset(registers)


def physical_pc_for_logical_word(
    logical_word_index: int,
) -> int:
    """
    Map an unbounded logical program-image word index into the frozen
    9-bit physical PC space.

    The runtime IMEM is a 128-word ring:

        physical_word = logical_word % 128
        physical_pc   = physical_word * 4
    """
    if (
        isinstance(logical_word_index, bool)
        or not isinstance(logical_word_index, int)
        or logical_word_index < 0
    ):
        raise ValueError(
            "logical_word_index must be a non-negative integer"
        )

    return (
        logical_word_index
        % IMEM_WORD_CAPACITY
    ) * INSTRUCTION_BYTES


@dataclass(frozen=True)
class PlannedStreamBlock:
    """
    One complete template instance plus any deterministic campaign
    background filler that becomes due immediately after it.

    A block is the minimum streaming allocation/release unit. Templates
    are never split across blocks.

    image_words:
        Exact words written into runtime IMEM.

    expected_executed_word_offsets:
        Offsets within image_words expected to appear in accepted
        executed-program order.

        Flushed A7 fall-through words are intentionally absent.

    witnesses:
        Exact producer/consumer provenance for the targeted template
        dependency or dependencies. Background filler creates no
        attribution witness.
    """

    template_instance_id: int

    arm_id: ArmID
    target: TargetSelection

    logical_word_start: int
    first_executed_instruction_index: int

    template: RealizedTemplate
    background_fillers: Tuple[FillerInstruction, ...]

    image_words: Tuple[int, ...]
    expected_executed_word_offsets: Tuple[int, ...]

    witnesses: Tuple[AttributionWitness, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.template_instance_id, bool)
            or not isinstance(self.template_instance_id, int)
            or self.template_instance_id <= 0
        ):
            raise ValueError(
                "template_instance_id must be positive"
            )

        if (
            isinstance(self.logical_word_start, bool)
            or not isinstance(self.logical_word_start, int)
            or self.logical_word_start < 0
        ):
            raise ValueError(
                "logical_word_start must be non-negative"
            )

        if (
            isinstance(
                self.first_executed_instruction_index,
                bool,
            )
            or not isinstance(
                self.first_executed_instruction_index,
                int,
            )
            or self.first_executed_instruction_index <= 0
        ):
            raise ValueError(
                "first_executed_instruction_index "
                "must be positive"
            )

        if self.arm_id is not self.template.arm_id:
            raise ValueError(
                "block arm must match realized template arm"
            )

        if self.target != self.template.target:
            raise ValueError(
                "block target must match realized template target"
            )

        if not self.image_words:
            raise ValueError(
                "stream block must contain image words"
            )

        if len(self.image_words) > MAX_STREAM_BLOCK_WORDS:
            raise ValueError(
                "stream block exceeds frozen maximum size"
            )

        expected_image = (
            self.template.words
            + tuple(
                filler.word
                for filler in self.background_fillers
            )
        )

        if self.image_words != expected_image:
            raise ValueError(
                "stream block image does not match "
                "template plus background fillers"
            )

        for filler in self.background_fillers:
            if filler.kind is not FillerKind.CAMPAIGN_BACKGROUND:
                raise ValueError(
                    "stream block contains non-campaign filler "
                    "outside the realized template"
                )

        if len(self.expected_executed_word_offsets) != (
            len(
                self.template.expected_executed_word_indices
            )
            + len(self.background_fillers)
        ):
            raise ValueError(
                "executed-word offset count mismatch"
            )

        if (
            len(self.expected_executed_word_offsets)
            != len(
                set(
                    self.expected_executed_word_offsets
                )
            )
        ):
            raise ValueError(
                "executed-word offsets contain duplicates"
            )

        for offset in self.expected_executed_word_offsets:
            if not 0 <= offset < len(self.image_words):
                raise ValueError(
                    "executed-word offset outside stream block"
                )

    @property
    def image_word_count(self) -> int:
        return len(self.image_words)

    @property
    def targeted_image_word_count(self) -> int:
        """
        Frozen 80:20 accounting numerator.

        This is template image size, not executed-template size.
        Structural template words, including A7 flushed fall-through
        words, remain targeted words.
        """
        return self.template.image_word_count

    @property
    def background_filler_count(self) -> int:
        return len(self.background_fillers)

    @property
    def expected_executed_instruction_count(self) -> int:
        return len(
            self.expected_executed_word_offsets
        )

    @property
    def logical_word_end_exclusive(self) -> int:
        return (
            self.logical_word_start
            + self.image_word_count
        )

    @property
    def physical_word_addresses(self) -> Tuple[int, ...]:
        return tuple(
            physical_pc_for_logical_word(
                self.logical_word_start + offset
            )
            for offset in range(
                self.image_word_count
            )
        )

    @property
    def expected_executed_pcs(self) -> Tuple[int, ...]:
        return tuple(
            physical_pc_for_logical_word(
                self.logical_word_start + offset
            )
            for offset
            in self.expected_executed_word_offsets
        )

    @property
    def expected_executed_words(self) -> Tuple[int, ...]:
        return tuple(
            self.image_words[offset]
            for offset
            in self.expected_executed_word_offsets
        )


class StreamPlanningError(RuntimeError):
    """Raised when bounded stream planning becomes inconsistent."""


class BoundedProgramRing:
    """
    FIFO accounting model for the frozen 128-word runtime IMEM ring.

    This class deliberately does not touch RTL. It only proves that the
    planner never has more live program-image words than physical IMEM
    capacity.

    Allocation and release operate on complete stream blocks, so a
    template is never partially reclaimed.
    """

    def __init__(
        self,
        *,
        capacity_words: int = IMEM_WORD_CAPACITY,
    ) -> None:
        if (
            isinstance(capacity_words, bool)
            or not isinstance(capacity_words, int)
            or capacity_words <= 0
        ):
            raise ValueError(
                "capacity_words must be positive"
            )

        if capacity_words > IMEM_WORD_CAPACITY:
            raise ValueError(
                "capacity_words exceeds physical IMEM capacity"
            )

        self._capacity_words = capacity_words
        self._blocks: list[PlannedStreamBlock] = []
        self._used_words = 0

    @property
    def capacity_words(self) -> int:
        return self._capacity_words

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
    def pending_block_count(self) -> int:
        return len(self._blocks)

    @property
    def blocks(self) -> Tuple[PlannedStreamBlock, ...]:
        return tuple(self._blocks)

    def can_append(
        self,
        block: PlannedStreamBlock,
    ) -> bool:
        if not isinstance(
            block,
            PlannedStreamBlock,
        ):
            raise TypeError(
                "block must be PlannedStreamBlock"
            )

        return (
            block.image_word_count
            <= self.free_words
        )

    def append(
        self,
        block: PlannedStreamBlock,
    ) -> None:
        if not self.can_append(block):
            raise StreamPlanningError(
                "runtime IMEM ring has insufficient free space"
            )

        if self._blocks:
            expected_start = (
                self._blocks[-1]
                .logical_word_end_exclusive
            )

            if block.logical_word_start != expected_start:
                raise StreamPlanningError(
                    "stream block logical layout is not contiguous"
                )

        self._blocks.append(block)
        self._used_words += (
            block.image_word_count
        )

    def release_oldest(
        self,
        *,
        template_instance_id: int,
    ) -> PlannedStreamBlock:
        if not self._blocks:
            raise StreamPlanningError(
                "cannot release from an empty program ring"
            )

        oldest = self._blocks[0]

        if (
            oldest.template_instance_id
            != template_instance_id
        ):
            raise StreamPlanningError(
                "program-ring release must preserve FIFO order"
            )

        self._blocks.pop(0)

        self._used_words -= (
            oldest.image_word_count
        )

        if self._used_words < 0:
            raise RuntimeError(
                "program-ring accounting underflow"
            )

        return oldest

@dataclass(frozen=True)
class AcceptedBlockResult:
    """
    Immutable completion record for one fully consumed stream block.
    """

    template_instance_id: int
    first_instruction_index: int
    last_instruction_index: int
    accepted_instruction_count: int

    def __post_init__(self) -> None:
        if self.template_instance_id <= 0:
            raise ValueError(
                "template_instance_id must be positive"
            )

        if self.first_instruction_index <= 0:
            raise ValueError(
                "first_instruction_index must be positive"
            )

        if (
            self.last_instruction_index
            < self.first_instruction_index
        ):
            raise ValueError(
                "last_instruction_index precedes first"
            )

        if self.accepted_instruction_count <= 0:
            raise ValueError(
                "accepted_instruction_count must be positive"
            )

        if (
            self.last_instruction_index
            - self.first_instruction_index
            + 1
            != self.accepted_instruction_count
        ):
            raise ValueError(
                "accepted instruction range is not contiguous"
            )


class StreamExecutionMismatch(RuntimeError):
    """
    Raised when RTL accepted-program order diverges from the planned
    stream.
    """


class AcceptedStreamTracker:
    """
    Validate planned stream blocks against the architectural accepted
    ExecutionEvent stream.

    This tracker uses only executed-program-order events. Clock cycles,
    stalls, and flushed/wrong-path instructions do not advance it.

    Memory usage is bounded by the blocks currently resident in the
    runtime IMEM ring.
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

        self._blocks: list[
            PlannedStreamBlock
        ] = []

        self._block_progress = 0

        self._next_expected_instruction_index = (
            first_expected_instruction_index
        )

        self._accepted_count = 0

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
    def pending_block_count(self) -> int:
        return len(self._blocks)

    @property
    def current_block(
        self,
    ) -> PlannedStreamBlock | None:
        if not self._blocks:
            return None

        return self._blocks[0]

    def enqueue(
        self,
        block: PlannedStreamBlock,
    ) -> None:
        if not isinstance(
            block,
            PlannedStreamBlock,
        ):
            raise TypeError(
                "block must be PlannedStreamBlock"
            )

        if self._blocks:
            previous = self._blocks[-1]

            expected_logical_start = (
                previous.logical_word_end_exclusive
            )

            if (
                block.logical_word_start
                != expected_logical_start
            ):
                raise StreamExecutionMismatch(
                    "accepted-stream blocks are not "
                    "logically contiguous"
                )

        expected_first_index = (
            self._next_expected_instruction_index
            + sum(
                pending.expected_executed_instruction_count
                for pending in self._blocks
            )
        )

        if (
            block.first_executed_instruction_index
            != expected_first_index
        ):
            raise StreamExecutionMismatch(
                "block executed-index layout is not contiguous: "
                f"expected={expected_first_index}, "
                f"observed="
                f"{block.first_executed_instruction_index}"
            )

        self._blocks.append(
            block
        )

    def observe(
        self,
        event: ExecutionEvent,
    ) -> AcceptedBlockResult | None:
        """
        Consume exactly one architecturally accepted instruction.

        Returns AcceptedBlockResult only when the event completes the
        current stream block.
        """
        if not isinstance(
            event,
            ExecutionEvent,
        ):
            raise TypeError(
                "event must be ExecutionEvent"
            )

        if not self._blocks:
            raise StreamExecutionMismatch(
                "accepted instruction arrived with "
                "no planned stream block"
            )

        if (
            event.instruction_index
            != self._next_expected_instruction_index
        ):
            raise StreamExecutionMismatch(
                "accepted instruction_index mismatch: "
                f"expected="
                f"{self._next_expected_instruction_index}, "
                f"observed={event.instruction_index}"
            )

        block = self._blocks[0]

        expected_pcs = (
            block.expected_executed_pcs
        )

        expected_words = (
            block.expected_executed_words
        )

        if (
            self._block_progress
            >= len(expected_pcs)
        ):
            raise RuntimeError(
                "stream block progress overflow"
            )

        expected_pc = expected_pcs[
            self._block_progress
        ]

        expected_word = expected_words[
            self._block_progress
        ]

        if event.pc != expected_pc:
            raise StreamExecutionMismatch(
                "accepted PC diverged from stream plan: "
                f"instruction_index={event.instruction_index}, "
                f"expected_pc=0x{expected_pc:03x}, "
                f"observed_pc=0x{event.pc:03x}"
            )

        if event.instruction != expected_word:
            raise StreamExecutionMismatch(
                "accepted instruction word diverged "
                "from stream plan: "
                f"instruction_index={event.instruction_index}, "
                f"pc=0x{event.pc:03x}, "
                f"expected=0x{expected_word:08x}, "
                f"observed=0x{event.instruction:08x}"
            )

        self._accepted_count += 1
        self._next_expected_instruction_index += 1
        self._block_progress += 1

        if (
            self._block_progress
            != block.expected_executed_instruction_count
        ):
            return None

        completed = self._blocks.pop(0)

        first_index = (
            completed.first_executed_instruction_index
        )

        accepted_count = (
            completed.expected_executed_instruction_count
        )

        last_index = (
            first_index
            + accepted_count
            - 1
        )

        self._block_progress = 0

        return AcceptedBlockResult(
            template_instance_id=(
                completed.template_instance_id
            ),
            first_instruction_index=(
                first_index
            ),
            last_instruction_index=(
                last_index
            ),
            accepted_instruction_count=(
                accepted_count
            ),
        )

class AdaptiveEpochStreamPlanner:
    """
    Deterministic stream planner for one active Adaptive-CGS campaign.

    The planner separates three independent quantities:

      1. template image words:
           used by the frozen 80:20 filler scheduler;

      2. expected executed instructions:
           used to decide when a nominal epoch has enough complete
           template instances;

      3. physical IMEM occupancy:
           bounded by the 128-word runtime ring.

    The planner never splits a template instance.
    """

    def __init__(
        self,
        *,
        coordinator: AdaptiveEpochCoordinator,
        template_realizer: TemplateRealizer,
        filler_scheduler: CampaignFillerScheduler,
        nominal_epoch_instructions: int,
        initial_logical_word_index: int = 0,
        first_executed_instruction_index: int = 1,
    ) -> None:
        if not isinstance(
            coordinator,
            AdaptiveEpochCoordinator,
        ):
            raise TypeError(
                "coordinator must be AdaptiveEpochCoordinator"
            )

        if not isinstance(
            template_realizer,
            TemplateRealizer,
        ):
            raise TypeError(
                "template_realizer must be TemplateRealizer"
            )

        if not isinstance(
            filler_scheduler,
            CampaignFillerScheduler,
        ):
            raise TypeError(
                "filler_scheduler must be CampaignFillerScheduler"
            )

        if (
            isinstance(nominal_epoch_instructions, bool)
            or not isinstance(
                nominal_epoch_instructions,
                int,
            )
            or nominal_epoch_instructions <= 0
        ):
            raise ValueError(
                "nominal_epoch_instructions "
                "must be positive"
            )

        if (
            isinstance(initial_logical_word_index, bool)
            or not isinstance(
                initial_logical_word_index,
                int,
            )
            or initial_logical_word_index < 0
        ):
            raise ValueError(
                "initial_logical_word_index "
                "must be non-negative"
            )

        if (
            isinstance(
                first_executed_instruction_index,
                bool,
            )
            or not isinstance(
                first_executed_instruction_index,
                int,
            )
            or first_executed_instruction_index <= 0
        ):
            raise ValueError(
                "first_executed_instruction_index "
                "must be positive"
            )

        self._coordinator = coordinator
        self._realizer = template_realizer
        self._filler_scheduler = (
            filler_scheduler
        )

        self._nominal_epoch_instructions = (
            nominal_epoch_instructions
        )

        self._next_logical_word_index = (
            initial_logical_word_index
        )

        self._next_executed_instruction_index = (
            first_executed_instruction_index
        )

        self._next_template_instance_id = 1

        self._epoch_start: EpochStart | None = None
        self._planned_epoch_executed = 0

    @property
    def active(self) -> bool:
        return self._epoch_start is not None

    @property
    def epoch_start(self) -> EpochStart | None:
        return self._epoch_start

    @property
    def planned_epoch_executed_instructions(
        self,
    ) -> int:
        return self._planned_epoch_executed

    @property
    def nominal_epoch_instructions(self) -> int:
        return self._nominal_epoch_instructions

    @property
    def next_logical_word_index(self) -> int:
        return self._next_logical_word_index

    @property
    def next_executed_instruction_index(self) -> int:
        return (
            self._next_executed_instruction_index
        )

    @property
    def epoch_plan_complete(self) -> bool:
        return (
            self.active
            and self._planned_epoch_executed
            >= self._nominal_epoch_instructions
        )

    def begin_epoch(self) -> EpochStart:
        if self._epoch_start is not None:
            raise RuntimeError(
                "stream planner already has an active epoch"
            )

        start = self._coordinator.begin_epoch()

        self._epoch_start = start
        self._planned_epoch_executed = 0

        return start

    def build_next_block(
        self,
    ) -> PlannedStreamBlock:
        if self._epoch_start is None:
            raise RuntimeError(
                "cannot build stream block without active epoch"
            )

        if self.epoch_plan_complete:
            raise RuntimeError(
                "nominal epoch plan is already complete"
            )

        start = self._epoch_start

        start_pc = physical_pc_for_logical_word(
            self._next_logical_word_index
        )

        template = self._realizer.realize(
            start.decision.arm_id,
            start.target,
            start_pc=start_pc,
        )

        # Frozen 80:20 mix uses complete template image words.
        # A7 therefore contributes four targeted words even though only
        # two are architecturally executed.
        filler_due = (
            self._filler_scheduler
            .schedule_after_template(
                template.image_word_count
            )
        )

        if (
            filler_due
            > MAX_BACKGROUND_FILLERS_PER_TEMPLATE
        ):
            raise StreamPlanningError(
                "unexpected filler burst exceeds bounded "
                "per-template stream assumption"
            )

        protected_registers = (
            _positive_targets(start.target)
        )

        fillers = tuple(
            build_filler_instruction(
                kind=FillerKind.CAMPAIGN_BACKGROUND,
                protected_registers=protected_registers,
            )
            for _ in range(filler_due)
        )

        image_words = (
            template.words
            + tuple(
                filler.word
                for filler in fillers
            )
        )

        template_executed_offsets = (
            template.expected_executed_word_indices
        )

        filler_base = template.image_word_count

        filler_executed_offsets = tuple(
            filler_base + offset
            for offset in range(
                len(fillers)
            )
        )

        expected_executed_offsets = (
            template_executed_offsets
            + filler_executed_offsets
        )

        witnesses = build_template_witnesses(
            template,
            template_instance_id=(
                self._next_template_instance_id
            ),
            first_executed_instruction_index=(
                self._next_executed_instruction_index
            ),
        )

        block = PlannedStreamBlock(
            template_instance_id=(
                self._next_template_instance_id
            ),
            arm_id=start.decision.arm_id,
            target=start.target,
            logical_word_start=(
                self._next_logical_word_index
            ),
            first_executed_instruction_index=(
                self._next_executed_instruction_index
            ),
            template=template,
            background_fillers=fillers,
            image_words=image_words,
            expected_executed_word_offsets=(
                expected_executed_offsets
            ),
            witnesses=witnesses,
        )

        self._next_logical_word_index += (
            block.image_word_count
        )

        self._next_executed_instruction_index += (
            block.expected_executed_instruction_count
        )

        self._next_template_instance_id += 1

        self._planned_epoch_executed += (
            block.expected_executed_instruction_count
        )

        return block

    def register_block_witnesses(
        self,
        block: PlannedStreamBlock,
    ) -> None:
        """
        Register a block's exact dependencies only after the block has
        actually been committed to runtime IMEM.

        Keeping generation and registration separate prevents a failed
        ring allocation or failed IMEM write from leaving phantom
        reward witnesses behind.
        """
        if self._epoch_start is None:
            raise RuntimeError(
                "cannot register block without active epoch"
            )

        if block.arm_id is not (
            self._epoch_start.decision.arm_id
        ):
            raise ValueError(
                "block belongs to a different active arm"
            )

        self._coordinator.register_attribution_witnesses(
            block.witnesses
        )

    def close_planning_epoch(self) -> None:
        """
        Clear planner-local epoch state.

        This does NOT finish the adaptive epoch in the coordinator.
        Runtime integration must first process all accepted instructions,
        L2 hits, provenance pruning, and then call coordinator.finish_epoch()
        with the actual executed-instruction count.
        """
        if self._epoch_start is None:
            raise RuntimeError(
                "stream planner has no active epoch"
            )

        if not self.epoch_plan_complete:
            raise RuntimeError(
                "cannot close planning epoch before "
                "nominal executed target is reached"
            )

        self._epoch_start = None
        self._planned_epoch_executed = 0
