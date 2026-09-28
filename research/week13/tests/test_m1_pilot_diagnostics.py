from research.week13.pure_random.pilot_diagnostics import (
    build_m1_plan_diagnostics,
)
from research.week13.pure_random.stream_planner import (
    generate_pure_random_plan,
)


def test_diagnostics_preserve_plan_hash():
    plan = generate_pure_random_plan(
        11001,
        1000,
    )

    before = plan.plan_hash

    diagnostics = (
        build_m1_plan_diagnostics(
            plan
        )
    )

    after = plan.plan_hash

    assert before == after
    assert diagnostics is not None


def test_diagnostics_are_deterministic():
    plan = generate_pure_random_plan(
        11001,
        1000,
    )

    first = build_m1_plan_diagnostics(
        plan
    )

    second = build_m1_plan_diagnostics(
        plan
    )

    assert first == second


def test_payload_and_structural_nop_conservation():
    plan = generate_pure_random_plan(
        11001,
        1000,
    )

    diagnostics = (
        build_m1_plan_diagnostics(
            plan
        )
    )

    assert (
        sum(
            diagnostics.family_counts.values()
        )
        == len(plan.blocks)
    )

    assert (
        len(plan.blocks)
        + diagnostics
        .structural_nop_accepted_count
        == plan.accepted_instruction_count
    )


def test_branch_diagnostics_conserve_payloads():
    plan = generate_pure_random_plan(
        11001,
        1000,
    )

    diagnostics = (
        build_m1_plan_diagnostics(
            plan
        )
    )

    branch_count = (
        diagnostics.family_counts[
            "BRANCH"
        ]
    )

    assert (
        sum(
            diagnostics
            .branch_subtype_counts
            .values()
        )
        == branch_count
    )

    assert (
        diagnostics.branch_taken_count
        + diagnostics.branch_not_taken_count
        == branch_count
    )


def test_memory_diagnostics_conserve_payloads():
    plan = generate_pure_random_plan(
        11001,
        1000,
    )

    diagnostics = (
        build_m1_plan_diagnostics(
            plan
        )
    )

    lw_count = (
        diagnostics.family_counts["LW"]
    )

    sw_count = (
        diagnostics.family_counts["SW"]
    )

    memory_count = (
        lw_count + sw_count
    )

    assert (
        sum(
            diagnostics
            .lw_ea_histogram
            .values()
        )
        == lw_count
    )

    assert (
        sum(
            diagnostics
            .sw_ea_histogram
            .values()
        )
        == sw_count
    )

    assert (
        sum(
            diagnostics
            .memory_viable_base_set_size_histogram
            .values()
        )
        == memory_count
    )

    assert (
        sum(
            diagnostics
            .accepted_base_register_histogram
            .values()
        )
        == memory_count
    )


def test_histogram_domains_are_frozen():
    plan = generate_pure_random_plan(
        11001,
        100,
    )

    diagnostics = (
        build_m1_plan_diagnostics(
            plan
        )
    )

    assert set(
        diagnostics.lw_ea_histogram
    ) == {
        str(ea)
        for ea in range(0, 512, 4)
    }

    assert set(
        diagnostics.sw_ea_histogram
    ) == {
        str(ea)
        for ea in range(0, 512, 4)
    }

    assert set(
        diagnostics
        .memory_viable_base_set_size_histogram
    ) == {
        str(size)
        for size in range(1, 33)
    }

    assert set(
        diagnostics
        .accepted_base_register_histogram
    ) == {
        f"x{reg}"
        for reg in range(32)
    }
