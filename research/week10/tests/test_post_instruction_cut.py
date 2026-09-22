from dataclasses import dataclass

from research.week10.adaptive.post_instruction_cut import (
    complete_post_instruction_cut,
)


@dataclass(frozen=True)
class SyntheticCheckpoint:
    executed_instructions: int
    l2_intent_count: int


class SyntheticCoverage:
    """
    Minimal synchronous-checkpoint model.

    It intentionally reproduces the relevant CoverageCollector
    contract: record_instruction(N) immediately emits a checkpoint
    when N is an interval boundary.
    """

    def __init__(self, checkpoint_interval: int = 1000):
        if checkpoint_interval <= 0:
            raise ValueError(
                "checkpoint_interval must be positive"
            )

        self.checkpoint_interval = checkpoint_interval
        self.executed_instructions = 0
        self.l2_intent_count = 0
        self.checkpoints = []

    def record_l2_intent(self) -> None:
        self.l2_intent_count += 1

    def record_instruction(
        self,
        *,
        instruction_id: int,
        cycle: int,
    ) -> None:
        del cycle

        expected = self.executed_instructions + 1

        if instruction_id != expected:
            raise AssertionError(
                "synthetic executed-instruction discontinuity"
            )

        self.executed_instructions += 1

        if (
            self.executed_instructions
            % self.checkpoint_interval
            == 0
        ):
            self.checkpoints.append(
                SyntheticCheckpoint(
                    executed_instructions=(
                        self.executed_instructions
                    ),
                    l2_intent_count=(
                        self.l2_intent_count
                    ),
                )
            )


def run_consistent_cut_stream(
    instruction_count: int,
    *,
    l2_hit_indices=(),
):
    coverage = SyntheticCoverage(
        checkpoint_interval=1000
    )

    observed_count = 0
    hit_indices = set(l2_hit_indices)

    for instruction_index in range(
        1,
        instruction_count + 1,
    ):
        def observe_coverage(
            index=instruction_index,
        ):
            if index in hit_indices:
                coverage.record_l2_intent()

        observed_count = (
            complete_post_instruction_cut(
                observed_count=observed_count,
                instruction_index=instruction_index,
                cycle=instruction_index,
                coverage=coverage,
                observe_coverage=observe_coverage,
            )
        )

    assert (
        observed_count
        == coverage.executed_instructions
    )

    return coverage


def test_below_first_boundary_emits_no_checkpoint():
    coverage = run_consistent_cut_stream(
        999,
        l2_hit_indices=(999,),
    )

    assert coverage.executed_instructions == 999
    assert coverage.l2_intent_count == 1
    assert coverage.checkpoints == []


def test_boundary_1000_is_post_instruction_consistent_cut():
    # Instruction 1000 deliberately creates new L2 Intent.
    # The checkpoint must therefore contain that mutation.
    coverage = run_consistent_cut_stream(
        1000,
        l2_hit_indices=(1000,),
    )

    assert coverage.checkpoints == [
        SyntheticCheckpoint(
            executed_instructions=1000,
            l2_intent_count=1,
        )
    ]

    # Exact epoch-end state equals the checkpoint cut at N=1000.
    checkpoint = coverage.checkpoints[0]

    assert (
        checkpoint.executed_instructions
        == coverage.executed_instructions
    )

    assert (
        checkpoint.l2_intent_count
        == coverage.l2_intent_count
    )


def test_2500_emits_exactly_two_consistent_checkpoints():
    # Both checkpoint-boundary instructions deliberately mutate
    # L2 state, making off-by-one ordering deterministic.
    coverage = run_consistent_cut_stream(
        2500,
        l2_hit_indices=(1000, 2000),
    )

    assert coverage.checkpoints == [
        SyntheticCheckpoint(
            executed_instructions=1000,
            l2_intent_count=1,
        ),
        SyntheticCheckpoint(
            executed_instructions=2000,
            l2_intent_count=2,
        ),
    ]

    assert coverage.executed_instructions == 2500
    assert coverage.l2_intent_count == 2


def test_legacy_record_before_observe_is_detectably_inconsistent():
    """
    Mutation test for the original Week10 ordering.

    record_instruction(1000) occurs before the observer mutation.
    Therefore the emitted checkpoint has L2 state from instruction
    999 even though its executed counter says 1000.
    """

    coverage = SyntheticCoverage(
        checkpoint_interval=1000
    )

    for instruction_index in range(1, 1001):
        coverage.record_instruction(
            instruction_id=instruction_index,
            cycle=instruction_index,
        )

        if instruction_index == 1000:
            coverage.record_l2_intent()

    assert coverage.executed_instructions == 1000
    assert coverage.l2_intent_count == 1

    assert len(coverage.checkpoints) == 1

    checkpoint = coverage.checkpoints[0]

    assert checkpoint.executed_instructions == 1000

    # This mismatch is the consistent-cut violation that f-1 fixes.
    assert (
        checkpoint.l2_intent_count
        != coverage.l2_intent_count
    )

    assert checkpoint.l2_intent_count == 0
