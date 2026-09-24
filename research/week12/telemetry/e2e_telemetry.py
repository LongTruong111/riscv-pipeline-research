"""Reporting-only Week-12 E2E telemetry."""

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Optional


SCHEMA_VERSION = "week12.e2e.v1"

_SHA1_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _require_nonnegative_int(name: str, value: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise ValueError(
            f"{name} must be a non-negative integer"
        )


@dataclass(frozen=True, slots=True)
class E2ETelemetryRecord:
    schema_version: str

    git_commit: str
    git_dirty: bool

    dut_variant: str
    workload: str

    accepted_instructions: int
    retired_instructions: int
    stall_cycles: int
    flush_cycles: int

    architectural_pass: bool

    functional_pass: bool
    functional_failures: int

    performance_pass: bool
    performance_failures: int
    total_excess_cycles: int

    coverage_valid: bool
    coverage_executed: int
    l1_intent_count: int
    l1_validated_count: int
    l2_intent_count: int
    l2_validated_count: int
    checkpoint_count: int

    l1_pending: int
    l2_terminal_pending: int
    protocol_errors: int

    first_failure: Optional[Mapping[str, Any]]

    waveform_path: Optional[str]
    waveform_sha256: Optional[str]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version "
                f"{self.schema_version!r}"
            )

        if not isinstance(self.git_commit, str):
            raise TypeError("git_commit must be a string")

        if _SHA1_RE.fullmatch(self.git_commit) is None:
            raise ValueError(
                "git_commit must be a full 40-hex commit ID"
            )

        if not isinstance(self.git_dirty, bool):
            raise TypeError("git_dirty must be bool")

        for name, value in (
            ("dut_variant", self.dut_variant),
            ("workload", self.workload),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"{name} must be a non-empty string"
                )

        for name, value in (
            ("accepted_instructions", self.accepted_instructions),
            ("retired_instructions", self.retired_instructions),
            ("stall_cycles", self.stall_cycles),
            ("flush_cycles", self.flush_cycles),
            ("functional_failures", self.functional_failures),
            ("performance_failures", self.performance_failures),
            ("total_excess_cycles", self.total_excess_cycles),
            ("coverage_executed", self.coverage_executed),
            ("l1_intent_count", self.l1_intent_count),
            ("l1_validated_count", self.l1_validated_count),
            ("l2_intent_count", self.l2_intent_count),
            ("l2_validated_count", self.l2_validated_count),
            ("checkpoint_count", self.checkpoint_count),
            ("l1_pending", self.l1_pending),
            ("l2_terminal_pending", self.l2_terminal_pending),
            ("protocol_errors", self.protocol_errors),
        ):
            _require_nonnegative_int(name, value)

        if self.retired_instructions > self.accepted_instructions:
            raise ValueError(
                "retired_instructions cannot exceed "
                "accepted_instructions"
            )

        if self.coverage_executed > self.accepted_instructions:
            raise ValueError(
                "coverage_executed cannot exceed "
                "accepted_instructions"
            )

        if self.functional_failures > self.retired_instructions:
            raise ValueError(
                "functional_failures cannot exceed "
                "retired_instructions"
            )

        if self.performance_failures > self.retired_instructions:
            raise ValueError(
                "performance_failures cannot exceed "
                "retired_instructions"
            )

        if (
            self.functional_pass
            and self.functional_failures != 0
        ):
            raise ValueError(
                "functional_pass conflicts with failure count"
            )

        if (
            self.performance_pass
            and self.performance_failures != 0
        ):
            raise ValueError(
                "performance_pass conflicts with failure count"
            )

        if self.l1_validated_count > self.l1_intent_count:
            raise ValueError(
                "L1 Validated cannot exceed L1 Intent"
            )

        if self.l2_validated_count > self.l2_intent_count:
            raise ValueError(
                "L2 Validated cannot exceed L2 Intent"
            )

        if (
            self.first_failure is not None
            and not isinstance(self.first_failure, Mapping)
        ):
            raise TypeError(
                "first_failure must be a mapping or None"
            )

        has_wave_path = self.waveform_path is not None
        has_wave_hash = self.waveform_sha256 is not None

        if has_wave_path != has_wave_hash:
            raise ValueError(
                "waveform_path and waveform_sha256 "
                "must either both be present or both be None"
            )

        if has_wave_path:
            assert self.waveform_path is not None
            assert self.waveform_sha256 is not None

            if not self.waveform_path:
                raise ValueError(
                    "waveform_path must not be empty"
                )

            if (
                _SHA256_RE.fullmatch(
                    self.waveform_sha256
                )
                is None
            ):
                raise ValueError(
                    "waveform_sha256 must be 64 hex digits"
                )

    @property
    def telemetry_complete(self) -> bool:
        # Successful construction proves schema completeness.
        return True

    def to_dict(self) -> dict:
        result = asdict(self)

        result["git_commit"] = (
            self.git_commit.lower()
        )

        if self.waveform_sha256 is not None:
            result["waveform_sha256"] = (
                self.waveform_sha256.lower()
            )

        return result


def write_json(
    record: E2ETelemetryRecord,
    path,
) -> Path:
    """Atomically serialize one final E2E record."""

    if not isinstance(record, E2ETelemetryRecord):
        raise TypeError(
            "record must be E2ETelemetryRecord"
        )

    output = Path(path)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = output.with_name(
        output.name + ".tmp"
    )

    payload = json.dumps(
        record.to_dict(),
        indent=2,
        sort_keys=True,
    ) + "\n"

    temporary.write_text(
        payload,
        encoding="utf-8",
    )

    temporary.replace(output)
    return output


def sha256_file(path) -> str:
    """Return SHA-256 of an artifact without loading it all into RAM."""

    artifact = Path(path)

    digest = hashlib.sha256()

    with artifact.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()
