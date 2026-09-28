from __future__ import annotations

from dataclasses import dataclass

from research.week5.impl.execution_event import (
    ExecutionEvent,
)
from research.week10.adaptive.wrap_aware_architectural_model import (
    WrapAwareRV32ArchitecturalModel,
)
from research.week13.pure_random.control_realizer import (
    BRANCH_VARIANTS,
)
from research.week13.pure_random.family_sampler import (
    InstructionFamily,
)
from research.week13.pure_random.operand_realizer import (
    DMEM_BYTES,
    DMEM_WORD_BYTES,
    memory_base_choices,
)
from research.week13.pure_random.stream_planner import (
    PureRandomPlan,
)


@dataclass(frozen=True)
class M1PlanDiagnostics:
    """
    Deterministic telemetry derived from one already-generated M1 plan.

    This helper consumes no RNG and does not alter the plan.
    """

    family_counts: dict[str, int]

    branch_subtype_counts: dict[str, int]
    branch_taken_count: int
    branch_not_taken_count: int

    structural_nop_accepted_count: int

    lw_ea_histogram: dict[str, int]
    sw_ea_histogram: dict[str, int]

    memory_viable_base_set_size_histogram: dict[str, int]
    accepted_base_register_histogram: dict[str, int]


def _shadow_event(
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


def build_m1_plan_diagnostics(
    plan: PureRandomPlan,
) -> M1PlanDiagnostics:
    """
    Reconstruct protocol-required static M1 generator diagnostics.

    The architectural shadow is replayed only to recover the viable
    memory-base-set size that existed when each LW/SW payload was
    generated.

    Complexity:
        O(N) time for accepted budget N.

    Additional retained state:
        O(1) with respect to N. All histograms have frozen domains.
    """
    if not isinstance(plan, PureRandomPlan):
        raise TypeError(
            "plan must be PureRandomPlan"
        )

    family_counts = {
        family.value: 0
        for family in InstructionFamily
    }

    branch_subtype_counts = {
        name: 0
        for name, _encoder in BRANCH_VARIANTS
    }

    branch_taken_count = 0
    branch_not_taken_count = 0

    structural_nop_accepted_count = 0

    lw_ea_histogram = {
        str(ea): 0
        for ea in range(
            0,
            DMEM_BYTES,
            DMEM_WORD_BYTES,
        )
    }

    sw_ea_histogram = {
        str(ea): 0
        for ea in range(
            0,
            DMEM_BYTES,
            DMEM_WORD_BYTES,
        )
    }

    memory_viable_base_set_size_histogram = {
        str(size): 0
        for size in range(1, 33)
    }

    accepted_base_register_histogram = {
        f"x{reg}": 0
        for reg in range(32)
    }

    model = WrapAwareRV32ArchitecturalModel()

    next_instruction_index = 1

    for block in plan.blocks:
        if (
            block.first_accepted_instruction_index
            != next_instruction_index
        ):
            raise AssertionError(
                "plan accepted-instruction layout "
                "is not contiguous"
            )

        realized = block.realized
        family = realized.family

        family_counts[family.value] += 1

        accepted_structural = set(
            block.accepted_word_indices
        ).intersection(
            realized.structural_word_indices
        )

        structural_nop_accepted_count += len(
            accepted_structural
        )

        if family is InstructionFamily.BRANCH:
            if (
                realized.mnemonic
                not in branch_subtype_counts
            ):
                raise AssertionError(
                    "unknown frozen branch subtype: "
                    f"{realized.mnemonic}"
                )

            branch_subtype_counts[
                realized.mnemonic
            ] += 1

            expected_path = (
                realized
                .expected_executed_word_indices
            )

            if expected_path == (0, 3):
                branch_taken_count += 1

            elif expected_path == (
                0,
                1,
                2,
                3,
            ):
                branch_not_taken_count += 1

            else:
                raise AssertionError(
                    "branch block has unexpected "
                    f"execution path: {expected_path}"
                )

        if family in (
            InstructionFamily.LW,
            InstructionFamily.SW,
        ):
            if (
                realized.effective_address
                is None
                or realized.rs1 is None
                or realized.immediate is None
            ):
                raise AssertionError(
                    "memory block lacks frozen "
                    "realization metadata"
                )

            ea = realized.effective_address

            choices = memory_base_choices(
                model.registers(),
                ea,
            )

            viable_size = len(choices)

            memory_viable_base_set_size_histogram[
                str(viable_size)
            ] += 1

            accepted_base_register_histogram[
                f"x{realized.rs1}"
            ] += 1

            if family is InstructionFamily.LW:
                lw_ea_histogram[
                    str(ea)
                ] += 1
            else:
                sw_ea_histogram[
                    str(ea)
                ] += 1

            matching_choices = tuple(
                choice
                for choice in choices
                if (
                    choice.rs1 == realized.rs1
                    and choice.immediate
                    == realized.immediate
                )
            )

            if len(matching_choices) != 1:
                raise AssertionError(
                    "realized memory base/immediate "
                    "is not exactly one viable choice"
                )

        for word_index in (
            block.accepted_word_indices
        ):
            pc = realized.physical_pc_for_word(
                word_index
            )

            if pc != model.expected_pc:
                raise AssertionError(
                    "diagnostic shadow PC mismatch: "
                    f"planned={pc:#x}, "
                    f"shadow={model.expected_pc:#x}"
                )

            instruction = realized.words[
                word_index
            ]

            step = model.step(
                _shadow_event(
                    instruction_index=(
                        next_instruction_index
                    ),
                    pc=pc,
                    instruction=instruction,
                )
            )

            if not step.pc_match:
                raise AssertionError(
                    "diagnostic shadow replay "
                    "reported PC mismatch"
                )

            next_instruction_index += 1

    if (
        next_instruction_index
        != plan.accepted_instruction_count + 1
    ):
        raise AssertionError(
            "diagnostic replay accepted count mismatch"
        )

    if model.expected_pc != plan.final_expected_pc:
        raise AssertionError(
            "diagnostic replay final PC mismatch"
        )

    if (
        len(plan.blocks)
        + structural_nop_accepted_count
        != plan.accepted_instruction_count
    ):
        raise AssertionError(
            "payload/structural-NOP conservation failed"
        )

    if (
        branch_taken_count
        + branch_not_taken_count
        != family_counts[
            InstructionFamily.BRANCH.value
        ]
    ):
        raise AssertionError(
            "branch outcome accounting mismatch"
        )

    memory_payload_count = (
        family_counts[
            InstructionFamily.LW.value
        ]
        + family_counts[
            InstructionFamily.SW.value
        ]
    )

    if (
        sum(
            memory_viable_base_set_size_histogram
            .values()
        )
        != memory_payload_count
    ):
        raise AssertionError(
            "memory viable-set accounting mismatch"
        )

    if (
        sum(
            accepted_base_register_histogram
            .values()
        )
        != memory_payload_count
    ):
        raise AssertionError(
            "memory base-register accounting mismatch"
        )

    return M1PlanDiagnostics(
        family_counts=family_counts,
        branch_subtype_counts=(
            branch_subtype_counts
        ),
        branch_taken_count=(
            branch_taken_count
        ),
        branch_not_taken_count=(
            branch_not_taken_count
        ),
        structural_nop_accepted_count=(
            structural_nop_accepted_count
        ),
        lw_ea_histogram=lw_ea_histogram,
        sw_ea_histogram=sw_ea_histogram,
        memory_viable_base_set_size_histogram=(
            memory_viable_base_set_size_histogram
        ),
        accepted_base_register_histogram=(
            accepted_base_register_histogram
        ),
    )
