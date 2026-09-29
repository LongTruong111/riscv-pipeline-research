from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

CONFIG = (
    ROOT
    / "research/week14/configs/"
    "m1_pure_random.yaml"
)

HASH_FILE = (
    ROOT
    / "research/week14/configs/"
    "m1_pure_random.sha256"
)


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
    ).strip()


def load() -> dict:
    # File uses JSON syntax, which is valid YAML 1.2.
    return json.loads(
        CONFIG.read_text(encoding="utf-8")
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


def test_identity_and_feedback_contract():
    d = load()

    assert d["method"]["id"] == "M1-PR"

    feedback = d["feedback"]

    assert all(
        value is False
        for value in feedback.values()
    )


def test_uniform_family_contract():
    d = load()

    policy = d[
        "payload_family_policy"
    ]

    assert policy["type"] == (
        "STATIC_UNIFORM"
    )

    assert policy[
        "ordered_families"
    ] == [
        "ADD",
        "ADDI",
        "LW",
        "SW",
        "BRANCH",
        "JAL",
        "JALR",
        "LUI",
        "AUIPC",
    ]

    assert policy[
        "probability_each"
    ] == {
        "numerator": 1,
        "denominator": 9,
    }


def test_branch_uniformity_contract():
    d = load()

    branch = d[
        "branch_subtype_policy"
    ]

    assert branch[
        "ordered_subtypes"
    ] == [
        "BEQ",
        "BNE",
        "BLT",
        "BGE",
        "BLTU",
        "BGEU",
    ]

    assert branch[
        "probability_each_given_branch"
    ] == {
        "numerator": 1,
        "denominator": 6,
    }


def test_register_and_x0_contract():
    d = load()

    regs = d["register_domain"]

    assert regs[
        "positive_gpr_write_rd"
    ]["min"] == 1

    assert regs[
        "positive_gpr_write_rd"
    ]["max"] == 31

    assert regs[
        "unconstrained_rs1"
    ]["min"] == 0

    assert regs[
        "unconstrained_rs1"
    ]["max"] == 31

    assert regs[
        "unconstrained_rs2"
    ]["min"] == 0

    assert regs[
        "unconstrained_rs2"
    ]["max"] == 31

    containment = d[
        "known_defect_containment"
    ]

    assert containment[
        "positive_campaign_excludes_rd_x0"
    ] is True

    assert containment[
        "checker_x0_invariant_remains_enabled"
    ] is True

    assert containment[
        "directed_x0_obligations_are_separate"
    ] == ["H18", "H19"]


def test_final_budget_and_seed_namespace():
    d = load()

    campaign = d["campaign"]

    assert campaign[
        "accepted_budget_per_seed"
    ] == 100000

    assert campaign[
        "checkpoint_interval"
    ] == 1000

    assert campaign[
        "exact_accepted_cut"
    ] is True

    assert campaign[
        "final_seeds"
    ] == list(range(1001, 1016))

    assert campaign[
        "seed_count"
    ] == 15

    assert d[
        "week14_execution_policy"
    ][
        "final_100k_x_15_campaign_allowed"
    ] is False


def test_gate_t13_provenance_is_content_addressed():
    d = load()

    authority = d["authority"]

    assert authority[
        "gate_t13_commit"
    ] == git(
        "rev-parse",
        "GATE_T13_COMPLETE^{commit}",
    )

    assert authority[
        "design_tree_sha"
    ] == git(
        "rev-parse",
        (
            "GATE_T13_COMPLETE^{commit}:"
            "design"
        ),
    )

    assert authority[
        "protocol_tree_sha"
    ] == git(
        "rev-parse",
        (
            "GATE_T13_COMPLETE^{commit}:"
            "research/week13/protocol"
        ),
    )

    assert authority[
        "pure_random_tree_sha"
    ] == git(
        "rev-parse",
        (
            "GATE_T13_COMPLETE^{commit}:"
            "research/week13/pure_random"
        ),
    )


def test_raw_byte_hash_ledger():
    expected_hash, expected_name = (
        HASH_FILE.read_text(
            encoding="utf-8"
        )
        .strip()
        .split(maxsplit=1)
    )

    assert expected_name == (
        "research/week14/configs/"
        "m1_pure_random.yaml"
    )

    assert sha256(CONFIG) == expected_hash
