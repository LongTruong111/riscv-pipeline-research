from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research.week10.adaptive.campaign_telemetry import (
    CampaignCheckpointRecord,
    EpochTelemetryRecord,
)
from research.week15.reproducibility.canonical_trace import (
    AdaptiveCanonicalTraceRecorder,
    CanonicalTraceError,
    CanonicalTraceHasher,
    canonical_json_line,
)


ROOT = Path(__file__).resolve().parents[3]

CONTRACT = (
    ROOT
    / "research/week15/contracts/"
    "adaptive_cgs_freeze.yaml"
)


def load_contract() -> dict:
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8"
        )
    )


def epoch_record() -> EpochTelemetryRecord:
    return EpochTelemetryRecord(
        schema_version="week10-adaptive-v1",
        checkpoint_semantics=(
            "post_instruction_cut_v1"
        ),
        epoch_index=0,
        selected_arm="A0",
        selection_mode="epsilon_exploration",
        candidate_arms=(
            "A0",
            "A1",
            "A2",
        ),
        target_d1=7,
        target_d2=None,
        first_executed_instruction=1,
        last_executed_instruction=500,
        actual_executed_instructions=500,
        covered_at_epoch_start_count=0,
        global_observed_l2_intent_count=2,
        attributable_observed_l2_intent_count=1,
        global_new_l2_intent_count=2,
        attributable_new_l2_intent_count=1,
        reward=2.0,
        q_value_before=0.0,
        max_q_before=0.0,
        old_q=0.0,
        new_q=1.0,
        pull_count=1,
        q_values_after=(
            ("A0", 1.0),
            ("A1", 0.0),
        ),
        pull_counts_after=(
            ("A0", 1),
            ("A1", 0),
        ),
        recent_rewards_after=(
            ("A0", 2.0),
            ("A1", 0.0),
        ),
    )


def checkpoint_record() -> CampaignCheckpointRecord:
    return CampaignCheckpointRecord(
        schema_version="week10-adaptive-v1",
        checkpoint_semantics=(
            "post_instruction_cut_v1"
        ),
        executed_instructions=1000,
        cycle=1123,
        l1_intent_count=17,
        l1_validated_count=16,
        l2_intent_count=42,
        l2_validated_count=40,
        epoch_index=2,
        q_values=(
            ("A0", 1.0),
            ("A1", 0.0),
        ),
        pull_counts=(
            ("A0", 1),
            ("A1", 1),
        ),
        recent_rewards=(
            ("A0", 2.0),
            ("A1", 0.0),
        ),
    )


def test_contract_canonical_serialization_matches_implementation():
    canonical = (
        load_contract()
        ["freeze"]
        ["canonical_serialization"]
    )

    assert canonical[
        "record_encoding"
    ] == "UTF-8"

    assert canonical[
        "logical_format"
    ] == "JSON_LINES"

    assert canonical[
        "mapping_key_order"
    ] == "lexicographic"

    assert canonical[
        "sequence_order"
    ] == "preserved"

    assert canonical[
        "set_values_allowed"
    ] is False

    assert canonical[
        "json_separators"
    ] == [
        ",",
        ":",
    ]

    assert canonical[
        "ensure_ascii"
    ] is False

    assert canonical[
        "record_terminator"
    ] == "\\n"

    assert canonical[
        "hash"
    ] == "SHA256"


def test_canonical_line_sorts_keys_and_hex_encodes_floats():
    line = canonical_json_line(
        {
            "z": 1.5,
            "a": 0.1,
            "m": [
                2.0,
                3,
            ],
        }
    )

    assert line == (
        b'{"a":"hex:0x1.999999999999ap-4",'
        b'"m":["hex:0x1.0000000000000p+1",3],'
        b'"z":"hex:0x1.8000000000000p+0"}\n'
    )


def test_canonical_line_preserves_sequence_order():
    first = canonical_json_line(
        {
            "x": [
                "A0",
                "A1",
            ]
        }
    )

    second = canonical_json_line(
        {
            "x": [
                "A1",
                "A0",
            ]
        }
    )

    assert first != second


@pytest.mark.parametrize(
    "value",
    [
        {1, 2},
        frozenset({1, 2}),
    ],
)
def test_canonical_line_rejects_sets(value):
    with pytest.raises(
        CanonicalTraceError,
        match="sets are forbidden",
    ):
        canonical_json_line(
            {"value": value}
        )


def test_canonical_line_rejects_nonstring_mapping_key():
    with pytest.raises(
        CanonicalTraceError,
        match="mapping keys must be strings",
    ):
        canonical_json_line(
            {
                "outer": {
                    1: "invalid",
                }
            }
        )


def test_incremental_hasher_matches_exact_concatenated_jsonl():
    records = [
        {
            "i": 1,
            "reward": 0.5,
        },
        {
            "i": 2,
            "reward": 1.25,
        },
    ]

    hasher = CanonicalTraceHasher(
        "test_trace"
    )

    expected_bytes = b""

    for record in records:
        line = canonical_json_line(
            record
        )

        expected_bytes += line
        hasher.update(record)

    assert hasher.record_count == 2

    assert (
        hasher.hexdigest()
        == hashlib.sha256(
            expected_bytes
        ).hexdigest()
    )


def test_same_semantic_mapping_gives_same_hash_regardless_of_input_key_order():
    first = CanonicalTraceHasher("t")
    second = CanonicalTraceHasher("t")

    first.update(
        {
            "a": 1,
            "b": 0.5,
        }
    )

    second.update(
        {
            "b": 0.5,
            "a": 1,
        }
    )

    assert (
        first.hexdigest()
        == second.hexdigest()
    )


def test_instruction_trace_uses_only_accepted_identity_fields():
    recorder = (
        AdaptiveCanonicalTraceRecorder()
    )

    recorder.record_instruction(
        accepted_instruction_index=1,
        pc=0x00000000,
        instruction_word=0x12345678,
    )

    counts = recorder.record_counts()

    assert counts[
        "instruction_stream"
    ] == 1

    assert counts[
        "arm_decision_trace"
    ] == 0

    assert counts[
        "reward_trace"
    ] == 0

    assert counts[
        "coverage_trace"
    ] == 0


def test_epoch_record_updates_four_epoch_derived_traces_once():
    recorder = (
        AdaptiveCanonicalTraceRecorder()
    )

    recorder.record_epoch(
        epoch_record()
    )

    counts = recorder.record_counts()

    assert counts[
        "arm_decision_trace"
    ] == 1

    assert counts[
        "reward_trace"
    ] == 1

    assert counts[
        "q_trace"
    ] == 1

    assert counts[
        "epoch_trace"
    ] == 1

    assert counts[
        "instruction_stream"
    ] == 0

    assert counts[
        "coverage_trace"
    ] == 0


def test_checkpoint_updates_only_gate_coverage_trace():
    recorder = (
        AdaptiveCanonicalTraceRecorder()
    )

    recorder.record_checkpoint(
        checkpoint_record()
    )

    counts = recorder.record_counts()

    assert counts[
        "coverage_trace"
    ] == 1

    assert counts[
        "instruction_stream"
    ] == 0

    assert counts[
        "arm_decision_trace"
    ] == 0

    assert counts[
        "reward_trace"
    ] == 0

    assert counts[
        "q_trace"
    ] == 0

    assert counts[
        "epoch_trace"
    ] == 0


def test_same_authoritative_records_produce_identical_all_trace_hashes():
    first = (
        AdaptiveCanonicalTraceRecorder()
    )

    second = (
        AdaptiveCanonicalTraceRecorder()
    )

    for recorder in (
        first,
        second,
    ):
        recorder.record_instruction(
            accepted_instruction_index=1,
            pc=0,
            instruction_word=0x12345678,
        )

        recorder.record_epoch(
            epoch_record()
        )

        recorder.record_checkpoint(
            checkpoint_record()
        )

    assert (
        first.digests()
        == second.digests()
    )

    assert (
        first.record_counts()
        == second.record_counts()
    )


def test_gate_required_trace_names_match_contract():
    contract = load_contract()

    required = set(
        contract["freeze"]
        ["trace_schema"]
        ["gate_required_traces"]
    )

    recorder = (
        AdaptiveCanonicalTraceRecorder()
    )

    available = set(
        recorder.digests()
    )

    assert required <= available

    assert required == {
        "instruction_stream",
        "arm_decision_trace",
        "reward_trace",
        "coverage_trace",
    }


def test_supplemental_trace_names_match_contract():
    contract = load_contract()

    supplemental = set(
        contract["freeze"]
        ["trace_schema"]
        ["supplemental_traces"]
    )

    recorder = (
        AdaptiveCanonicalTraceRecorder()
    )

    available = set(
        recorder.digests()
    )

    assert supplemental <= available

    assert supplemental == {
        "q_trace",
        "epoch_trace",
    }


@pytest.mark.parametrize(
    (
        "accepted_instruction_index",
        "pc",
        "instruction_word",
    ),
    [
        (0, 0, 0),
        (-1, 0, 0),
        (True, 0, 0),
        (1, -1, 0),
        (1, 0x1_0000_0000, 0),
        (1, 0, -1),
        (1, 0, 0x1_0000_0000),
    ],
)
def test_instruction_record_rejects_invalid_identity(
    accepted_instruction_index,
    pc,
    instruction_word,
):
    recorder = (
        AdaptiveCanonicalTraceRecorder()
    )

    with pytest.raises(ValueError):
        recorder.record_instruction(
            accepted_instruction_index=(
                accepted_instruction_index
            ),
            pc=pc,
            instruction_word=(
                instruction_word
            ),
        )
