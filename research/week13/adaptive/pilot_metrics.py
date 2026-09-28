from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from research.week13.adaptive.pilot_contract import (
    ACCEPTED_BUDGET,
    CHECKPOINT_INTERVAL,
    L2_BIN_COUNT,
)


@dataclass(
    frozen=True,
    slots=True,
)
class L2IntentCheckpoint:
    accepted: int
    l2_intent_bins: int


def normalized_l2_intent_auc(
    checkpoints: Iterable[
        L2IntentCheckpoint
    ],
    *,
    n_max: int = ACCEPTED_BUDGET,
    checkpoint_interval: int = (
        CHECKPOINT_INTERVAL
    ),
    l2_bin_count: int = L2_BIN_COUNT,
) -> float:
    """
    Frozen Week-5 / Week-13 pilot metric.

    C(N) =
        covered L2 Intent bins at N
        / l2_bin_count

    AUC_norm =
        (1 / N_max) *
        integral_0^Nmax C(N) dN

    Numerical integration:
        trapezoidal rule at frozen checkpoints.

    Campaign origin:
        C(0) = 0 because no accepted instruction,
        and therefore no accepted-consumer Intent hit,
        exists before execution begins.

    Time:
        O(K), where K = number of checkpoints.

    Additional memory:
        O(K). For the frozen 10k/1k pilot,
        K = 10 and is therefore constant.
    """
    if (
        isinstance(n_max, bool)
        or not isinstance(n_max, int)
        or n_max <= 0
    ):
        raise ValueError(
            "n_max must be a positive integer"
        )

    if (
        isinstance(checkpoint_interval, bool)
        or not isinstance(
            checkpoint_interval,
            int,
        )
        or checkpoint_interval <= 0
    ):
        raise ValueError(
            "checkpoint_interval must be "
            "a positive integer"
        )

    if n_max % checkpoint_interval != 0:
        raise ValueError(
            "n_max must be divisible by "
            "checkpoint_interval"
        )

    if (
        isinstance(l2_bin_count, bool)
        or not isinstance(l2_bin_count, int)
        or l2_bin_count <= 0
    ):
        raise ValueError(
            "l2_bin_count must be "
            "a positive integer"
        )

    points = tuple(checkpoints)

    expected_accepts = tuple(
        range(
            checkpoint_interval,
            n_max + 1,
            checkpoint_interval,
        )
    )

    if len(points) != len(
        expected_accepts
    ):
        raise ValueError(
            "checkpoint count does not match "
            "the frozen integration grid"
        )

    previous_bins = 0

    for point, expected_accepted in zip(
        points,
        expected_accepts,
        strict=True,
    ):
        if not isinstance(
            point,
            L2IntentCheckpoint,
        ):
            raise TypeError(
                "checkpoints must contain "
                "L2IntentCheckpoint"
            )

        if (
            point.accepted
            != expected_accepted
        ):
            raise ValueError(
                "checkpoint boundary mismatch: "
                f"expected={expected_accepted}, "
                f"observed={point.accepted}"
            )

        if not (
            0
            <= point.l2_intent_bins
            <= l2_bin_count
        ):
            raise ValueError(
                "L2 Intent count outside "
                "coverage universe"
            )

        if (
            point.l2_intent_bins
            < previous_bins
        ):
            raise ValueError(
                "L2 Intent coverage must be "
                "monotonic"
            )

        previous_bins = (
            point.l2_intent_bins
        )

    previous_n = 0
    previous_c = 0.0

    area = 0.0

    for point in points:
        current_n = point.accepted
        current_c = (
            point.l2_intent_bins
            / l2_bin_count
        )

        width = current_n - previous_n

        area += (
            width
            * (previous_c + current_c)
            / 2.0
        )

        previous_n = current_n
        previous_c = current_c

    auc = area / n_max

    if not 0.0 <= auc <= 1.0:
        raise AssertionError(
            "normalized AUC escaped [0,1]"
        )

    return auc
