from research.week13.adaptive.pilot_contract import (
    ALPHA_CANDIDATES,
    BATCH_CANDIDATES,
    EPSILON_CANDIDATES,
    Q_FLOOR,
)
from research.week13.adaptive.selected_config import (
    PILOT_CONFIGURATION_COUNT,
    PILOT_RUN_COUNT,
    PILOT_SEEDS,
    SELECTED_ALPHA,
    SELECTED_EPSILON,
    SELECTED_NOMINAL_BATCH,
    SELECTED_Q_FLOOR,
)


def test_selected_config_belongs_to_frozen_grid():
    assert (
        SELECTED_EPSILON
        in EPSILON_CANDIDATES
    )

    assert (
        SELECTED_ALPHA
        in ALPHA_CANDIDATES
    )

    assert (
        SELECTED_NOMINAL_BATCH
        in BATCH_CANDIDATES
    )

    assert SELECTED_Q_FLOOR == Q_FLOOR


def test_selection_evidence_cardinality():
    assert PILOT_RUN_COUNT == 81
    assert PILOT_CONFIGURATION_COUNT == 27

    assert PILOT_SEEDS == (
        13001,
        13002,
        13003,
    )
