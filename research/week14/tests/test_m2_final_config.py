from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

CONFIG = (
    ROOT
    / "research/week14/configs/"
    "m2_weighted_random.yaml"
)

HASH_FILE = (
    ROOT
    / "research/week14/configs/"
    "m2_weighted_random.sha256"
)

SMOKE = (
    ROOT
    / "research/week14/results/"
    "m2_static_smoke/"
    "weighted_plan_seed14001.json"
)


def load(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(65536),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def test_method_and_weights():
    d = load(CONFIG)

    assert d["method"]["id"] == "M2-WR"

    arm = d["arm_policy"]

    assert arm["denominator"] == 16

    assert arm[
        "ordered_ticket_table"
    ] == [
        "A0",
        "A0",
        "A1",
        "A1",
        "A2",
        "A2",
        "A3",
        "A3",
        "A4",
        "A5",
        "A5",
        "A6",
        "A6",
        "A7",
        "A8",
        "A9",
    ]

    assert sum(
        arm["weights"].values()
    ) == 16


def test_no_feedback_configuration():
    d = load(CONFIG)

    assert all(
        value is False
        for value
        in d["feedback"].values()
    )

    assert d[
        "target_policy"
    ]["uncovered_first"] is False

    assert d[
        "target_policy"
    ][
        "runtime_coverage_feedback"
    ] is False

    assert d[
        "implementation"
    ][
        "adaptive_register_policy_used"
    ] is False


def test_target_contract():
    d = load(CONFIG)

    target = d["target_policy"]

    assert target[
        "single_distance_probability"
    ] == {
        "numerator": 1,
        "denominator": 31,
    }

    assert target["A4"][
        "ordered_pair_distinct"
    ] is True

    assert target["A4"][
        "ordered_pair_probability"
    ] == {
        "numerator": 1,
        "denominator": 930,
    }


def test_final_budget_and_seed_namespace():
    d = load(CONFIG)

    campaign = d["campaign"]

    assert campaign[
        "accepted_budget_per_seed"
    ] == 100000

    assert campaign[
        "checkpoint_interval"
    ] == 1000

    assert campaign[
        "final_seeds"
    ] == list(
        range(2001, 2016)
    )

    assert campaign[
        "seed_count"
    ] == 15

    assert d[
        "week14_execution_policy"
    ][
        "final_100k_x_15_campaign_allowed"
    ] is False


def test_smoke_is_nonfinal_and_deterministic():
    config = load(CONFIG)
    smoke = load(SMOKE)

    assert smoke["seed"] == 14001
    assert smoke["accepted"] == 1000
    assert smoke["determinism"] is True
    assert smoke[
        "final_campaign_executed"
    ] is False

    assert config[
        "week14_smoke"
    ]["final_seed"] is False

    assert config[
        "authority"
    ][
        "smoke_witness_sha256"
    ] == sha256(SMOKE)


def test_raw_config_hash():
    expected_hash, expected_path = (
        HASH_FILE.read_text(
            encoding="utf-8"
        )
        .strip()
        .split(maxsplit=1)
    )

    assert expected_path == (
        "research/week14/configs/"
        "m2_weighted_random.yaml"
    )

    assert sha256(CONFIG) == expected_hash
