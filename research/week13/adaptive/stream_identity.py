from __future__ import annotations

from dataclasses import dataclass

from research.week10.adaptive.campaign_runner import (
    AcceptedStreamTracker,
    RuntimeStreamWindow,
)


class AdaptiveStreamIdentityProtocolError(
    RuntimeError
):
    """
    Infrastructure/protocol failure while reading the
    frozen adaptive accepted-stream state.
    """


@dataclass(
    frozen=True,
    slots=True,
)
class ExpectedAdaptiveAcceptedIdentity:
    instruction_index: int
    pc: int
    instruction: int
    logical_word_index: int
    stream_entry_key: tuple[str, int]
    entry_progress: int


def peek_expected_accepted_identity(
    window: RuntimeStreamWindow,
) -> ExpectedAdaptiveAcceptedIdentity:
    """
    Read the next planned adaptive accepted instruction
    without mutating runtime/tracker state.

    This adapter deliberately isolates the only private-state
    dependency required by Week 13.

    Time:
        O(1)

    Additional memory:
        O(1)
    """
    if not isinstance(
        window,
        RuntimeStreamWindow,
    ):
        raise TypeError(
            "window must be RuntimeStreamWindow"
        )

    tracker = getattr(
        window,
        "_accepted_tracker",
        None,
    )

    if not isinstance(
        tracker,
        AcceptedStreamTracker,
    ):
        raise AdaptiveStreamIdentityProtocolError(
            "RuntimeStreamWindow no longer exposes "
            "the frozen AcceptedStreamTracker layout"
        )

    entry = tracker.current_block

    if entry is None:
        raise AdaptiveStreamIdentityProtocolError(
            "no pending adaptive stream entry "
            "for accepted-event prevalidation"
        )

    progress = tracker.current_block_progress

    count = (
        entry.expected_executed_instruction_count
    )

    if not 0 <= progress < count:
        raise AdaptiveStreamIdentityProtocolError(
            "accepted-stream progress is outside "
            "the current entry"
        )

    pcs = entry.expected_executed_pcs
    words = entry.expected_executed_words
    offsets = (
        entry.expected_executed_word_offsets
    )

    if not (
        len(pcs)
        == len(words)
        == len(offsets)
        == count
    ):
        raise AdaptiveStreamIdentityProtocolError(
            "adaptive stream entry exposes "
            "inconsistent expected-path lengths"
        )

    instruction_index = (
        tracker.next_expected_instruction_index
    )

    expected_from_entry = (
        entry.first_executed_instruction_index
        + progress
    )

    if (
        instruction_index
        != expected_from_entry
    ):
        raise AdaptiveStreamIdentityProtocolError(
            "tracker instruction index disagrees "
            "with current stream-entry progress"
        )

    logical_word_index = (
        entry.logical_word_start
        + offsets[progress]
    )

    return ExpectedAdaptiveAcceptedIdentity(
        instruction_index=instruction_index,
        pc=pcs[progress],
        instruction=words[progress],
        logical_word_index=(
            logical_word_index
        ),
        stream_entry_key=(
            entry.stream_entry_key
        ),
        entry_progress=progress,
    )
