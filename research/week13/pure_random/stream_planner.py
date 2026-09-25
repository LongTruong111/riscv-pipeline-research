from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from research.week5.impl.execution_event import ExecutionEvent
from research.week10.adaptive.wrap_aware_architectural_model import (
    WrapAwareRV32ArchitecturalModel,
)
from research.week13.pure_random.campaign_seed import (
    PureRandomSeeds,
    build_campaign_rngs,
)
from research.week13.pure_random.control_realizer import (
    realize_control,
)
from research.week13.pure_random.family_sampler import (
    InstructionFamily,
    sample_family,
)
from research.week13.pure_random.operand_realizer import (
    realize_non_control,
)
from research.week13.pure_random.realized_block import (
    RealizedPureRandomBlock,
)


PLAN_SCHEMA = "week13.m1-pr.plan.v1"

CONTROL_FAMILIES = (
    InstructionFamily.BRANCH,
    InstructionFamily.JAL,
    InstructionFamily.JALR,
)


@dataclass(frozen=True)
class PlannedPureRandomBlock:
    block_index: int
    first_accepted_instruction_index: int
    realized: RealizedPureRandomBlock
    accepted_word_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.block_index, bool)
            or not isinstance(self.block_index, int)
            or self.block_index <= 0
        ):
            raise ValueError(
                "block_index must be positive"
            )

        if (
            isinstance(
                self.first_accepted_instruction_index,
                bool,
            )
            or not isinstance(
                self.first_accepted_instruction_index,
                int,
            )
            or self.first_accepted_instruction_index <= 0
        ):
            raise ValueError(
                "first_accepted_instruction_index "
                "must be positive"
            )

        if not self.accepted_word_indices:
            raise ValueError(
                "accepted_word_indices must not be empty"
            )

        full = (
            self.realized.expected_executed_word_indices
        )

        prefix_length = len(
            self.accepted_word_indices
        )

        if (
            self.accepted_word_indices
            != full[:prefix_length]
        ):
            raise ValueError(
                "accepted_word_indices must be an exact "
                "prefix of expected executed order"
            )

    @property
    def accepted_instruction_count(
        self,
    ) -> int:
        return len(
            self.accepted_word_indices
        )

    @property
    def is_partial(
        self,
    ) -> bool:
        return (
            self.accepted_word_indices
            != self.realized.expected_executed_word_indices
        )


@dataclass(frozen=True)
class PureRandomPlan:
    root_seed: int
    seeds: PureRandomSeeds
    requested_accepted_budget: int

    blocks: tuple[
        PlannedPureRandomBlock,
        ...
    ]

    accepted_instruction_count: int
    final_expected_pc: int

    def __post_init__(self) -> None:
        if self.seeds.root_seed != self.root_seed:
            raise ValueError(
                "seed bundle root does not match plan root"
            )

        if (
            self.accepted_instruction_count
            != self.requested_accepted_budget
        ):
            raise ValueError(
                "plan must terminate at exact accepted budget"
            )

        counted = sum(
            block.accepted_instruction_count
            for block in self.blocks
        )

        if counted != self.accepted_instruction_count:
            raise ValueError(
                "block accepted counts do not match plan count"
            )

        if not self.blocks:
            raise ValueError(
                "plan must contain at least one block"
            )

        for index, block in enumerate(
            self.blocks,
            start=1,
        ):
            if block.block_index != index:
                raise ValueError(
                    "block indices must be contiguous"
                )

        partial_blocks = [
            block
            for block in self.blocks
            if block.is_partial
        ]

        if len(partial_blocks) > 1:
            raise ValueError(
                "only the final block may be partial"
            )

        if (
            partial_blocks
            and partial_blocks[0] is not self.blocks[-1]
        ):
            raise ValueError(
                "partial block must be final"
            )

    def hash_payload(self) -> dict:
        return {
            "schema": PLAN_SCHEMA,
            "root_seed": self.root_seed,
            "family_seed": self.seeds.family_seed,
            "operand_seed": self.seeds.operand_seed,
            "requested_accepted_budget": (
                self.requested_accepted_budget
            ),
            "accepted_instruction_count": (
                self.accepted_instruction_count
            ),
            "final_expected_pc": self.final_expected_pc,
            "blocks": [
                {
                    "block_index": block.block_index,
                    "first_accepted_instruction_index": (
                        block.first_accepted_instruction_index
                    ),
                    "family": block.realized.family.value,
                    "mnemonic": block.realized.mnemonic,
                    "start_pc": block.realized.start_pc,
                    "words": list(
                        block.realized.words
                    ),
                    "expected_executed_word_indices": list(
                        block.realized
                        .expected_executed_word_indices
                    ),
                    "accepted_word_indices": list(
                        block.accepted_word_indices
                    ),
                    "structural_word_indices": list(
                        block.realized.structural_word_indices
                    ),
                    "rd": block.realized.rd,
                    "rs1": block.realized.rs1,
                    "rs2": block.realized.rs2,
                    "immediate": block.realized.immediate,
                    "effective_address": (
                        block.realized.effective_address
                    ),
                }
                for block in self.blocks
            ],
        }

    @property
    def plan_hash(self) -> str:
        encoded = json.dumps(
            self.hash_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")

        return hashlib.sha256(
            encoded
        ).hexdigest()


def _make_shadow_event(
    *,
    instruction_index: int,
    pc: int,
    instruction: int,
) -> ExecutionEvent:
    return ExecutionEvent(
        instruction_index=instruction_index,
        cycle=instruction_index,
        pc=pc,
        instruction=instruction,
        rs1=(instruction >> 15) & 0x1F,
        rs2=(instruction >> 20) & 0x1F,
        rd=(instruction >> 7) & 0x1F,
        uses_rs1=False,
        uses_rs2=False,
        writes_rd=False,
        producer_type="NONE",
        consumer_type="NONE",
    )


def _advance_shadow(
    model: WrapAwareRV32ArchitecturalModel,
    realized: RealizedPureRandomBlock,
    accepted_word_indices: tuple[int, ...],
    *,
    first_instruction_index: int,
) -> int:
    next_index = first_instruction_index

    for word_index in accepted_word_indices:
        pc = realized.physical_pc_for_word(
            word_index
        )

        if pc != model.expected_pc:
            raise AssertionError(
                "planned block does not match shadow fetch PC: "
                f"planned={pc:#x}, "
                f"shadow={model.expected_pc:#x}"
            )

        step = model.step(
            _make_shadow_event(
                instruction_index=next_index,
                pc=pc,
                instruction=realized.words[
                    word_index
                ],
            )
        )

        if not step.pc_match:
            raise AssertionError(
                "shadow replay reported PC mismatch"
            )

        next_index += 1

    return next_index


def generate_pure_random_plan(
    root_seed: int,
    accepted_budget: int,
) -> PureRandomPlan:
    """
    Generate one deterministic M1-PR offline plan.

    The final resident block may be only partially consumed in
    accepted-program order. No synthetic event is generated to finish
    that block.

    Complexity:
        O(N) time for accepted budget N.
        O(N) retained plan storage.
    """
    if (
        isinstance(accepted_budget, bool)
        or not isinstance(accepted_budget, int)
        or accepted_budget <= 0
    ):
        raise ValueError(
            "accepted_budget must be a positive integer"
        )

    rngs = build_campaign_rngs(
        root_seed
    )

    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    blocks: list[
        PlannedPureRandomBlock
    ] = []

    accepted_count = 0
    next_instruction_index = 1
    block_index = 1

    while accepted_count < accepted_budget:
        family = sample_family(
            rngs.family_rng
        )

        start_pc = model.expected_pc

        if family in CONTROL_FAMILIES:
            realized = realize_control(
                family,
                operand_rng=rngs.operand_rng,
                model=model,
                start_pc=start_pc,
            )
        else:
            realized = realize_non_control(
                family,
                operand_rng=rngs.operand_rng,
                model=model,
                start_pc=start_pc,
            )

        remaining = (
            accepted_budget
            - accepted_count
        )

        full_expected = (
            realized.expected_executed_word_indices
        )

        prefix_length = min(
            remaining,
            len(full_expected),
        )

        accepted_prefix = (
            full_expected[:prefix_length]
        )

        planned = PlannedPureRandomBlock(
            block_index=block_index,
            first_accepted_instruction_index=(
                next_instruction_index
            ),
            realized=realized,
            accepted_word_indices=accepted_prefix,
        )

        blocks.append(
            planned
        )

        next_instruction_index = (
            _advance_shadow(
                model,
                realized,
                accepted_prefix,
                first_instruction_index=(
                    next_instruction_index
                ),
            )
        )

        accepted_count += (
            planned.accepted_instruction_count
        )

        if planned.is_partial:
            if accepted_count != accepted_budget:
                raise AssertionError(
                    "partial block before exact budget"
                )

            break

        block_index += 1

    return PureRandomPlan(
        root_seed=root_seed,
        seeds=rngs.seeds,
        requested_accepted_budget=(
            accepted_budget
        ),
        blocks=tuple(
            blocks
        ),
        accepted_instruction_count=(
            accepted_count
        ),
        final_expected_pc=model.expected_pc,
    )
