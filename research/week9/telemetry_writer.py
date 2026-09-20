"""Week 9 batched telemetry output.

This writer intentionally buffers records and flushes them in batches,
avoiding per-cycle CSV I/O during performance campaigns.
"""

import csv
from pathlib import Path
from typing import Dict, Iterable, Mapping, Tuple


class BatchedCsvWriter:
    """Buffered CSV writer with fixed schema.

    Retained memory is bounded by batch_size:

        O(batch_size)

    with respect to campaign length.
    """

    def __init__(
        self,
        path,
        *,
        fieldnames: Iterable[str],
        batch_size: int = 100,
    ) -> None:
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or batch_size <= 0
        ):
            raise ValueError(
                "batch_size must be a positive integer"
            )

        self.path = Path(path)

        self.fieldnames: Tuple[str, ...] = tuple(
            fieldnames
        )

        if not self.fieldnames:
            raise ValueError(
                "fieldnames must not be empty"
            )

        if len(set(self.fieldnames)) != len(
            self.fieldnames
        ):
            raise ValueError(
                "fieldnames must be unique"
            )

        if any(
            not isinstance(name, str) or not name
            for name in self.fieldnames
        ):
            raise ValueError(
                "every fieldname must be a non-empty string"
            )

        self.batch_size = batch_size

        self._buffer = []
        self._closed = False
        self._header_written = self.path.exists()

    @property
    def buffered_count(self) -> int:
        return len(self._buffer)

    @property
    def closed(self) -> bool:
        return self._closed

    def _validate_record(
        self,
        record: Mapping,
    ) -> Dict:
        if not isinstance(record, Mapping):
            raise TypeError(
                "record must be a mapping"
            )

        expected = set(self.fieldnames)
        observed = set(record.keys())

        if observed != expected:
            missing = expected - observed
            extra = observed - expected

            raise ValueError(
                "record schema mismatch: "
                f"missing={sorted(missing)}, "
                f"extra={sorted(extra)}"
            )

        return {
            name: record[name]
            for name in self.fieldnames
        }

    def write(
        self,
        record: Mapping,
    ) -> None:
        if self._closed:
            raise RuntimeError(
                "cannot write to a closed BatchedCsvWriter"
            )

        normalized = self._validate_record(
            record
        )

        self._buffer.append(normalized)

        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if self._closed:
            raise RuntimeError(
                "cannot flush a closed BatchedCsvWriter"
            )

        if not self._buffer:
            return

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        mode = "a" if self._header_written else "w"

        with self.path.open(
            mode,
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=self.fieldnames,
            )

            if not self._header_written:
                writer.writeheader()
                self._header_written = True

            writer.writerows(self._buffer)

        self._buffer.clear()

    def close(self) -> None:
        if self._closed:
            return

        if self._buffer:
            self.flush()

        self._closed = True

    def __enter__(self):
        if self._closed:
            raise RuntimeError(
                "cannot enter a closed BatchedCsvWriter"
            )

        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        self.close()
        return False
