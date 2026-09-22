from __future__ import annotations

from dataclasses import dataclass

import pytest

from research.week10.adaptive.campaign_runner import (
    IMEM_WORD_CAPACITY,
    MAX_STREAM_BLOCK_WORDS,
)
from research.week10.adaptive.intra_epoch_feeder import (
    EBD_RESERVE_WORDS,
    plan_next_capacity_safe_entry,
    refill_threshold_words,
)


@dataclass(frozen=True)
class FakeEntry:
    image_word_count: int
    expected_executed_instruction_count: int
    kind: str


class FakePlanner:
    """
    Minimal deterministic planner model for admission-control tests.

    Payload models a two-word arm with the frozen cumulative 80:20
    filler schedule:

        block 1: 2 targeted words
        block 2: 2 targeted + 1 filler
        block 3: 2 targeted words
        block 4: 2 targeted + 1 filler
        ...

    All words in this synthetic A0-like stream are architecturally
    executed.  The epoch begins with one already-planned EBD.
    """

    def __init__(
        self,
        *,
        nominal_epoch_instructions: int,
    ) -> None:
        self.active = True

        self.nominal_epoch_instructions = (
            nominal_epoch_instructions
        )

        # EBD_t is instruction one of the epoch denominator.
        self.planned_epoch_executed = 1

        self.pending_boundary_delimiter = None

        self.build_calls = 0
        self.boundary_calls = 0

        self.payload_image_words = 0
        self.last_payload_planned_before = None

    @property
    def epoch_plan_complete(self) -> bool:
        return (
            self.planned_epoch_executed
            >= self.nominal_epoch_instructions
        )

    def build_next_block(self) -> FakeEntry:
        if self.epoch_plan_complete:
            raise RuntimeError(
                "payload is already complete"
            )

        self.build_calls += 1

        self.last_payload_planned_before = (
            self.planned_epoch_executed
        )

        # Two targeted words per template.
        #
        # Frozen 4:1 image mix means every second such template
        # receives one filler:
        #
        #   2, 3, 2, 3, ...
        image_words = (
            3
            if self.build_calls % 2 == 0
            else 2
        )

        entry = FakeEntry(
            image_word_count=image_words,
            expected_executed_instruction_count=(
                image_words
            ),
            kind="PAYLOAD",
        )

        self.payload_image_words += image_words

        self.planned_epoch_executed += (
            entry.expected_executed_instruction_count
        )

        return entry

    def plan_next_boundary_delimiter(
        self,
    ) -> FakeEntry:
        if not self.epoch_plan_complete:
            raise RuntimeError(
                "cannot place boundary inside "
                "incomplete payload"
            )

        if (
            self.pending_boundary_delimiter
            is not None
        ):
            raise RuntimeError(
                "boundary already planned"
            )

        self.boundary_calls += 1

        delimiter = FakeEntry(
            image_word_count=1,
            expected_executed_instruction_count=1,
            kind="EBD",
        )

        self.pending_boundary_delimiter = (
            delimiter
        )

        return delimiter


def test_refill_threshold_reserves_one_word_for_next_ebd():
    assert (
        refill_threshold_words(
            preseed_next_boundary=False
        )
        == MAX_STREAM_BLOCK_WORDS
    )

    assert (
        refill_threshold_words(
            preseed_next_boundary=True
        )
        == (
            MAX_STREAM_BLOCK_WORDS
            + EBD_RESERVE_WORDS
        )
    )


def test_capacity_guard_does_not_mutate_payload_planner_when_full():
    planner = FakePlanner(
        nominal_epoch_instructions=500
    )

    planned_before = (
        planner.planned_epoch_executed
    )

    entry = plan_next_capacity_safe_entry(
        planner,
        free_words=(
            MAX_STREAM_BLOCK_WORDS
        ),
        preseed_next_boundary=True,
    )

    assert entry is None
    assert planner.build_calls == 0

    assert (
        planner.planned_epoch_executed
        == planned_before
    )


def test_capacity_guard_builds_one_complete_block_when_safe():
    planner = FakePlanner(
        nominal_epoch_instructions=500
    )

    entry = plan_next_capacity_safe_entry(
        planner,
        free_words=(
            MAX_STREAM_BLOCK_WORDS
            + EBD_RESERVE_WORDS
        ),
        preseed_next_boundary=True,
    )

    assert entry is not None
    assert entry.kind == "PAYLOAD"

    assert (
        entry.image_word_count
        <= MAX_STREAM_BLOCK_WORDS
    )

    assert planner.build_calls == 1


def test_completed_payload_preseeds_exactly_one_boundary():
    planner = FakePlanner(
        nominal_epoch_instructions=1
    )

    assert planner.epoch_plan_complete

    delimiter = plan_next_capacity_safe_entry(
        planner,
        free_words=1,
        preseed_next_boundary=True,
    )

    assert delimiter is not None
    assert delimiter.kind == "EBD"
    assert delimiter.image_word_count == 1

    assert planner.boundary_calls == 1

    duplicate = plan_next_capacity_safe_entry(
        planner,
        free_words=1,
        preseed_next_boundary=True,
    )

    assert duplicate is None
    assert planner.boundary_calls == 1


def test_nominal_500_streams_through_bounded_128_word_window():
    planner = FakePlanner(
        nominal_epoch_instructions=500
    )

    # EBD_t is initially resident.
    resident_entries = [
        FakeEntry(
            image_word_count=1,
            expected_executed_instruction_count=1,
            kind="ACTIVE_EBD",
        )
    ]

    used_words = 1
    max_used_words = used_words

    released_entries = 0
    capacity_block_events = 0

    generated_image_words = 1

    min_free_after_payload_commit = (
        IMEM_WORD_CAPACITY
    )

    while True:
        free_words = (
            IMEM_WORD_CAPACITY
            - used_words
        )

        entry = plan_next_capacity_safe_entry(
            planner,
            free_words=free_words,
            preseed_next_boundary=True,
        )

        if entry is not None:
            resident_entries.append(entry)

            used_words += entry.image_word_count

            generated_image_words += (
                entry.image_word_count
            )

            max_used_words = max(
                max_used_words,
                used_words,
            )

            assert (
                used_words
                <= IMEM_WORD_CAPACITY
            )

            if entry.kind == "PAYLOAD":
                free_after_commit = (
                    IMEM_WORD_CAPACITY
                    - used_words
                )

                min_free_after_payload_commit = min(
                    min_free_after_payload_commit,
                    free_after_commit,
                )

                # Until payload planning finishes, one slot must remain
                # available for EBD_(t+1).
                assert (
                    free_after_commit
                    >= EBD_RESERVE_WORDS
                )

                continue

            assert entry.kind == "EBD"
            break

        # Admission is temporarily blocked by resident capacity.
        #
        # Model one FIFO stream entry finishing accepted execution and
        # being reclaimed before the next refill attempt.
        capacity_block_events += 1

        assert resident_entries, (
            "capacity feeder deadlocked with no "
            "resident entry available for release"
        )

        released = resident_entries.pop(0)

        used_words -= released.image_word_count
        released_entries += 1

        assert used_words >= 0

    assert planner.epoch_plan_complete

    assert (
        planner.planned_epoch_executed
        >= 500
    )

    # Complete-template policy:
    # immediately before the final payload block the target had not yet
    # been reached; that whole block is what crosses the nominal target.
    assert (
        planner.last_payload_planned_before
        is not None
    )

    assert (
        planner.last_payload_planned_before
        < 500
    )

    assert planner.boundary_calls == 1

    # This is the actual property T10.9g needs:
    # logical epoch image is much larger than physical IMEM, while
    # resident occupancy never exceeds 128 words.
    assert (
        generated_image_words
        > IMEM_WORD_CAPACITY
    )

    assert (
        max_used_words
        <= IMEM_WORD_CAPACITY
    )

    assert (
        min_free_after_payload_commit
        >= EBD_RESERVE_WORDS
    )

    assert released_entries > 0
    assert capacity_block_events > 0


def test_final_epoch_does_not_plan_future_boundary():
    planner = FakePlanner(
        nominal_epoch_instructions=1
    )

    entry = plan_next_capacity_safe_entry(
        planner,
        free_words=IMEM_WORD_CAPACITY,
        preseed_next_boundary=False,
    )

    assert entry is None
    assert planner.boundary_calls == 0


@pytest.mark.parametrize(
    "free_words",
    [
        -1,
        IMEM_WORD_CAPACITY + 1,
        True,
        1.5,
    ],
)
def test_invalid_free_word_count_is_rejected(
    free_words,
):
    planner = FakePlanner(
        nominal_epoch_instructions=500
    )

    with pytest.raises(ValueError):
        plan_next_capacity_safe_entry(
            planner,
            free_words=free_words,
            preseed_next_boundary=True,
        )
