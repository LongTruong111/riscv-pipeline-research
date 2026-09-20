import math

import pytest

from research.week9.benchmark.metrics import (
    BenchmarkSample,
    BenchmarkTracker,
    parse_proc_status_rss_kib,
)


def sample(
    *,
    cycle,
    instructions,
    wall_ns,
    rss_kib,
    pending=0,
    performance=0,
    timing=0,
    steps=0,
    events=0,
):
    return BenchmarkSample(
        cycle=cycle,
        executed_instructions=instructions,
        wall_ns=wall_ns,
        rss_kib=rss_kib,
        pending_hits=pending,
        retained_performance=performance,
        timing_observations=timing,
        architectural_steps=steps,
        recent_events=events,
    )


def test_parse_proc_status_rss():
    text = (
        "Name:\tpython3\n"
        "VmSize:\t100000 kB\n"
        "VmRSS:\t12345 kB\n"
        "Threads:\t1\n"
    )

    assert parse_proc_status_rss_kib(text) == 12345


def test_parse_proc_status_rejects_missing_rss():
    with pytest.raises(ValueError):
        parse_proc_status_rss_kib(
            "Name:\tpython3\n"
        )


def test_sample_rejects_negative_field():
    with pytest.raises(ValueError):
        sample(
            cycle=0,
            instructions=0,
            wall_ns=0,
            rss_kib=-1,
        )


def test_summary_rates_and_rss_deltas():
    tracker = BenchmarkTracker()

    tracker.record_start(
        sample(
            cycle=0,
            instructions=0,
            wall_ns=1_000_000_000,
            rss_kib=10_000,
        )
    )

    tracker.record_mid(
        sample(
            cycle=50_000,
            instructions=40_000,
            wall_ns=6_000_000_000,
            rss_kib=10_100,
            pending=2,
            performance=1,
            timing=3,
            steps=3,
            events=4,
        )
    )

    tracker.record_end(
        sample(
            cycle=100_000,
            instructions=80_000,
            wall_ns=11_000_000_000,
            rss_kib=10_120,
        )
    )

    result = tracker.summary()

    assert result.cycles == 100_000
    assert result.executed_instructions == 80_000
    assert result.wall_seconds == 10.0

    assert result.cycles_per_second == 10_000.0
    assert result.instructions_per_second == 8_000.0

    assert (
        result.first_half_cycles_per_second
        == 10_000.0
    )

    assert (
        result.second_half_cycles_per_second
        == 10_000.0
    )

    assert result.throughput_degradation_pct == 0.0

    assert result.rss_mid_delta_kib == 100
    assert result.rss_end_delta_kib == 120

    assert result.max_pending_hits == 2
    assert result.max_retained_performance == 1
    assert result.max_timing_observations == 3
    assert result.max_architectural_steps == 3
    assert result.max_recent_events == 4

    assert (
        result.estimated_100k_instruction_seconds
        == 12.5
    )


def test_second_half_slowdown_is_reported():
    tracker = BenchmarkTracker()

    tracker.record_start(
        sample(
            cycle=0,
            instructions=0,
            wall_ns=0,
            rss_kib=100,
        )
    )

    tracker.record_mid(
        sample(
            cycle=50,
            instructions=50,
            wall_ns=1_000_000_000,
            rss_kib=100,
        )
    )

    tracker.record_end(
        sample(
            cycle=100,
            instructions=100,
            wall_ns=3_000_000_000,
            rss_kib=100,
        )
    )

    result = tracker.summary()

    assert (
        result.first_half_cycles_per_second
        == 50.0
    )

    assert (
        result.second_half_cycles_per_second
        == 25.0
    )

    assert result.throughput_degradation_pct == 50.0


def test_tracker_retains_only_three_lifecycle_samples():
    tracker = BenchmarkTracker()

    tracker.record_start(
        sample(
            cycle=0,
            instructions=0,
            wall_ns=0,
            rss_kib=100,
        )
    )

    for cycle in range(1, 10_000):
        tracker.observe_state(
            sample(
                cycle=cycle,
                instructions=cycle,
                wall_ns=cycle,
                rss_kib=100,
                pending=cycle % 4,
                performance=cycle % 2,
                timing=3,
                steps=3,
                events=4,
            )
        )

    tracker.record_mid(
        sample(
            cycle=10_000,
            instructions=10_000,
            wall_ns=10_000,
            rss_kib=100,
        )
    )

    tracker.record_end(
        sample(
            cycle=20_000,
            instructions=20_000,
            wall_ns=20_000,
            rss_kib=100,
        )
    )

    result = tracker.summary()

    assert result.max_pending_hits == 3
    assert result.max_retained_performance == 1
    assert result.max_timing_observations == 3
    assert result.max_architectural_steps == 3
    assert result.max_recent_events == 4

    assert tracker._start is not None
    assert tracker._mid is not None
    assert tracker._end is not None


def test_zero_instruction_throughput_gives_infinite_estimate():
    tracker = BenchmarkTracker()

    tracker.record_start(
        sample(
            cycle=0,
            instructions=0,
            wall_ns=0,
            rss_kib=100,
        )
    )

    tracker.record_mid(
        sample(
            cycle=50,
            instructions=0,
            wall_ns=1_000_000_000,
            rss_kib=100,
        )
    )

    tracker.record_end(
        sample(
            cycle=100,
            instructions=0,
            wall_ns=2_000_000_000,
            rss_kib=100,
        )
    )

    result = tracker.summary()

    assert result.instructions_per_second == 0.0
    assert math.isinf(
        result.estimated_100k_instruction_seconds
    )
