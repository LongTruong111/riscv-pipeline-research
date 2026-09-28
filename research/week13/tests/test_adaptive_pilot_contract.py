import pytest

from research.week13.adaptive.pilot_contract import (
    ACCEPTED_BUDGET,
    ALPHA_CANDIDATES,
    BATCH_CANDIDATES,
    CHECKPOINT_INTERVAL,
    EPSILON_CANDIDATES,
    PILOT_SEEDS,
    hyperparameter_configs,
    pilot_runs,
)
from research.week13.adaptive.pilot_metrics import (
    L2IntentCheckpoint,
    normalized_l2_intent_auc,
)


def test_full_grid_is_exactly_27_configs():
    configs = hyperparameter_configs()

    assert len(configs) == 27
    assert len(set(configs)) == 27

    assert {
        config.epsilon
        for config in configs
    } == set(EPSILON_CANDIDATES)

    assert {
        config.alpha
        for config in configs
    } == set(ALPHA_CANDIDATES)

    assert {
        config.nominal_batch
        for config in configs
    } == set(BATCH_CANDIDATES)


def test_full_pilot_is_exactly_81_runs():
    runs = pilot_runs()

    assert len(runs) == 81
    assert len(set(runs)) == 81

    assert {
        run.seed
        for run in runs
    } == set(PILOT_SEEDS)

    assert (
        len(runs)
        * ACCEPTED_BUDGET
        == 810_000
    )


def make_points(counts):
    return tuple(
        L2IntentCheckpoint(
            accepted=accepted,
            l2_intent_bins=count,
        )
        for accepted, count in zip(
            range(
                CHECKPOINT_INTERVAL,
                ACCEPTED_BUDGET + 1,
                CHECKPOINT_INTERVAL,
            ),
            counts,
            strict=True,
        )
    )


def test_auc_zero_coverage_is_zero():
    points = make_points(
        [0] * 10
    )

    assert (
        normalized_l2_intent_auc(
            points
        )
        == 0.0
    )


def test_auc_full_from_first_checkpoint():
    points = make_points(
        [62] * 10
    )

    # Trapezoid from C(0)=0 to
    # C(1000)=1 contributes 500.
    # Remaining nine intervals contribute
    # 9000, therefore:
    #
    # 9500 / 10000 = 0.95
    assert (
        normalized_l2_intent_auc(
            points
        )
        == pytest.approx(0.95)
    )


def test_auc_matches_raw_trapezoid():
    counts = [
        6,
        12,
        18,
        24,
        31,
        37,
        43,
        49,
        55,
        62,
    ]

    points = make_points(counts)

    raw_counts = [0, *counts]

    raw_area = sum(
        CHECKPOINT_INTERVAL
        * (left + right)
        / 2.0
        for left, right in zip(
            raw_counts[:-1],
            raw_counts[1:],
            strict=True,
        )
    )

    expected = (
        raw_area
        / (
            62
            * ACCEPTED_BUDGET
        )
    )

    assert (
        normalized_l2_intent_auc(
            points
        )
        == pytest.approx(expected)
    )


def test_auc_rejects_missing_checkpoint():
    points = make_points(
        [0] * 10
    )[:-1]

    with pytest.raises(
        ValueError,
        match="checkpoint count",
    ):
        normalized_l2_intent_auc(
            points
        )


def test_auc_rejects_nonmonotonic_coverage():
    points = make_points([
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        7,
        9,
    ])

    with pytest.raises(
        ValueError,
        match="monotonic",
    ):
        normalized_l2_intent_auc(
            points
        )
