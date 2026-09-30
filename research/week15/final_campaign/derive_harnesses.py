from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)

FINAL_ROOT = (
    REPO_ROOT
    / "research/week15/final_campaign"
)

PLAN_PATH = (
    FINAL_ROOT
    / "IMPLEMENTATION_PLAN.json"
)

M1_SOURCE = (
    REPO_ROOT
    / "research/week13/pure_random/"
    "rtl/test_m1_pilot.py"
)

M2_SOURCE = (
    REPO_ROOT
    / "research/week14/weighted_random/"
    "rtl/test_m2_preflight_exact_cut.py"
)

M3_SOURCE = (
    REPO_ROOT
    / "research/week15/rtl/"
    "test_adaptive_reproducibility.py"
)

M1_OUT = (
    FINAL_ROOT
    / "test_m1_final.py"
)

M2_OUT = (
    FINAL_ROOT
    / "test_m2_final.py"
)

M3_OUT = (
    FINAL_ROOT
    / "test_m3_final.py"
)


def sha256_bytes(
    data: bytes,
) -> str:
    return hashlib.sha256(
        data
    ).hexdigest()


def sha256_file(
    path: Path,
) -> str:
    return sha256_bytes(
        path.read_bytes()
    )


def assignment_names(
    node: ast.AST,
) -> set[str]:
    names: set[str] = set()

    if isinstance(
        node,
        ast.Assign,
    ):
        targets = node.targets

    elif isinstance(
        node,
        ast.AnnAssign,
    ):
        targets = [node.target]

    else:
        return names

    for target in targets:
        if isinstance(
            target,
            ast.Name,
        ):
            names.add(
                target.id
            )

    return names


def apply_ranges(
    source: str,
    replacements: list[
        tuple[int, int, str]
    ],
) -> str:
    lines = source.splitlines(
        keepends=True
    )

    occupied: list[
        tuple[int, int]
    ] = []

    for start, end, _ in replacements:
        for other_start, other_end in occupied:
            if not (
                end < other_start
                or start > other_end
            ):
                raise AssertionError(
                    "overlapping source patch: "
                    f"{start}-{end} vs "
                    f"{other_start}-{other_end}"
                )

        occupied.append(
            (start, end)
        )

    for start, end, text in sorted(
        replacements,
        key=lambda item: item[0],
        reverse=True,
    ):
        replacement = text

        if (
            replacement
            and not replacement.endswith(
                "\n"
            )
        ):
            replacement += "\n"

        lines[
            start - 1:end
        ] = (
            replacement.splitlines(
                keepends=True
            )
        )

    return "".join(
        lines
    )


def top_assignment(
    tree: ast.Module,
    name: str,
) -> ast.AST:
    matches = [
        node
        for node in tree.body
        if name
        in assignment_names(node)
    ]

    if len(matches) != 1:
        raise AssertionError(
            f"expected one top assignment "
            f"for {name}, got {len(matches)}"
        )

    return matches[0]


def function_node(
    tree: ast.Module,
    name: str,
) -> ast.AST:
    matches = [
        node
        for node in tree.body
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name == name
    ]

    if len(matches) != 1:
        raise AssertionError(
            f"expected one function {name}, "
            f"got {len(matches)}"
        )

    return matches[0]


def nested_assignment(
    function: ast.AST,
    name: str,
) -> ast.AST:
    matches = [
        node
        for node in ast.walk(
            function
        )
        if name
        in assignment_names(node)
    ]

    if len(matches) != 1:
        raise AssertionError(
            f"expected one nested assignment "
            f"{name}, got {len(matches)}"
        )

    return matches[0]


def expected_source_sha(
    method: str,
) -> str:
    plan = json.loads(
        PLAN_PATH.read_text(
            encoding="utf-8"
        )
    )

    return plan[
        "methods"
    ][method][
        "source"
    ]["sha256"]


def verify_source(
    method: str,
    path: Path,
) -> None:
    actual = sha256_file(
        path
    )

    expected = expected_source_sha(
        method
    )

    if actual != expected:
        raise RuntimeError(
            f"{method} frozen source mismatch: "
            f"{actual} != {expected}"
        )


def derive_m1() -> str:
    verify_source(
        "M1",
        M1_SOURCE,
    )

    source = M1_SOURCE.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(
        source
    )

    repo_root = top_assignment(
        tree,
        "REPO_ROOT",
    )

    seed_start = top_assignment(
        tree,
        "PILOT_SEEDS",
    )

    checkpoint_end = top_assignment(
        tree,
        "CHECKPOINT_INTERVAL",
    )

    schema = top_assignment(
        tree,
        "PILOT_SCHEMA_VERSION",
    )

    provenance = function_node(
        tree,
        "validate_pilot_provenance",
    )

    test_function = function_node(
        tree,
        "test_m1_pilot_exact_cut_10000",
    )

    result_dir = nested_assignment(
        test_function,
        "result_dir",
    )

    result_path = nested_assignment(
        test_function,
        "result_path",
    )

    config_block = """\
from research.week15.final_campaign.runtime_config import (
    load_final_runtime_config,
)

FINAL_CONFIG = load_final_runtime_config(
    "M1"
)

PILOT_SEEDS = frozenset({
    FINAL_CONFIG.root_seed,
})

ROOT_SEED = FINAL_CONFIG.root_seed
ACCEPTED_BUDGET = FINAL_CONFIG.accepted_budget
CHECKPOINT_INTERVAL = FINAL_CONFIG.checkpoint_interval
"""

    provenance_block = """\
def validate_pilot_provenance() -> str:
    head = git_text(
        "rev-parse",
        "HEAD",
    )

    dirty = git_text(
        "status",
        "--porcelain",
    )

    if dirty:
        raise AssertionError(
            "official Week15 M1 final execution "
            "requires a clean git tree"
        )

    t15 = git_text(
        "rev-parse",
        "GATE_T15_COMPLETE^{commit}",
    )

    if t15 != FINAL_CONFIG.gate_t15_head:
        raise AssertionError(
            "GATE_T15_COMPLETE identity mismatch"
        )

    design_delta = git_text(
        "diff",
        f"{FINAL_CONFIG.gate_t15_head}..{head}",
        "--",
        "design",
    )

    if design_delta:
        raise AssertionError(
            "design/ changed after Gate T15"
        )

    return head
"""

    replacements = [
        (
            repo_root.lineno,
            repo_root.end_lineno,
            """REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)""",
        ),
        (
            schema.lineno,
            schema.end_lineno,
            (
                'PILOT_SCHEMA_VERSION = '
                '"w15.m1-final.telemetry.v1"'
            ),
        ),
        (
            provenance.lineno,
            provenance.end_lineno,
            provenance_block,
        ),
        (
            seed_start.lineno,
            checkpoint_end.end_lineno,
            config_block,
        ),
        (
            result_dir.lineno,
            result_dir.end_lineno,
            (
                "    result_dir = "
                "FINAL_CONFIG.result_dir"
            ),
        ),
        (
            result_path.lineno,
            result_path.end_lineno,
            (
                "    result_path = "
                "FINAL_CONFIG.result_path"
            ),
        ),
    ]

    derived = apply_ranges(
        source,
        replacements,
    )

    phase_count = derived.count(
        '"phase": "pilot"'
    )

    if phase_count == 0:
        raise AssertionError(
            "M1 pilot phase labels not found"
        )

    derived = derived.replace(
        '"phase": "pilot"',
        '"phase": FINAL_CONFIG.phase',
    )

    derived = derived.replace(
        "W13_M1_PILOT_RESULT",
        "W15_M1_FINAL_RESULT",
    )

    compile(
        derived,
        str(M1_OUT),
        "exec",
    )

    return derived


def remove_m2_expected_asserts(
    source: str,
) -> str:
    tree = ast.parse(
        source
    )

    banned = {
        "EXPECTED_PLAN_HASH",
        "EXPECTED_BLOCK_COUNT",
        "EXPECTED_IMAGE_WORDS",
        "EXPECTED_LAST_GENERATION",
        "EXPECTED_ARMS",
    }

    replacements: list[
        tuple[int, int, str]
    ] = []

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Assert,
        ):
            continue

        segment = ast.get_source_segment(
            source,
            node,
        )

        if segment is None:
            raise AssertionError(
                "cannot recover assert source"
            )

        if any(
            name in segment
            for name in banned
        ):
            replacements.append(
                (
                    node.lineno,
                    node.end_lineno,
                    "",
                )
            )

            continue

        compact = "".join(
            segment.split()
        )

        if (
            "functional.failed_count==0"
            in compact
            or
            "performance.failed_count==0"
            in compact
        ):
            replacements.append(
                (
                    node.lineno,
                    node.end_lineno,
                    "",
                )
            )

    return apply_ranges(
        source,
        replacements,
    )


def replace_m2_checkpoint_assert(
    source: str,
) -> str:
    tree = ast.parse(
        source
    )

    matches = []

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Assert,
        ):
            continue

        segment = ast.get_source_segment(
            source,
            node,
        )

        if (
            segment
            and
            "checkpoint.executed_instructions"
            in segment
        ):
            matches.append(
                node
            )

    if len(matches) != 1:
        raise AssertionError(
            "expected one M2 checkpoint-grid "
            f"assert, got {len(matches)}"
        )

    node = matches[0]

    replacement = """\
    assert [
        checkpoint.executed_instructions
        for checkpoint in checkpoints
    ] == list(
        range(
            CHECKPOINT_INTERVAL,
            ACCEPTED_BUDGET + 1,
            CHECKPOINT_INTERVAL,
        )
    )
"""

    return apply_ranges(
        source,
        [
            (
                node.lineno,
                node.end_lineno,
                replacement,
            )
        ],
    )


def remove_m2_boundary_special_case(
    source: str,
) -> str:
    lines = source.splitlines(
        keepends=True
    )

    starts = [
        i
        for i, line in enumerate(
            lines
        )
        if (
            "final_plan_block = ("
            in line
        )
    ]

    if len(starts) != 1:
        raise AssertionError(
            "expected one final_plan_block "
            f"assignment, got {len(starts)}"
        )

    start = starts[0]

    end = None

    for i in range(
        start + 1,
        len(lines),
    ):
        if lines[i].strip() == "break":
            end = i
            break

    if end is None:
        raise AssertionError(
            "M2 exact-cut break not found"
        )

    context = "".join(
        lines[start:end]
    )

    if (
        "pending_entry_count"
        not in context
        or
        "EXPECTED_IMAGE_WORDS"
        not in context
    ):
        raise AssertionError(
            "unexpected M2 special-case region"
        )

    del lines[
        start:end
    ]

    return "".join(
        lines
    )


def derive_m2() -> str:
    verify_source(
        "M2",
        M2_SOURCE,
    )

    source = M2_SOURCE.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(
        source
    )

    root = top_assignment(
        tree,
        "ROOT_SEED",
    )

    checkpoint = top_assignment(
        tree,
        "CHECKPOINT_INTERVAL",
    )

    config_block = """\
from research.week15.final_campaign.runtime_config import (
    load_final_runtime_config,
)

FINAL_CONFIG = load_final_runtime_config(
    "M2"
)

ROOT_SEED = FINAL_CONFIG.root_seed
ACCEPTED_BUDGET = FINAL_CONFIG.accepted_budget
CHECKPOINT_INTERVAL = FINAL_CONFIG.checkpoint_interval

RESULT_DIR = FINAL_CONFIG.result_dir
RESULT_PATH = FINAL_CONFIG.result_path
"""

    replacements = [
        (
            root.lineno,
            checkpoint.end_lineno,
            config_block,
        )
    ]

    for name in (
        "EXPECTED_PLAN_HASH",
        "EXPECTED_BLOCK_COUNT",
        "EXPECTED_IMAGE_WORDS",
        "EXPECTED_LAST_GENERATION",
        "EXPECTED_ARMS",
    ):
        node = top_assignment(
            tree,
            name,
        )

        replacements.append(
            (
                node.lineno,
                node.end_lineno,
                "",
            )
        )

    source = apply_ranges(
        source,
        replacements,
    )

    source = (
        remove_m2_boundary_special_case(
            source
        )
    )

    source = (
        remove_m2_expected_asserts(
            source
        )
    )

    source = (
        replace_m2_checkpoint_assert(
            source
        )
    )

    if source.count(
        "import time\n"
    ) != 1:
        raise AssertionError(
            "unexpected M2 import-time count"
        )

    source = source.replace(
        "import time\n",
        "import json\nimport time\n",
        1,
    )

    marker = (
        "    dut._log.info(\n"
        '        "W14_M2_PREFLIGHT=PASS "'
    )

    marker_index = source.find(
        marker
    )

    if marker_index < 0:
        raise AssertionError(
            "M2 final log marker not found"
        )

    result_block = """\
    run_status = (
        "VALID_DUT_FAILURE_NONTERMINAL"
        if (
            functional.failed_count > 0
            or performance.failed_count > 0
        )
        else "COMPLETED"
    )

    RESULT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if RESULT_PATH.exists():
        raise AssertionError(
            "refusing to overwrite existing "
            f"M2 final result: {RESULT_PATH}"
        )

    result_record = {
        "schema_version": (
            "w15.m2-final.telemetry.v1"
        ),
        "phase": FINAL_CONFIG.phase,
        "method": "M2",
        "seed": ROOT_SEED,
        "accepted_budget": ACCEPTED_BUDGET,
        "checkpoint_interval": (
            CHECKPOINT_INTERVAL
        ),
        "status": run_status,
        "post_cut_clock_edges": 0,
        "plan_hash": plan.plan_hash,
        "lifecycle": {
            "accepted": (
                final_snapshot.accepted
            ),
            "retired_checked": (
                final_snapshot
                .retired_checked
            ),
            "in_flight": in_flight,
            "functional_pending": (
                final_snapshot
                .functional_pending
            ),
            "performance_pending": (
                final_snapshot
                .performance_pending
            ),
        },
        "functional": {
            "checked": (
                functional.checked_count
            ),
            "passed": (
                functional.passed_count
            ),
            "failed": (
                functional.failed_count
            ),
            "first_failure": (
                first_functional_failure
            ),
            "diagnostics": (
                functional_failure_diagnostics
            ),
        },
        "performance": {
            "checked": (
                performance.checked_count
            ),
            "passed": (
                performance.passed_count
            ),
            "failed": (
                performance.failed_count
            ),
            "first_failure": (
                first_performance_failure
            ),
            "first_accept_divergence": (
                first_accept_timing_divergence
            ),
            "diagnostics": (
                performance_failure_diagnostics
            ),
        },
        "coverage": {
            "l1_intent": (
                final_checkpoint
                .l1_intent_count
            ),
            "l1_validated": (
                final_checkpoint
                .l1_validated_count
            ),
            "l2_intent": (
                final_checkpoint
                .l2_intent_count
            ),
            "l2_validated": (
                final_checkpoint
                .l2_validated_count
            ),
            "checkpoints": [
                {
                    "executed_instructions": (
                        checkpoint
                        .executed_instructions
                    ),
                    "cycle": checkpoint.cycle,
                    "l1_intent": (
                        checkpoint
                        .l1_intent_count
                    ),
                    "l1_validated": (
                        checkpoint
                        .l1_validated_count
                    ),
                    "l2_intent": (
                        checkpoint
                        .l2_intent_count
                    ),
                    "l2_validated": (
                        checkpoint
                        .l2_validated_count
                    ),
                }
                for checkpoint
                in checkpoints
            ],
        },
        "runtime": {
            "cycles": cycle,
            "stall_cycles": (
                stall_cycle_count
            ),
            "flush_cycles": (
                flush_cycle_count
            ),
            "released_entries": (
                released_entry_count
            ),
            "refill_pauses": (
                refill_pause_count
            ),
            "patched_words": (
                patched_word_count
            ),
            "patch_reuses": (
                patch_reuse_count
            ),
            "max_resident_words": (
                max_resident_words
            ),
            "wall_ns": elapsed_ns,
            "accepted_per_s": (
                accepted_per_second
            ),
        },
    }

    RESULT_PATH.write_text(
        json.dumps(
            result_record,
            indent=2,
            sort_keys=True,
        )
        + "\\n",
        encoding="utf-8",
    )

"""

    source = (
        source[:marker_index]
        + result_block
        + source[marker_index:]
    )

    source = source.replace(
        '"W14_M2_PREFLIGHT=PASS "',
        (
            '"W15_M2_FINAL_RESULT " '
            'f"status={run_status} "'
        ),
        1,
    )

    for banned in (
        "EXPECTED_PLAN_HASH",
        "EXPECTED_BLOCK_COUNT",
        "EXPECTED_IMAGE_WORDS",
        "EXPECTED_LAST_GENERATION",
        "EXPECTED_ARMS",
    ):
        if banned in source:
            raise AssertionError(
                f"M2 residual KAT symbol: "
                f"{banned}"
            )

    compile(
        source,
        str(M2_OUT),
        "exec",
    )

    return source


def derive_m3() -> str:
    verify_source(
        "M3",
        M3_SOURCE,
    )

    source = M3_SOURCE.read_text(
        encoding="utf-8"
    )

    old = (
        "from research.week15."
        "reproducibility.runtime_config import ("
    )

    new = (
        "from research.week15."
        "final_campaign.runtime_config import ("
    )

    if source.count(old) != 1:
        raise AssertionError(
            "unexpected M3 runtime-config "
            "import count"
        )

    derived = source.replace(
        old,
        new,
        1,
    )

    compile(
        derived,
        str(M3_OUT),
        "exec",
    )

    return derived


def main() -> None:
    outputs = {
        M1_OUT: derive_m1(),
        M2_OUT: derive_m2(),
        M3_OUT: derive_m3(),
    }

    for path, source in outputs.items():
        path.write_text(
            source,
            encoding="utf-8",
        )

        print(
            "DERIVED",
            path.relative_to(
                REPO_ROOT
            ),
            sha256_file(path),
        )


if __name__ == "__main__":
    main()
