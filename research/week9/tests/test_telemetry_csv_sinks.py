import csv

from research.week9.adaptive_telemetry import (
    AdaptiveTelemetryRecord,
)
from research.week9.coverage_collector import (
    CoverageCheckpoint,
)
from research.week9.telemetry_csv_sinks import (
    AdaptiveCsvSink,
    CoverageCheckpointCsvSink,
)


def test_coverage_checkpoint_sink_writes_expected_schema(tmp_path):
    path = tmp_path / "coverage.csv"

    sink = CoverageCheckpointCsvSink(
        path,
        batch_size=2,
    )

    sink(
        CoverageCheckpoint(
            executed_instructions=1000,
            cycle=1200,
            l1_intent_count=10,
            l1_validated_count=8,
            l2_intent_count=40,
            l2_validated_count=35,
        )
    )

    sink(
        CoverageCheckpoint(
            executed_instructions=2000,
            cycle=2400,
            l1_intent_count=15,
            l1_validated_count=12,
            l2_intent_count=55,
            l2_validated_count=49,
        )
    )

    sink.close()

    with path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        rows = list(csv.DictReader(file))

    assert rows[0]["executed_instructions"] == "1000"
    assert rows[0]["l1_intent_count"] == "10"
    assert rows[0]["l2_validated_count"] == "35"

    assert rows[1]["executed_instructions"] == "2000"


def test_adaptive_sink_writes_expected_schema(tmp_path):
    path = tmp_path / "adaptive.csv"

    sink = AdaptiveCsvSink(
        path,
        batch_size=1,
    )

    sink(
        AdaptiveTelemetryRecord(
            epoch=1,
            instruction_count=1000,
            arm_id="A2",
            reward=3.0,
            q_value=1.25,
            epsilon=0.10,
            alpha=0.30,
            pull_count=1,
        )
    )

    sink.close()

    with path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        rows = list(csv.DictReader(file))

    assert rows == [
        {
            "epoch": "1",
            "instruction_count": "1000",
            "arm_id": "A2",
            "reward": "3.0",
            "q_value": "1.25",
            "epsilon": "0.1",
            "alpha": "0.3",
            "pull_count": "1",
        }
    ]


def test_coverage_sink_can_flush_partial_batch(tmp_path):
    path = tmp_path / "coverage.csv"

    sink = CoverageCheckpointCsvSink(
        path,
        batch_size=100,
    )

    sink(
        CoverageCheckpoint(
            executed_instructions=1000,
            cycle=1200,
            l1_intent_count=1,
            l1_validated_count=1,
            l2_intent_count=1,
            l2_validated_count=1,
        )
    )

    assert not path.exists()

    sink.close()

    assert path.exists()


def test_adaptive_sink_can_flush_partial_batch(tmp_path):
    path = tmp_path / "adaptive.csv"

    sink = AdaptiveCsvSink(
        path,
        batch_size=100,
    )

    sink(
        AdaptiveTelemetryRecord(
            epoch=1,
            instruction_count=1000,
            arm_id="A0",
            reward=0.0,
            q_value=0.0,
            epsilon=0.05,
            alpha=0.1,
            pull_count=1,
        )
    )

    assert not path.exists()

    sink.close()

    assert path.exists()
