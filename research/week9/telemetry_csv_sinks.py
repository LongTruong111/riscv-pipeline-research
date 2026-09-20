"""Week 9 CSV adapters for coverage and Adaptive-CGS telemetry.

These adapters intentionally keep file-I/O concerns outside:
- CoverageCollector
- AdaptiveTelemetrySink

Both adapters delegate buffered output to BatchedCsvWriter.
"""

from pathlib import Path

from research.week9.adaptive_telemetry import (
    AdaptiveTelemetryRecord,
)
from research.week9.coverage_collector import (
    CoverageCheckpoint,
)
from research.week9.telemetry_writer import (
    BatchedCsvWriter,
)


class CoverageCheckpointCsvSink:
    """Stream coverage checkpoints through batched CSV output."""

    FIELDNAMES = (
        "executed_instructions",
        "cycle",
        "l1_intent_count",
        "l1_validated_count",
        "l2_intent_count",
        "l2_validated_count",
    )

    def __init__(
        self,
        path,
        *,
        batch_size: int = 100,
    ) -> None:
        self._writer = BatchedCsvWriter(
            Path(path),
            fieldnames=self.FIELDNAMES,
            batch_size=batch_size,
        )

    def __call__(
        self,
        checkpoint: CoverageCheckpoint,
    ) -> None:
        if not isinstance(
            checkpoint,
            CoverageCheckpoint,
        ):
            raise TypeError(
                "checkpoint must be CoverageCheckpoint"
            )

        self._writer.write(
            {
                "executed_instructions": (
                    checkpoint.executed_instructions
                ),
                "cycle": checkpoint.cycle,
                "l1_intent_count": (
                    checkpoint.l1_intent_count
                ),
                "l1_validated_count": (
                    checkpoint.l1_validated_count
                ),
                "l2_intent_count": (
                    checkpoint.l2_intent_count
                ),
                "l2_validated_count": (
                    checkpoint.l2_validated_count
                ),
            }
        )

    def flush(self) -> None:
        self._writer.flush()

    def close(self) -> None:
        self._writer.close()

    @property
    def buffered_count(self) -> int:
        return self._writer.buffered_count


class AdaptiveCsvSink:
    """Stream Adaptive-CGS epoch telemetry through batched CSV output."""

    FIELDNAMES = (
        "epoch",
        "instruction_count",
        "arm_id",
        "reward",
        "q_value",
        "epsilon",
        "alpha",
        "pull_count",
    )

    def __init__(
        self,
        path,
        *,
        batch_size: int = 100,
    ) -> None:
        self._writer = BatchedCsvWriter(
            Path(path),
            fieldnames=self.FIELDNAMES,
            batch_size=batch_size,
        )

    def __call__(
        self,
        record: AdaptiveTelemetryRecord,
    ) -> None:
        if not isinstance(
            record,
            AdaptiveTelemetryRecord,
        ):
            raise TypeError(
                "record must be AdaptiveTelemetryRecord"
            )

        self._writer.write(
            {
                "epoch": record.epoch,
                "instruction_count": (
                    record.instruction_count
                ),
                "arm_id": record.arm_id,
                "reward": record.reward,
                "q_value": record.q_value,
                "epsilon": record.epsilon,
                "alpha": record.alpha,
                "pull_count": record.pull_count,
            }
        )

    def flush(self) -> None:
        self._writer.flush()

    def close(self) -> None:
        self._writer.close()

    @property
    def buffered_count(self) -> int:
        return self._writer.buffered_count
