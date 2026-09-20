import csv

from research.week9.adaptive_telemetry import (
    AdaptiveTelemetryRecord,
    AdaptiveTelemetrySink,
)
from research.week9.coverage_collector import (
    CoverageCollector,
)
from research.week9.telemetry_csv_sinks import (
    AdaptiveCsvSink,
    CoverageCheckpointCsvSink,
)


def test_coverage_collector_streams_checkpoints_without_retention(
    tmp_path,
):
    path = tmp_path / "coverage.csv"

    csv_sink = CoverageCheckpointCsvSink(
        path,
        batch_size=2,
    )

    collector = CoverageCollector(
        checkpoint_interval=1000,
        retain_checkpoints=False,
        checkpoint_sink=csv_sink,
    )

    collector.record_l1_intent(
        "H01",
        instruction_id=2,
        cycle=2,
        wall_ns=100,
    )

    collector.record_l1_validated(
        "H01",
        instruction_id=2,
        cycle=5,
        wall_ns=200,
    )

    collector.record_l2_intent(
        "d1",
        5,
        instruction_id=2,
        cycle=2,
        wall_ns=300,
    )

    for instruction_id in range(1, 2001):
        collector.record_instruction(
            instruction_id=instruction_id,
            cycle=instruction_id + 3,
        )

    csv_sink.close()

    # Production mode keeps no checkpoint history.
    assert collector.checkpoints == []

    with path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 2

    assert rows[0]["executed_instructions"] == "1000"
    assert rows[0]["l1_intent_count"] == "1"
    assert rows[0]["l1_validated_count"] == "1"
    assert rows[0]["l2_intent_count"] == "1"
    assert rows[0]["l2_validated_count"] == "0"

    assert rows[1]["executed_instructions"] == "2000"


def test_adaptive_telemetry_streams_without_retention(
    tmp_path,
):
    path = tmp_path / "adaptive.csv"

    csv_sink = AdaptiveCsvSink(
        path,
        batch_size=2,
    )

    telemetry = AdaptiveTelemetrySink(
        retain_records=False,
        record_sink=csv_sink,
    )

    telemetry.emit(
        AdaptiveTelemetryRecord(
            epoch=1,
            instruction_count=1000,
            arm_id="A2",
            reward=3.0,
            q_value=1.0,
            epsilon=0.10,
            alpha=0.30,
            pull_count=1,
        )
    )

    telemetry.emit(
        AdaptiveTelemetryRecord(
            epoch=2,
            instruction_count=2000,
            arm_id="A4",
            reward=1.0,
            q_value=0.8,
            epsilon=0.10,
            alpha=0.30,
            pull_count=1,
        )
    )

    csv_sink.close()

    # Production mode retains only sequencing state.
    assert telemetry.records == []
    assert telemetry.emitted_count == 2

    with path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 2

    assert rows[0]["epoch"] == "1"
    assert rows[0]["arm_id"] == "A2"

    assert rows[1]["epoch"] == "2"
    assert rows[1]["arm_id"] == "A4"


def test_large_checkpoint_stream_keeps_collector_history_empty(
    tmp_path,
):
    path = tmp_path / "coverage.csv"

    csv_sink = CoverageCheckpointCsvSink(
        path,
        batch_size=8,
    )

    collector = CoverageCollector(
        checkpoint_interval=1000,
        retain_checkpoints=False,
        checkpoint_sink=csv_sink,
    )

    # 100 checkpoints, but none retained in collector RAM.
    for instruction_id in range(1, 100_001):
        collector.record_instruction(
            instruction_id=instruction_id,
            cycle=instruction_id + 3,
        )

    csv_sink.close()

    assert collector.executed_instructions == 100_000
    assert collector.checkpoints == []

    with path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 100
    assert rows[-1]["executed_instructions"] == "100000"
