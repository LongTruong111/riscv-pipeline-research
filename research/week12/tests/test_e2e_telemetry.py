import json

import pytest

from research.week12.telemetry.e2e_telemetry import (
    E2ETelemetryRecord,
    SCHEMA_VERSION,
    sha256_file,
    write_json,
)


def valid_record(**overrides):
    values = dict(
        schema_version=SCHEMA_VERSION,
        git_commit="a" * 40,
        git_dirty=False,
        dut_variant="canonical",
        workload="golden58",
        accepted_instructions=58,
        retired_instructions=58,
        stall_cycles=10,
        flush_cycles=0,
        architectural_pass=True,
        functional_pass=True,
        functional_failures=0,
        performance_pass=True,
        performance_failures=0,
        total_excess_cycles=0,
        coverage_valid=True,
        coverage_executed=58,
        l1_intent_count=4,
        l1_validated_count=4,
        l2_intent_count=4,
        l2_validated_count=4,
        checkpoint_count=0,
        l1_pending=0,
        l2_terminal_pending=1,
        protocol_errors=0,
        first_failure=None,
        waveform_path=None,
        waveform_sha256=None,
    )

    values.update(overrides)
    return E2ETelemetryRecord(**values)


def test_valid_record_is_complete():
    record = valid_record()

    assert record.telemetry_complete

    payload = record.to_dict()

    assert payload["accepted_instructions"] == 58
    assert payload["first_failure"] is None
    assert payload["waveform_path"] is None


def test_validated_cannot_exceed_intent():
    with pytest.raises(
        ValueError,
        match="L1 Validated",
    ):
        valid_record(
            l1_intent_count=3,
            l1_validated_count=4,
        )


def test_waveform_metadata_is_atomic_pair():
    with pytest.raises(
        ValueError,
        match="must either both be present",
    ):
        valid_record(
            waveform_path="failure.vcd",
            waveform_sha256=None,
        )


def test_first_failure_is_serialized(tmp_path):
    record = valid_record(
        functional_pass=False,
        functional_failures=1,
        first_failure={
            "instruction_id": 5,
            "checker": "functional",
            "check_name": "write_data",
        },
    )

    output = write_json(
        record,
        tmp_path / "record.json",
    )

    payload = json.loads(
        output.read_text(encoding="utf-8")
    )

    assert (
        payload["first_failure"]["instruction_id"]
        == 5
    )


def test_json_write_is_deterministic(tmp_path):
    record = valid_record()

    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_json(record, first)
    write_json(record, second)

    assert first.read_bytes() == second.read_bytes()


def test_sha256_file(tmp_path):
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"abc")

    assert sha256_file(artifact) == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )
