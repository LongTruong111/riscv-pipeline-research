import pytest

from research.week12.telemetry.mutation_telemetry import (
    MutationSmokeRecord,
    SCHEMA_VERSION,
)


def valid_record(**overrides):
    values = dict(
        schema_version=SCHEMA_VERSION,
        git_commit="a" * 40,
        git_dirty=False,
        dut_variant="m1-smoke",
        workload="integrated50",
        canonical_control_pass=True,
        mutant_compile_pass=True,
        mutant_simulation_pass=True,
        accepted_instructions=50,
        retired_instructions=50,
        target_activation_count=12,
        target_suppressed_count=12,
        checker_failure_count=12,
        authoritative_checker_failure=True,
        first_target_instruction_id=5,
        first_failure={
            "instruction_id": 5,
            "checker": "week11_integrated_timing",
            "check_name": "forward_a",
            "expected": 2,
            "observed": 0,
        },
        waveform_path="failure.vcd",
        waveform_sha256="b" * 64,
    )

    values.update(overrides)
    return MutationSmokeRecord(**values)


def test_valid_record_is_caught():
    assert valid_record().mutation_caught


def test_compile_failure_is_not_caught():
    assert not valid_record(
        mutant_compile_pass=False
    ).mutation_caught


def test_no_target_activation_is_not_caught():
    assert not valid_record(
        target_activation_count=0,
        target_suppressed_count=0,
    ).mutation_caught


def test_checker_flag_requires_failure_count():
    with pytest.raises(
        ValueError,
        match="conflicts",
    ):
        valid_record(
            checker_failure_count=0,
        )


def test_suppressed_cannot_exceed_activation():
    with pytest.raises(
        ValueError,
        match="cannot exceed",
    ):
        valid_record(
            target_activation_count=1,
            target_suppressed_count=2,
        )
