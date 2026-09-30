from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)

ROOT = (
    REPO_ROOT
    / "research/week15/final_campaign"
)

LAUNCH = json.loads(
    (
        ROOT
        / "QUALIFICATION_LAUNCH_CONTRACT.json"
    ).read_text(
        encoding="utf-8"
    )
)


def test_matrix_exact():
    assert [
        (
            x["method"],
            x["seed"],
            x["accepted_budget"],
        )
        for x in LAUNCH["matrix"]
    ] == [
        ("M1", 16001, 100000),
        ("M2", 16002, 100000),
        ("M3", 16003, 100000),
    ]


def test_no_final_seed_in_matrix():
    final = (
        set(range(1001, 1016))
        | set(range(2001, 2016))
        | set(range(3001, 3016))
    )

    assert not (
        {
            x["seed"]
            for x in LAUNCH["matrix"]
        }
        & final
    )


def test_module_variable_is_legacy_module():
    assert (
        LAUNCH[
            "make_contract"
        ][
            "test_module_variable"
        ]
        == "MODULE"
    )


def test_all_modules_are_final_campaign_modules():
    for entry in LAUNCH["matrix"]:
        assert entry["module"].startswith(
            "research.week15."
            "final_campaign."
        )


def test_runner_imports():
    path = (
        ROOT
        / "run_infra_qualification.py"
    )

    spec = (
        importlib.util
        .spec_from_file_location(
            "week15_infra_runner",
            path,
        )
    )

    assert spec is not None
    assert spec.loader is not None

    module = (
        importlib.util
        .module_from_spec(spec)
    )

    spec.loader.exec_module(
        module
    )


def test_gate_does_not_use_performance_or_coverage_level():
    acceptance = LAUNCH[
        "acceptance"
    ]

    assert (
        acceptance[
            "performance_level_is_gate"
        ]
        is False
    )

    assert (
        acceptance[
            "coverage_level_is_gate"
        ]
        is False
    )

    assert (
        acceptance[
            "results_may_drive_tuning"
        ]
        is False
    )


def test_validate_result_accepts_m1_in_flight_at_cut():
    import json
    from pathlib import Path

    from research.week15.final_campaign.run_infra_qualification import (
        validate_result,
    )

    root = Path(__file__).resolve().parent

    path = (
        root
        / "qualification"
        / "attempt_002_result_schema_adapter_failure"
        / "m1_seed_16001_n_100000"
        / "m1_qualification_seed_16001_n_100000.json"
    )

    result = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    normalized = validate_result(
        result,
        method="M1",
        seed=16001,
        accepted_budget=100000,
    )

    assert normalized == {
        "accepted": 100000,
        "retired_checked": 99999,
        "in_flight": 1,
        "in_flight_source_field": (
            "in_flight_at_cut"
        ),
    }


def test_validate_result_accepts_canonical_in_flight():
    from research.week15.final_campaign.run_infra_qualification import (
        validate_result,
    )

    result = {
        "seed": 16002,
        "accepted_budget": 100000,
        "status": "COMPLETED",
        "post_cut_clock_edges": 0,
        "lifecycle": {
            "accepted": 100000,
            "retired_checked": 99997,
            "in_flight": 3,
        },
    }

    normalized = validate_result(
        result,
        method="M2",
        seed=16002,
        accepted_budget=100000,
    )

    assert normalized == {
        "accepted": 100000,
        "retired_checked": 99997,
        "in_flight": 3,
        "in_flight_source_field": (
            "in_flight"
        ),
    }


def test_validate_result_rejects_conflicting_dual_fields():
    import pytest

    from research.week15.final_campaign.run_infra_qualification import (
        validate_result,
    )

    result = {
        "seed": 16003,
        "accepted_budget": 100000,
        "status": "COMPLETED",
        "post_cut_clock_edges": 0,
        "lifecycle": {
            "accepted": 100000,
            "retired_checked": 99999,
            "in_flight": 1,
            "in_flight_at_cut": 2,
        },
    }

    with pytest.raises(
        RuntimeError,
        match="conflicting in-flight",
    ):
        validate_result(
            result,
            method="M3",
            seed=16003,
            accepted_budget=100000,
        )


def test_runner_preserves_validation_failure_as_infra_invalid():
    from pathlib import Path

    path = (
        Path(__file__).resolve().parent
        / "run_infra_qualification.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    assert (
        '"validation_error_type"'
        in text
    )

    assert (
        '"validation_error"'
        in text
    )

    assert (
        '"classification": ('
        in text
    )

    assert (
        '"INFRA_INVALID"'
        in text
    )
