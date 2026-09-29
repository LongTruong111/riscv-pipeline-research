from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

AUDIT_PATH = (
    ROOT
    / "research/week14/preflight/"
    "directed_static_audit.json"
)

PREREG_PATH = (
    ROOT
    / "research/week14/preflight/"
    "directed_expected_rejections.json"
)

TREE_PATH = (
    ROOT
    / "research/week14/preflight/"
    "protected_tree_sha.json"
)


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
    ).strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(65536),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def sign_extend_12(value: int) -> int:
    value &= 0xFFF
    if value & 0x800:
        value -= 0x1000
    return value


def test_gate_t13_tag_peels_to_preregistered_base():
    prereg = load_json(PREREG_PATH)

    peeled = git(
        "rev-parse",
        "GATE_T13_COMPLETE^{commit}",
    )

    assert peeled == prereg["gate_t13_commit"]


def test_protected_committed_trees_match_gate_t13():
    provenance = load_json(TREE_PATH)

    base = provenance["gate_t13_commit"]

    for path, entry in (
        provenance["protected_paths"].items()
    ):
        expected = entry["base_tree"]

        assert (
            git(
                "rev-parse",
                f"{base}:{path}",
            )
            == expected
        )

        assert (
            git(
                "rev-parse",
                f"HEAD:{path}",
            )
            == expected
        )


def test_protected_paths_have_no_worktree_delta():
    provenance = load_json(TREE_PATH)

    for path in provenance["protected_paths"]:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--quiet",
                "HEAD",
                "--",
                path,
            ],
            cwd=ROOT,
            check=False,
        )

        assert result.returncode == 0, (
            f"protected path has working-tree "
            f"delta: {path}"
        )


def test_directed_fixture_bijection_and_hashes():
    audit = load_json(AUDIT_PATH)

    assert audit["case_count"] == 20
    assert audit["target_bijection"] is True

    test_ids = {
        row["test_id"]
        for row in audit["cases"]
    }

    bins = {
        row["target_bin"]
        for row in audit["cases"]
    }

    assert test_ids == {
        f"T{i:02d}"
        for i in range(1, 21)
    }

    assert bins == {
        f"H{i:02d}"
        for i in range(1, 21)
    }

    for row in audit["cases"]:
        fixture = ROOT / row["fixture_path"]

        assert fixture.is_file()

        assert (
            sha256_file(fixture)
            == row["fixture_sha256"]
        )


def test_preregistered_rejection_set_is_exactly_t18():
    prereg = load_json(PREREG_PATH)

    expected = prereg[
        "expected_rejection_test_ids"
    ]

    assert expected == ["T18"]
    assert prereg[
        "expected_rejection_count"
    ] == 1

    required_pass = set(
        prereg["required_non_rejected_cases"]
    )

    assert required_pass == {
        f"T{i:02d}"
        for i in range(1, 21)
        if i != 18
    }


def test_t18_nonzero_x0_activation_is_static():
    audit = load_json(AUDIT_PATH)

    cases = {
        row["test_id"]: row
        for row in audit["cases"]
    }

    item = cases["T18"]["instructions"][0]
    word = int(item["word"], 16)

    opcode = word & 0x7F
    funct3 = (word >> 12) & 0x7
    rd = (word >> 7) & 0x1F
    rs1 = (word >> 15) & 0x1F
    imm = sign_extend_12(
        word >> 20
    )

    assert opcode == 0x13
    assert funct3 == 0
    assert rd == 0
    assert rs1 == 1
    assert imm == 7

    initial_x1 = 0

    architectural_result = (
        initial_x1 + imm
    ) & 0xFFFFFFFF

    assert architectural_result == 7


def test_t19_x0_write_is_zero_under_frozen_initial_state():
    audit = load_json(AUDIT_PATH)

    cases = {
        row["test_id"]: row
        for row in audit["cases"]
    }

    item = cases["T19"]["instructions"][0]
    word = int(item["word"], 16)

    opcode = word & 0x7F
    funct3 = (word >> 12) & 0x7
    rd = (word >> 7) & 0x1F
    rs1 = (word >> 15) & 0x1F
    imm = sign_extend_12(
        word >> 20
    )

    assert opcode == 0x03
    assert funct3 == 0x2
    assert rd == 0
    assert rs1 == 1
    assert imm == 0

    # Frozen isolated-run initial state.
    initial_x1 = 0
    dmem_word_at_zero = 0

    effective_address = (
        initial_x1 + imm
    ) & 0xFFFFFFFF

    assert effective_address == 0
    assert dmem_word_at_zero == 0


def test_canonical_directed_suite_does_not_activate_jalr_defect():
    audit = load_json(AUDIT_PATH)

    jalr = {
        row["test_id"]:
            row["jalr_instruction_indices"]
        for row in audit["cases"]
        if row["jalr_instruction_indices"]
    }

    assert jalr == {}

    t15 = next(
        row
        for row in audit["cases"]
        if row["test_id"] == "T15"
    )

    first_word = int(
        t15["instructions"][0]["word"],
        16,
    )

    assert (first_word & 0x7F) == 0x6F
