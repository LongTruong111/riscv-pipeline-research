"""Week 9 Verification Economics telemetry.

Measures non-overlapping wall-time phases using a monotonic clock.

Tracked phases:
- generation
- simulation
- coverage
- adaptation

Total wall time is measured independently and may exceed the sum of
instrumented phases because orchestration / I/O / bookkeeping time may exist.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import time
from typing import Callable, Dict, Iterator, Optional


class TelemetryProtocolError(RuntimeError):
    """Raised when telemetry session/phase ordering is invalid."""


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    wall_generation_ns: int
    wall_simulation_ns: int
    wall_coverage_ns: int
    wall_adaptation_ns: int
    wall_total_ns: int

    @property
    def wall_generation(self) -> float:
        return self.wall_generation_ns / 1_000_000_000

    @property
    def wall_simulation(self) -> float:
        return self.wall_simulation_ns / 1_000_000_000

    @property
    def wall_coverage(self) -> float:
        return self.wall_coverage_ns / 1_000_000_000

    @property
    def wall_adaptation(self) -> float:
        return self.wall_adaptation_ns / 1_000_000_000

    @property
    def wall_total(self) -> float:
        return self.wall_total_ns / 1_000_000_000


class TelemetryAccumulator:
    """Accumulate non-overlapping Verification Economics wall-time phases."""

    _VALID_PHASES = (
        "generation",
        "simulation",
        "coverage",
        "adaptation",
    )

    def __init__(
        self,
        *,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self._clock_ns = clock_ns

        self._phase_ns: Dict[str, int] = {
            phase: 0
            for phase in self._VALID_PHASES
        }

        self._started = False
        self._stopped = False

        self._start_ns: Optional[int] = None
        self._stop_ns: Optional[int] = None

        self._active_phase: Optional[str] = None

    def start(self) -> None:
        if self._started and not self._stopped:
            raise TelemetryProtocolError(
                "telemetry session is already running"
            )

        if self._started and self._stopped:
            raise TelemetryProtocolError(
                "telemetry accumulator cannot be restarted"
            )

        self._start_ns = self._clock_ns()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            raise TelemetryProtocolError(
                "telemetry session has not started"
            )

        if self._stopped:
            raise TelemetryProtocolError(
                "telemetry session is already stopped"
            )

        if self._active_phase is not None:
            raise TelemetryProtocolError(
                "cannot stop telemetry while a phase is active"
            )

        self._stop_ns = self._clock_ns()
        self._stopped = True

    @contextmanager
    def phase(
        self,
        name: str,
    ) -> Iterator[None]:
        if name not in self._VALID_PHASES:
            raise ValueError(
                f"unknown telemetry phase: {name!r}"
            )

        if not self._started:
            raise TelemetryProtocolError(
                "telemetry session has not started"
            )

        if self._stopped:
            raise TelemetryProtocolError(
                "telemetry session is already stopped"
            )

        if self._active_phase is not None:
            raise TelemetryProtocolError(
                "nested/overlapping telemetry phases are not allowed"
            )

        self._active_phase = name
        start_ns = self._clock_ns()

        try:
            yield
        finally:
            end_ns = self._clock_ns()
            self._phase_ns[name] += end_ns - start_ns
            self._active_phase = None

    def snapshot(self) -> TelemetrySnapshot:
        if not self._started:
            raise TelemetryProtocolError(
                "telemetry session has not started"
            )

        if not self._stopped:
            raise TelemetryProtocolError(
                "telemetry session must be stopped before snapshot"
            )

        assert self._start_ns is not None
        assert self._stop_ns is not None

        return TelemetrySnapshot(
            wall_generation_ns=self._phase_ns["generation"],
            wall_simulation_ns=self._phase_ns["simulation"],
            wall_coverage_ns=self._phase_ns["coverage"],
            wall_adaptation_ns=self._phase_ns["adaptation"],
            wall_total_ns=self._stop_ns - self._start_ns,
        )

