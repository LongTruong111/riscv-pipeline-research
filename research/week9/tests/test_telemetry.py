import pytest

from research.week9.telemetry import (
    TelemetryAccumulator,
    TelemetryProtocolError,
)


class FakeClock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def advance(self, ns):
        self.now += ns


def test_phase_accumulates_wall_time():
    clock = FakeClock()
    telemetry = TelemetryAccumulator(clock_ns=clock)

    telemetry.start()

    with telemetry.phase("generation"):
        clock.advance(100)

    with telemetry.phase("simulation"):
        clock.advance(200)

    with telemetry.phase("coverage"):
        clock.advance(50)

    with telemetry.phase("adaptation"):
        clock.advance(25)

    clock.advance(10)

    telemetry.stop()

    snapshot = telemetry.snapshot()

    assert snapshot.wall_generation_ns == 100
    assert snapshot.wall_simulation_ns == 200
    assert snapshot.wall_coverage_ns == 50
    assert snapshot.wall_adaptation_ns == 25

    # Total includes time outside explicitly instrumented phases.
    assert snapshot.wall_total_ns == 385


def test_same_phase_can_accumulate_multiple_intervals():
    clock = FakeClock()
    telemetry = TelemetryAccumulator(clock_ns=clock)

    telemetry.start()

    with telemetry.phase("coverage"):
        clock.advance(10)

    with telemetry.phase("coverage"):
        clock.advance(15)

    telemetry.stop()

    assert telemetry.snapshot().wall_coverage_ns == 25


def test_total_is_not_forced_to_equal_phase_sum():
    clock = FakeClock()
    telemetry = TelemetryAccumulator(clock_ns=clock)

    telemetry.start()

    clock.advance(20)

    with telemetry.phase("simulation"):
        clock.advance(100)

    clock.advance(30)

    telemetry.stop()

    snapshot = telemetry.snapshot()

    assert snapshot.wall_simulation_ns == 100
    assert snapshot.wall_total_ns == 150


def test_nested_phase_is_rejected():
    clock = FakeClock()
    telemetry = TelemetryAccumulator(clock_ns=clock)

    telemetry.start()

    with pytest.raises(TelemetryProtocolError):
        with telemetry.phase("generation"):
            clock.advance(10)

            with telemetry.phase("coverage"):
                clock.advance(5)


def test_unknown_phase_is_rejected():
    clock = FakeClock()
    telemetry = TelemetryAccumulator(clock_ns=clock)

    telemetry.start()

    with pytest.raises(ValueError):
        with telemetry.phase("unknown"):
            pass


def test_phase_requires_started_session():
    clock = FakeClock()
    telemetry = TelemetryAccumulator(clock_ns=clock)

    with pytest.raises(TelemetryProtocolError):
        with telemetry.phase("simulation"):
            pass


def test_double_start_is_rejected():
    clock = FakeClock()
    telemetry = TelemetryAccumulator(clock_ns=clock)

    telemetry.start()

    with pytest.raises(TelemetryProtocolError):
        telemetry.start()


def test_stop_without_start_is_rejected():
    clock = FakeClock()
    telemetry = TelemetryAccumulator(clock_ns=clock)

    with pytest.raises(TelemetryProtocolError):
        telemetry.stop()


def test_stop_with_active_phase_is_rejected():
    clock = FakeClock()
    telemetry = TelemetryAccumulator(clock_ns=clock)

    telemetry.start()

    ctx = telemetry.phase("simulation")
    ctx.__enter__()

    with pytest.raises(TelemetryProtocolError):
        telemetry.stop()

    ctx.__exit__(None, None, None)


def test_snapshot_requires_stopped_session():
    clock = FakeClock()
    telemetry = TelemetryAccumulator(clock_ns=clock)

    telemetry.start()

    with pytest.raises(TelemetryProtocolError):
        telemetry.snapshot()


def test_snapshot_exposes_seconds():
    clock = FakeClock()
    telemetry = TelemetryAccumulator(clock_ns=clock)

    telemetry.start()

    with telemetry.phase("generation"):
        clock.advance(1_500_000_000)

    telemetry.stop()

    snapshot = telemetry.snapshot()

    assert snapshot.wall_generation == pytest.approx(1.5)
    assert snapshot.wall_total == pytest.approx(1.5)
