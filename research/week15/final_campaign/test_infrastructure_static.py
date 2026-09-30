from __future__ import annotations

import hashlib
import json
from pathlib import Path
import py_compile

import pytest

from research.week15.final_campaign.runtime_config import (
    INFRA_CLOSURE_PATH,
    load_final_runtime_config,
)


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)

FINAL_ROOT = (
    REPO_ROOT
    / "research/week15/final_campaign"
)

PLAN = json.loads(
    (
        FINAL_ROOT
        / "IMPLEMENTATION_PLAN.json"
    ).read_text(
        encoding="utf-8"
    )
)


def sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def test_frozen_sources_still_match_plan():
    for method in (
        "M1",
        "M2",
        "M3",
    ):
        record = (
            PLAN["methods"]
            [method]["source"]
        )

        path = (
            REPO_ROOT
            / record["path"]
        )

        assert sha256(path) == (
            record["sha256"]
        )


@pytest.mark.parametrize(
    "method,seed",
    [
        ("M1", 16001),
        ("M2", 16002),
        ("M3", 16003),
    ],
)
def test_qualification_runtime_matrix(
    tmp_path,
    method,
    seed,
):
    cfg = load_final_runtime_config(
        method,
        {
            "W15_FINAL_SEED": str(seed),
            "W15_FINAL_BUDGET": "100000",
            "W15_FINAL_PHASE": (
                "qualification"
            ),
            "W15_FINAL_RESULT_DIR": str(
                tmp_path
            ),
        },
    )

    assert cfg.method == method
    assert cfg.root_seed == seed
    assert cfg.accepted_budget == 100000
    assert cfg.checkpoint_interval == 1000
    assert cfg.phase == "qualification"


@pytest.mark.parametrize(
    "method,seed",
    [
        ("M1", 16002),
        ("M2", 16003),
        ("M3", 16001),
    ],
)
def test_cross_method_qualification_seed_rejected(
    tmp_path,
    method,
    seed,
):
    with pytest.raises(
        ValueError,
        match="qualification seed",
    ):
        load_final_runtime_config(
            method,
            {
                "W15_FINAL_SEED": str(seed),
                "W15_FINAL_BUDGET": "100000",
                "W15_FINAL_PHASE": (
                    "qualification"
                ),
                "W15_FINAL_RESULT_DIR": str(
                    tmp_path
                ),
            },
        )


def test_wrong_budget_rejected(
    tmp_path,
):
    with pytest.raises(
        ValueError,
        match="100000",
    ):
        load_final_runtime_config(
            "M1",
            {
                "W15_FINAL_SEED": "16001",
                "W15_FINAL_BUDGET": "99999",
                "W15_FINAL_PHASE": (
                    "qualification"
                ),
                "W15_FINAL_RESULT_DIR": str(
                    tmp_path
                ),
            },
        )


def test_result_directory_inside_repo_rejected():
    with pytest.raises(
        ValueError,
        match="outside repository",
    ):
        load_final_runtime_config(
            "M1",
            {
                "W15_FINAL_SEED": "16001",
                "W15_FINAL_BUDGET": "100000",
                "W15_FINAL_PHASE": (
                    "qualification"
                ),
                "W15_FINAL_RESULT_DIR": str(
                    FINAL_ROOT
                ),
            },
        )


def test_final_seed_locked_until_infra_closure(
    tmp_path,
):
    if INFRA_CLOSURE_PATH.exists():
        return

    with pytest.raises(
        RuntimeError,
        match="missing authority",
    ):
        load_final_runtime_config(
            "M1",
            {
                "W15_FINAL_SEED": "1001",
                "W15_FINAL_BUDGET": "100000",
                "W15_FINAL_PHASE": "final",
                "W15_FINAL_RESULT_DIR": str(
                    tmp_path
                ),
            },
        )


def test_m3_diff_is_runtime_import_only():
    source = (
        REPO_ROOT
        / "research/week15/rtl/"
        "test_adaptive_reproducibility.py"
    ).read_text(
        encoding="utf-8"
    )

    expected = source.replace(
        (
            "from research.week15."
            "reproducibility.runtime_config "
            "import ("
        ),
        (
            "from research.week15."
            "final_campaign.runtime_config "
            "import ("
        ),
        1,
    )

    actual = (
        FINAL_ROOT
        / "test_m3_final.py"
    ).read_text(
        encoding="utf-8"
    )

    assert actual == expected


def test_m2_known_answer_symbols_removed():
    text = (
        FINAL_ROOT
        / "test_m2_final.py"
    ).read_text(
        encoding="utf-8"
    )

    for banned in (
        "EXPECTED_PLAN_HASH",
        "EXPECTED_BLOCK_COUNT",
        "EXPECTED_IMAGE_WORDS",
        "EXPECTED_LAST_GENERATION",
        "EXPECTED_ARMS",
    ):
        assert banned not in text

    assert (
        '"VALID_DUT_FAILURE_NONTERMINAL"'
        in text
    )

    assert (
        "RESULT_PATH.write_text("
        in text
    )


def test_all_final_harnesses_compile():
    for name in (
        "runtime_config.py",
        "test_m1_final.py",
        "test_m2_final.py",
        "test_m3_final.py",
    ):
        py_compile.compile(
            str(FINAL_ROOT / name),
            doraise=True,
        )


def test_final_harness_repo_root_relocation_contract():
    import ast

    def find_repo_root(path):
        text = path.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(text)

        nodes = []

        for node in tree.body:
            if not isinstance(
                node,
                (
                    ast.Assign,
                    ast.AnnAssign,
                ),
            ):
                continue

            targets = (
                node.targets
                if isinstance(
                    node,
                    ast.Assign,
                )
                else [node.target]
            )

            if any(
                isinstance(
                    target,
                    ast.Name,
                )
                and target.id == "REPO_ROOT"
                for target in targets
            ):
                nodes.append(node)

        return text, nodes

    m1_text, m1_nodes = find_repo_root(
        FINAL_ROOT
        / "test_m1_final.py"
    )

    m2_text, m2_nodes = find_repo_root(
        FINAL_ROOT
        / "test_m2_final.py"
    )

    m3_text, m3_nodes = find_repo_root(
        FINAL_ROOT
        / "test_m3_final.py"
    )

    assert len(m1_nodes) == 1

    m1_segment = ast.get_source_segment(
        m1_text,
        m1_nodes[0],
    )

    assert m1_segment is not None
    assert ".parents[3]" in m1_segment
    assert ".parents[4]" not in m1_segment

    # M2 does not own Git provenance and
    # intentionally has no REPO_ROOT.
    assert len(m2_nodes) == 0
    assert "def git_text(" not in m2_text
    assert (
        "validate_pilot_provenance"
        not in m2_text
    )

    assert len(m3_nodes) == 1

    m3_segment = ast.get_source_segment(
        m3_text,
        m3_nodes[0],
    )

    assert m3_segment is not None
    assert ".parents[3]" in m3_segment
    assert ".parents[4]" not in m3_segment
