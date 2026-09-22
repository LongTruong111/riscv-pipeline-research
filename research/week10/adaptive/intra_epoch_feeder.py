from __future__ import annotations

from typing import Protocol

from research.week10.adaptive.campaign_runner import (
    IMEM_WORD_CAPACITY,
    MAX_STREAM_BLOCK_WORDS,
)


EBD_RESERVE_WORDS = 1


class CapacityEntry(Protocol):
    """
    Minimal stream-entry surface required by capacity planning.
    """

    @property
    def image_word_count(self) -> int:
        ...


class CapacityAwarePlanner(Protocol):
    """
    Minimal AdaptiveEpochStreamPlanner surface required by the
    intra-epoch capacity feeder.

    AdaptiveEpochStreamPlanner satisfies this protocol directly.
    """

    @property
    def active(self) -> bool:
        ...

    @property
    def epoch_plan_complete(self) -> bool:
        ...

    @property
    def pending_boundary_delimiter(
        self,
    ) -> CapacityEntry | None:
        ...

    def build_next_block(
        self,
    ) -> CapacityEntry:
        ...

    def plan_next_boundary_delimiter(
        self,
    ) -> CapacityEntry:
        ...


def refill_threshold_words(
    *,
    preseed_next_boundary: bool,
) -> int:
    """
    Conservative number of free IMEM words required before planning
    another payload block.

    Payload generation cannot be rolled back after build_next_block(),
    therefore capacity must be proven before that mutating call.

    If another epoch follows, reserve exactly one physical word for its
    EBD.  A complete payload block can occupy at most
    MAX_STREAM_BLOCK_WORDS.
    """
    if not isinstance(
        preseed_next_boundary,
        bool,
    ):
        raise TypeError(
            "preseed_next_boundary must be bool"
        )

    return (
        MAX_STREAM_BLOCK_WORDS
        + (
            EBD_RESERVE_WORDS
            if preseed_next_boundary
            else 0
        )
    )


def plan_next_capacity_safe_entry(
    planner: CapacityAwarePlanner,
    *,
    free_words: int,
    preseed_next_boundary: bool,
) -> CapacityEntry | None:
    """
    Plan at most one new stream entry without exceeding bounded IMEM.

    Return:
      * one complete payload block while the epoch payload is incomplete;
      * the next EBD after the complete-template nominal target has been
        reached, when preseed_next_boundary=True;
      * None when current physical capacity cannot safely admit another
        entry or when nothing remains to plan.

    Important:
      build_next_block() mutates logical/executed planner state.
      Consequently this function performs a conservative capacity check
      before calling it.  No rollback is required.

    Complexity:
      O(1) time and O(1) memory per admission decision with respect to
      campaign instruction count N.
    """
    if (
        isinstance(free_words, bool)
        or not isinstance(free_words, int)
        or not 0 <= free_words <= IMEM_WORD_CAPACITY
    ):
        raise ValueError(
            "free_words must be an integer in "
            f"[0, {IMEM_WORD_CAPACITY}]"
        )

    if not isinstance(
        preseed_next_boundary,
        bool,
    ):
        raise TypeError(
            "preseed_next_boundary must be bool"
        )

    if not planner.active:
        raise RuntimeError(
            "capacity feeder requires an active "
            "planning epoch"
        )

    # ----------------------------------------------------------
    # Payload is complete.
    #
    # The only legal next planned entry is EBD_(t+1), and only
    # when another adaptive epoch exists.
    # ----------------------------------------------------------
    if planner.epoch_plan_complete:
        if not preseed_next_boundary:
            return None

        if (
            planner.pending_boundary_delimiter
            is not None
        ):
            return None

        if free_words < EBD_RESERVE_WORDS:
            return None

        delimiter = (
            planner.plan_next_boundary_delimiter()
        )

        if (
            delimiter.image_word_count
            != EBD_RESERVE_WORDS
        ):
            raise AssertionError(
                "epoch boundary delimiter must occupy "
                "exactly one IMEM word"
            )

        if delimiter.image_word_count > free_words:
            raise AssertionError(
                "planned boundary delimiter exceeds "
                "available IMEM capacity"
            )

        return delimiter

    # ----------------------------------------------------------
    # Payload remains incomplete.
    #
    # Do not mutate planner state unless the maximum possible
    # complete block is guaranteed to fit.
    # ----------------------------------------------------------
    required_free_words = refill_threshold_words(
        preseed_next_boundary=(
            preseed_next_boundary
        )
    )

    if free_words < required_free_words:
        return None

    block = planner.build_next_block()

    if (
        block.image_word_count
        > MAX_STREAM_BLOCK_WORDS
    ):
        raise AssertionError(
            "planned payload block exceeds frozen "
            "maximum stream-block size"
        )

    boundary_reserve = (
        EBD_RESERVE_WORDS
        if preseed_next_boundary
        else 0
    )

    usable_payload_words = (
        free_words
        - boundary_reserve
    )

    if (
        block.image_word_count
        > usable_payload_words
    ):
        raise AssertionError(
            "payload block violated pre-admission "
            "capacity guarantee"
        )

    return block
