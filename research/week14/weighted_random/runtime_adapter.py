from __future__ import annotations

from research.week13.pure_random.runtime_stream import (
    PureRandomRuntimeEntry,
)
from research.week14.weighted_random.static_generator import (
    WeightedRandomPlan,
)


class WeightedRandomRuntimeEntry(
    PureRandomRuntimeEntry
):
    """
    Thin M2 identity adapter over the frozen M1 runtime entry.

    All physical placement, expected executed offsets,
    hard-cap-prefix semantics, and bounded runtime behavior
    remain inherited from the frozen Week-13 implementation.
    """

    @property
    def stream_entry_key(
        self,
    ) -> tuple[str, int]:
        return (
            "M2",
            self.block_index,
        )


def build_weighted_runtime_entries(
    plan: WeightedRandomPlan,
) -> tuple[
    WeightedRandomRuntimeEntry,
    ...,
]:
    if not isinstance(
        plan,
        WeightedRandomPlan,
    ):
        raise TypeError(
            "plan must be WeightedRandomPlan"
        )

    result: list[
        WeightedRandomRuntimeEntry
    ] = []

    logical_word_start = 0

    for block in plan.blocks:
        entry = WeightedRandomRuntimeEntry(
            logical_word_start=(
                logical_word_start
            ),
            planned=block,
        )

        result.append(entry)

        logical_word_start = (
            entry.logical_word_end_exclusive
        )

    return tuple(result)
