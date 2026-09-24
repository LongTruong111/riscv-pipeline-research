"""Week-12 mutation-smoke evidence schema."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping


SCHEMA_VERSION = "week12.mutation.v1"

_SHA1_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _nonnegative(name: str, value: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise ValueError(
            f"{name} must be a non-negative integer"
        )


@dataclass(frozen=True, slots=True)
class MutationSmokeRecord:
    schema_version: str

    git_commit: str
    git_dirty: bool

    dut_variant: str
    workload: str

    canonical_control_pass: bool
    mutant_compile_pass: bool
    mutant_simulation_pass: bool

    accepted_instructions: int
    retired_instructions: int

    target_activation_count: int
    target_suppressed_count: int

    checker_failure_count: int
    authoritative_checker_failure: bool

    first_target_instruction_id: int
    first_failure: Mapping[str, Any]

    waveform_path: str
    waveform_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported schema_version")

        if _SHA1_RE.fullmatch(self.git_commit) is None:
            raise ValueError(
                "git_commit must be a full 40-hex commit ID"
            )

        if not isinstance(self.git_dirty, bool):
            raise TypeError("git_dirty must be bool")

        if not self.dut_variant:
            raise ValueError("dut_variant must not be empty")

        if not self.workload:
            raise ValueError("workload must not be empty")

        for name, value in (
            (
                "accepted_instructions",
                self.accepted_instructions,
            ),
            (
                "retired_instructions",
                self.retired_instructions,
            ),
            (
                "target_activation_count",
                self.target_activation_count,
            ),
            (
                "target_suppressed_count",
                self.target_suppressed_count,
            ),
            (
                "checker_failure_count",
                self.checker_failure_count,
            ),
            (
                "first_target_instruction_id",
                self.first_target_instruction_id,
            ),
        ):
            _nonnegative(name, value)

        if (
            self.retired_instructions
            > self.accepted_instructions
        ):
            raise ValueError(
                "retired cannot exceed accepted"
            )

        if (
            self.target_suppressed_count
            > self.target_activation_count
        ):
            raise ValueError(
                "suppressed target count cannot exceed "
                "activation count"
            )

        if (
            self.authoritative_checker_failure
            and self.checker_failure_count == 0
        ):
            raise ValueError(
                "checker failure flag conflicts with count"
            )

        if not isinstance(self.first_failure, Mapping):
            raise TypeError(
                "first_failure must be a mapping"
            )

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
    def mutation_caught(self) -> bool:
        return (
            self.canonical_control_pass
            and self.mutant_compile_pass
            and self.mutant_simulation_pass
            and self.target_activation_count > 0
            and self.authoritative_checker_failure
            and self.checker_failure_count > 0
            and bool(self.first_failure)
            and bool(self.waveform_path)
            and bool(self.waveform_sha256)
        )

    def to_dict(self) -> dict:
        result = asdict(self)
        result["git_commit"] = self.git_commit.lower()
        result["waveform_sha256"] = (
            self.waveform_sha256.lower()
        )
        result["mutation_caught"] = (
            self.mutation_caught
        )
        return result


def write_json(
    record: MutationSmokeRecord,
    path,
) -> Path:
    if not isinstance(
        record,
        MutationSmokeRecord,
    ):
        raise TypeError(
            "record must be MutationSmokeRecord"
        )

    output = Path(path)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = output.with_name(
        output.name + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            record.to_dict(),
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    temporary.replace(output)
    return output
