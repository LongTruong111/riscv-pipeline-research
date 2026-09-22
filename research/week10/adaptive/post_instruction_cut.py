from __future__ import annotations

from typing import Callable, Protocol


class ExecutedInstructionCoverage(Protocol):
    """
    Minimal CoverageCollector interface required by the
    post-instruction consistent-cut coordinator.
    """

    @property
    def executed_instructions(self) -> int:
        ...

    def record_instruction(
        self,
        *,
        instruction_id: int,
        cycle: int,
    ) -> None:
        ...


def complete_post_instruction_cut(
    *,
    observed_count: int,
    instruction_index: int,
    cycle: int,
    coverage: ExecutedInstructionCoverage,
    observe_coverage: Callable[[], None],
) -> int:
    """
    Complete the coverage cut for one architecturally accepted event.

    Frozen Week10 semantics:

        coverage checkpoint at N
        =
        coverage state after every coverage observer for
        accepted instruction N has completed.

    CoverageCollector.record_instruction() may synchronously emit a
    checkpoint. Therefore observe_coverage() must execute first.

    This helper deliberately owns only ordering/accounting. Runtime
    stream reclamation remains outside the coverage cut.
    """

    if observed_count < 0:
        raise ValueError(
            "observed_count must be non-negative"
        )

    expected_instruction_index = (
        coverage.executed_instructions + 1
    )

    if instruction_index != expected_instruction_index:
        raise AssertionError(
            "executed-instruction continuity mismatch: "
            f"instruction_index={instruction_index}, "
            f"expected={expected_instruction_index}"
        )

    # Every coverage observer for instruction N must mutate its
    # state before record_instruction(N) is allowed to emit a
    # checkpoint.
    observe_coverage()

    observed_count += 1

    if observed_count != instruction_index:
        raise AssertionError(
            "coverage-observer continuity mismatch: "
            f"observed={observed_count}, "
            f"instruction_index={instruction_index}"
        )

    coverage.record_instruction(
        instruction_id=instruction_index,
        cycle=cycle,
    )

    if observed_count != coverage.executed_instructions:
        raise AssertionError(
            "post-instruction coverage cut is inconsistent: "
            f"observed={observed_count}, "
            f"executed={coverage.executed_instructions}"
        )

    return observed_count
