"""Week 9 Adaptive-CGS telemetry.

Telemetry is emitted once per adaptation epoch, not per simulation cycle.

Frozen Week-5 preregistration:
- arms: A0..A9
- epsilon: {0.05, 0.10, 0.20}
- alpha: {0.1, 0.3, 0.5}

Production use should normally set retain_records=False and stream records
through record_sink so retained memory remains bounded with campaign length.
"""

from dataclasses import dataclass
import math
from numbers import Real
from typing import Callable, List, Optional


FROZEN_ARM_IDS = tuple(f"A{i}" for i in range(10))
FROZEN_EPSILON = frozenset({0.05, 0.10, 0.20})
FROZEN_ALPHA = frozenset({0.1, 0.3, 0.5})


def _require_positive_int(name: str, value: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValueError(f"{name} must be a positive integer")


def _require_nonnegative_int(name: str, value: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise ValueError(
            f"{name} must be a non-negative integer"
        )


def _require_finite_real(name: str, value: Real) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number")

    converted = float(value)

    if not math.isfinite(converted):
        raise ValueError(f"{name} must be finite")

    return converted


@dataclass(frozen=True, slots=True)
class AdaptiveTelemetryRecord:
    """One Adaptive-CGS epoch telemetry record."""

    epoch: int
    instruction_count: int

    arm_id: str
    reward: float
    q_value: float

    epsilon: float
    alpha: float
    pull_count: int

    def __post_init__(self) -> None:
        _require_positive_int("epoch", self.epoch)
        _require_nonnegative_int(
            "instruction_count",
            self.instruction_count,
        )
        _require_positive_int(
            "pull_count",
            self.pull_count,
        )

        if self.arm_id not in FROZEN_ARM_IDS:
            raise ValueError(
                f"invalid frozen Adaptive-CGS arm: "
                f"{self.arm_id!r}"
            )

        reward = _require_finite_real(
            "reward",
            self.reward,
        )
        q_value = _require_finite_real(
            "q_value",
            self.q_value,
        )
        epsilon = _require_finite_real(
            "epsilon",
            self.epsilon,
        )
        alpha = _require_finite_real(
            "alpha",
            self.alpha,
        )

        if reward < 0:
            raise ValueError(
                "reward must be non-negative"
            )

        if epsilon not in FROZEN_EPSILON:
            raise ValueError(
                "epsilon is outside the frozen "
                "preregistered candidate set"
            )

        if alpha not in FROZEN_ALPHA:
            raise ValueError(
                "alpha is outside the frozen "
                "preregistered candidate set"
            )

        # Normalize numeric subclasses to plain float in the frozen object.
        object.__setattr__(self, "reward", reward)
        object.__setattr__(self, "q_value", q_value)
        object.__setattr__(self, "epsilon", epsilon)
        object.__setattr__(self, "alpha", alpha)


class AdaptiveTelemetrySink:
    """Bounded/streamable Adaptive-CGS telemetry sink.

    retain_records=False keeps only O(1) sequencing state in memory.
    """

    def __init__(
        self,
        *,
        retain_records: bool = False,
        record_sink: Optional[
            Callable[[AdaptiveTelemetryRecord], None]
        ] = None,
    ) -> None:
        if not isinstance(retain_records, bool):
            raise TypeError(
                "retain_records must be bool"
            )

        if (
            record_sink is not None
            and not callable(record_sink)
        ):
            raise TypeError(
                "record_sink must be callable or None"
            )

        self.retain_records = retain_records
        self.record_sink = record_sink

        self.records: List[
            AdaptiveTelemetryRecord
        ] = []

        self._last_epoch = 0
        self._last_instruction_count = 0
        self._emitted_count = 0

    @property
    def emitted_count(self) -> int:
        return self._emitted_count

    def emit(
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

        expected_epoch = self._last_epoch + 1

        if record.epoch != expected_epoch:
            raise ValueError(
                "adaptive telemetry epochs must be "
                "strictly contiguous: "
                f"expected {expected_epoch}, "
                f"got {record.epoch}"
            )

        if (
            record.instruction_count
            < self._last_instruction_count
        ):
            raise ValueError(
                "instruction_count must not decrease "
                "across adaptive epochs"
            )

        if self.retain_records:
            self.records.append(record)

        if self.record_sink is not None:
            self.record_sink(record)

        self._last_epoch = record.epoch
        self._last_instruction_count = (
            record.instruction_count
        )
        self._emitted_count += 1
