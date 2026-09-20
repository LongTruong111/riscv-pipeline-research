import csv

import pytest

from research.week9.telemetry_writer import (
    BatchedCsvWriter,
)


def test_records_are_buffered_before_flush(tmp_path):
    path = tmp_path / "telemetry.csv"

    writer = BatchedCsvWriter(
        path,
        fieldnames=("epoch", "reward"),
        batch_size=3,
    )

    writer.write(
        {
            "epoch": 1,
            "reward": 2.0,
        }
    )

    writer.write(
        {
            "epoch": 2,
            "reward": 1.0,
        }
    )

    # No flush yet.
    assert writer.buffered_count == 2
    assert not path.exists()


def test_batch_size_triggers_flush(tmp_path):
    path = tmp_path / "telemetry.csv"

    writer = BatchedCsvWriter(
        path,
        fieldnames=("epoch", "reward"),
        batch_size=2,
    )

    writer.write(
        {
            "epoch": 1,
            "reward": 2.0,
        }
    )

    writer.write(
        {
            "epoch": 2,
            "reward": 1.0,
        }
    )

    assert writer.buffered_count == 0
    assert path.exists()

    with path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        rows = list(csv.DictReader(file))

    assert rows == [
        {
            "epoch": "1",
            "reward": "2.0",
        },
        {
            "epoch": "2",
            "reward": "1.0",
        },
    ]


def test_multiple_flushes_preserve_single_header(tmp_path):
    path = tmp_path / "telemetry.csv"

    writer = BatchedCsvWriter(
        path,
        fieldnames=("epoch", "reward"),
        batch_size=1,
    )

    writer.write(
        {
            "epoch": 1,
            "reward": 2.0,
        }
    )

    writer.write(
        {
            "epoch": 2,
            "reward": 1.0,
        }
    )

    lines = path.read_text(
        encoding="utf-8",
    ).splitlines()

    assert lines[0] == "epoch,reward"
    assert lines.count("epoch,reward") == 1
    assert len(lines) == 3


def test_close_flushes_partial_batch(tmp_path):
    path = tmp_path / "telemetry.csv"

    writer = BatchedCsvWriter(
        path,
        fieldnames=("epoch", "reward"),
        batch_size=10,
    )

    writer.write(
        {
            "epoch": 1,
            "reward": 2.0,
        }
    )

    assert not path.exists()

    writer.close()

    assert path.exists()
    assert writer.buffered_count == 0


def test_context_manager_flushes_on_exit(tmp_path):
    path = tmp_path / "telemetry.csv"

    with BatchedCsvWriter(
        path,
        fieldnames=("epoch", "reward"),
        batch_size=10,
    ) as writer:
        writer.write(
            {
                "epoch": 1,
                "reward": 2.0,
            }
        )

    assert path.exists()


def test_invalid_batch_size_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        BatchedCsvWriter(
            tmp_path / "x.csv",
            fieldnames=("a",),
            batch_size=0,
        )


def test_empty_fieldnames_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        BatchedCsvWriter(
            tmp_path / "x.csv",
            fieldnames=(),
            batch_size=10,
        )


def test_record_schema_mismatch_is_rejected(tmp_path):
    writer = BatchedCsvWriter(
        tmp_path / "x.csv",
        fieldnames=("epoch", "reward"),
        batch_size=10,
    )

    with pytest.raises(ValueError):
        writer.write(
            {
                "epoch": 1,
            }
        )


def test_write_after_close_is_rejected(tmp_path):
    writer = BatchedCsvWriter(
        tmp_path / "x.csv",
        fieldnames=("epoch",),
        batch_size=10,
    )

    writer.close()

    with pytest.raises(RuntimeError):
        writer.write(
            {
                "epoch": 1,
            }
        )
