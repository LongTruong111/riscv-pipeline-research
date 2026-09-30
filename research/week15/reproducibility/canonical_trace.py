from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from typing import Any, Mapping

from research.week10.adaptive.campaign_telemetry import (
    CampaignCheckpointRecord,
    EpochTelemetryRecord,
)


CANONICAL_RECORD_ENCODING = "UTF-8"
CANONICAL_LOGICAL_FORMAT = "JSON_LINES"
CANONICAL_HASH = "SHA256"


class CanonicalTraceError(ValueError):
    """Raised when a value cannot enter a canonical trace."""


def _canonicalize(value: Any) -> Any:
    """
    Convert one semantic value into the frozen Week-15
    canonical JSON domain.

    Contract rules:
      - mapping keys are strings;
      - mapping key order is lexicographic at serialization;
      - sequence order is preserved;
      - sets are forbidden;
      - every binary float becomes:
            "hex:" + float.hex(value)
      - bool remains distinct from int;
      - no Python repr(), hash(), locale, or wall-clock state.
    """

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return "hex:" + value.hex()

    if isinstance(value, str):
        return value

    if isinstance(value, Mapping):
        result = {}

        for key, child in value.items():
            if not isinstance(key, str):
                raise CanonicalTraceError(
                    "canonical mapping keys must be strings"
                )

            result[key] = _canonicalize(child)

        return result

    if isinstance(value, (list, tuple)):
        return [
            _canonicalize(child)
            for child in value
        ]

    if isinstance(value, (set, frozenset)):
        raise CanonicalTraceError(
            "sets are forbidden in canonical traces"
        )

    raise CanonicalTraceError(
        "unsupported canonical trace value type: "
        f"{type(value).__name__}"
    )


def canonical_json_line(
    record: Mapping[str, Any],
) -> bytes:
    """
    Serialize one record using the single frozen equality format.

    Returned bytes always contain exactly one trailing LF.
    """

    if not isinstance(record, Mapping):
        raise CanonicalTraceError(
            "canonical trace record must be a mapping"
        )

    canonical = _canonicalize(record)

    text = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

    return (
        text + "\n"
    ).encode("utf-8")


class CanonicalTraceHasher:
    """
    O(1)-memory incremental SHA-256 trace hasher.

    History is deliberately not retained in RAM.
    """

    def __init__(self, name: str) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError(
                "trace name must be a non-empty string"
            )

        self._name = name
        self._hash = hashlib.sha256()
        self._record_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def record_count(self) -> int:
        return self._record_count

    def update(
        self,
        record: Mapping[str, Any],
    ) -> None:
        line = canonical_json_line(record)

        self._hash.update(line)
        self._record_count += 1

    def hexdigest(self) -> str:
        return self._hash.hexdigest()


class AdaptiveCanonicalTraceRecorder:
    """
    Streaming canonical trace recorder for Gate T15.

    This object does not calculate adaptive semantics.
    It only projects already-authoritative runtime observations
    into the frozen trace schemas and hashes them.

    Gate-required:
      - instruction_stream
      - arm_decision_trace
      - reward_trace
      - coverage_trace

    Supplemental:
      - q_trace
      - epoch_trace
    """

    _TRACE_NAMES = (
        "instruction_stream",
        "arm_decision_trace",
        "reward_trace",
        "coverage_trace",
        "q_trace",
        "epoch_trace",
    )

    def __init__(self) -> None:
        self._traces = {
            name: CanonicalTraceHasher(name)
            for name in self._TRACE_NAMES
        }

    def record_instruction(
        self,
        *,
        accepted_instruction_index: int,
        pc: int,
        instruction_word: int,
    ) -> None:
        """
        Record one already-validated accepted architectural event.

        This method deliberately receives primitives rather than a
        planned-stream object. The RTL harness must call it only from
        the accepted-event path after stream-identity validation.
        """

        if (
            isinstance(accepted_instruction_index, bool)
            or not isinstance(
                accepted_instruction_index,
                int,
            )
            or accepted_instruction_index <= 0
        ):
            raise ValueError(
                "accepted_instruction_index "
                "must be a positive integer"
            )

        if (
            isinstance(pc, bool)
            or not isinstance(pc, int)
            or not 0 <= pc <= 0xFFFFFFFF
        ):
            raise ValueError(
                "pc must be a 32-bit unsigned integer"
            )

        if (
            isinstance(instruction_word, bool)
            or not isinstance(
                instruction_word,
                int,
            )
            or not 0 <= instruction_word <= 0xFFFFFFFF
        ):
            raise ValueError(
                "instruction_word must be "
                "a 32-bit unsigned integer"
            )

        self._traces[
            "instruction_stream"
        ].update(
            {
                "accepted_instruction_index": (
                    accepted_instruction_index
                ),
                "instruction_word": instruction_word,
                "pc": pc,
            }
        )

    def record_epoch(
        self,
        record: EpochTelemetryRecord,
    ) -> None:
        """
        Project one authoritative EpochTelemetryRecord.

        Reward and Q are never recomputed here.
        """

        if not isinstance(
            record,
            EpochTelemetryRecord,
        ):
            raise TypeError(
                "record must be EpochTelemetryRecord"
            )

        self._traces[
            "arm_decision_trace"
        ].update(
            {
                "candidate_arms": (
                    record.candidate_arms
                ),
                "epoch_index": record.epoch_index,
                "selected_arm": record.selected_arm,
                "selection_mode": (
                    record.selection_mode
                ),
            }
        )

        self._traces[
            "reward_trace"
        ].update(
            {
                "actual_executed_instructions": (
                    record
                    .actual_executed_instructions
                ),
                "attributable_new_count": (
                    record
                    .attributable_new_l2_intent_count
                ),
                "epoch_index": record.epoch_index,
                "reward": record.reward,
                "selected_arm": record.selected_arm,
            }
        )

        self._traces[
            "q_trace"
        ].update(
            {
                "epoch_index": record.epoch_index,
                "q_values_after": (
                    record.q_values_after
                ),
            }
        )

        # Supplemental full authoritative epoch record.
        self._traces[
            "epoch_trace"
        ].update(
            asdict(record)
        )

    def record_checkpoint(
        self,
        record: CampaignCheckpointRecord,
    ) -> None:
        """
        Project one authoritative post-instruction coverage checkpoint.

        Cycle and adaptive snapshots are intentionally excluded from
        the gate-required coverage trace because the frozen minimum
        coverage equality contract concerns accepted-denominator
        coverage state.
        """

        if not isinstance(
            record,
            CampaignCheckpointRecord,
        ):
            raise TypeError(
                "record must be CampaignCheckpointRecord"
            )

        self._traces[
            "coverage_trace"
        ].update(
            {
                "accepted": (
                    record.executed_instructions
                ),
                "l1_intent": (
                    record.l1_intent_count
                ),
                "l1_validated": (
                    record.l1_validated_count
                ),
                "l2_intent": (
                    record.l2_intent_count
                ),
                "l2_validated": (
                    record.l2_validated_count
                ),
            }
        )

    def digests(self) -> dict[str, str]:
        return {
            name: self._traces[name].hexdigest()
            for name in sorted(self._traces)
        }

    def record_counts(self) -> dict[str, int]:
        return {
            name: self._traces[name].record_count
            for name in sorted(self._traces)
        }
