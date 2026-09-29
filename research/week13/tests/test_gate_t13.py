import json
from pathlib import Path

from research.week13.adaptive.selected_config import (
    PILOT_HARNESS_REVISION,
    SELECTED_ALPHA,
    SELECTED_EPSILON,
    SELECTED_NOMINAL_BATCH,
    SELECTED_Q_FLOOR,
)


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

GATE = json.loads(
    (ROOT / "gate_t13.json")
    .read_text(
        encoding="utf-8"
    )
)


def test_gate_t13_passes():
    assert GATE["schema_version"] == (
        "week13.gate-t13.v1"
    )

    assert GATE["gate"] == "T13"
    assert GATE["status"] == "PASS"

    assert (
        GATE["evidence_head_revision"]
        == "4d5aa07cc4db770485f02f66d2cce7b81ddbf102"
    )


def test_adaptive_selection_is_frozen():
    selected = GATE[
        "adaptive_selection"
    ]

    assert selected["status"] == "PASS"

    assert (
        selected["epsilon"]
        == SELECTED_EPSILON
    )

    assert (
        selected["alpha"]
        == SELECTED_ALPHA
    )

    assert (
        selected["q_floor"]
        == SELECTED_Q_FLOOR
    )

    assert (
        selected["nominal_batch"]
        == SELECTED_NOMINAL_BATCH
    )

    assert (
        selected["pilot_harness_revision"]
        == PILOT_HARNESS_REVISION
    )

    assert selected["pilot_runs"] == 81
    assert (
        selected["pilot_configurations"]
        == 27
    )


def test_gate_has_full_system_benchmark():
    benchmark = GATE[
        "full_system_benchmark"
    ]

    assert benchmark["status"] == "PASS"

    for method in (
        "m1_pure_random",
        "m3_adaptive_selected",
    ):
        data = benchmark[method]

        assert data["pilot_runs"] == 3
        assert (
            data["accepted_per_run"]
            == 10_000
        )

        assert data[
            "median_wall_ns"
        ] > 0

        assert data[
            "median_accepted_per_s"
        ] > 0

        assert data[
            "median_cycles_per_s"
        ] > 0

        assert data[
            "median_peak_rss_kib"
        ] > 0


def test_gate_has_reachability_witness():
    reach = GATE[
        "coverage_reachability"
    ]

    assert reach["status"] == "PASS"
    assert reach["l2_bin_count"] == 62

    assert 11002 in (
        reach[
            "full_l2_intent_witness_seeds"
        ]
    )


def test_gate_mutations_pass():
    mutation = GATE["mutation"]

    assert mutation["status"] == "PASS"

    m1 = mutation["MUT-M1"]

    assert m1["status"] == "PASS"
    assert (
        m1["target_activation_count"]
        == 12
    )
    assert (
        m1["checker_failure_count"]
        == 12
    )
    assert (
        m1["first_failure_instruction"]
        == 5
    )

    m2 = mutation["MUT-M2-x0"]

    assert m2["status"] == "PASS"

    assert (
        m2[
            "canonical_target_activation_count"
        ]
        == 1
    )

    assert (
        m2[
            "canonical_checker_failure_count"
        ]
        == 0
    )

    assert (
        m2["canonical_forward_a"]
        == 0
    )

    assert (
        m2[
            "mutant_target_activation_count"
        ]
        == 1
    )

    assert (
        m2[
            "mutant_checker_failure_count"
        ]
        == 1
    )

    assert (
        m2["mutant_forward_a"]
        == 2
    )
