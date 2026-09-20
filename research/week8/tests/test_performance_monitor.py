import pytest

from research.week7.retire_monitor import RetireEvent
from research.week7.timing_oracle_v1 import TimingExpectationV1
from research.week8.performance_monitor import (
    PerformanceMonitor,
    PerformanceMonitorProtocolError,
)


def timing(
    instruction_id,
    *,
    retire_cycle,
    accept_cycle=None,
):
    if accept_cycle is None:
        accept_cycle = retire_cycle - 3

    return TimingExpectationV1(
        instruction_id=instruction_id,
        pc=(instruction_id - 1) * 4,
        instruction=0x00000013,
        mnemonic="ADDI",
        accept_cycle=accept_cycle,
        stall_cycles_before_accept=0,
        retire_cycle=retire_cycle,
        forward_a=0,
        forward_b=0,
        source_a_producer_id=None,
        source_b_producer_id=None,
        source_a_cycle_age=None,
        source_b_cycle_age=None,
        redirect=False,
        redirect_bubbles=0,
    )


def retire(
    instruction_id,
    *,
    cycle,
    regwrite=True,
    rd=5,
    wdata=42,
):
    return RetireEvent(
        cycle=cycle,
        valid=True,
        regwrite=regwrite,
        rd=rd,
        wdata=wdata,
        instruction_id=instruction_id,
    )


def test_on_time_retire_passes():
    monitor = PerformanceMonitor(
        [timing(1, retire_cycle=4)]
    )

    result = monitor.observe_retire(
        retire(1, cycle=4)
    )

    assert result.passed
    assert result.delta_cycles == 0

    assert monitor.checked_count == 1
    assert monitor.passed_count == 1
    assert monitor.failed_count == 0
    assert monitor.complete
    assert monitor.overall_pass


def test_late_retire_fails():
    monitor = PerformanceMonitor(
        [timing(1, retire_cycle=4)]
    )

    result = monitor.observe_retire(
        retire(1, cycle=5)
    )

    assert not result.passed
    assert result.late
    assert not result.early
    assert result.delta_cycles == 1

    assert monitor.late_count == 1
    assert monitor.total_excess_cycles == 1
    assert monitor.max_excess_cycles == 1


def test_early_retire_fails():
    monitor = PerformanceMonitor(
        [timing(1, retire_cycle=4)]
    )

    result = monitor.observe_retire(
        retire(1, cycle=3)
    )

    assert not result.passed
    assert result.early
    assert not result.late
    assert result.delta_cycles == -1

    assert monitor.early_count == 1
    assert monitor.total_early_cycles == 1


def test_functional_fields_do_not_affect_performance():
    monitor = PerformanceMonitor(
        [timing(1, retire_cycle=4)]
    )

    # Deliberately nonsensical functional values.
    # Timing is still exactly correct.
    result = monitor.observe_retire(
        retire(
            1,
            cycle=4,
            regwrite=False,
            rd=31,
            wdata=0xDEADBEEF,
        )
    )

    assert result.passed
    assert monitor.overall_pass


def test_multiple_results_and_metrics():
    monitor = PerformanceMonitor(
        [
            timing(1, retire_cycle=4),
            timing(2, retire_cycle=5),
            timing(3, retire_cycle=6),
            timing(4, retire_cycle=7),
        ]
    )

    monitor.observe_retire(
        retire(1, cycle=4)
    )

    monitor.observe_retire(
        retire(2, cycle=6)
    )

    monitor.observe_retire(
        retire(3, cycle=8)
    )

    monitor.observe_retire(
        retire(4, cycle=6)
    )

    assert monitor.checked_count == 4
    assert monitor.passed_count == 1
    assert monitor.failed_count == 3

    assert monitor.late_count == 2
    assert monitor.early_count == 1

    assert monitor.total_excess_cycles == 3
    assert monitor.max_excess_cycles == 2
    assert monitor.total_early_cycles == 1

    assert monitor.failed_instruction_ids == (
        2,
        3,
        4,
    )

    assert monitor.complete
    assert not monitor.overall_pass


def test_incomplete_stream_is_not_overall_pass():
    monitor = PerformanceMonitor(
        [
            timing(1, retire_cycle=4),
            timing(2, retire_cycle=5),
        ]
    )

    result = monitor.observe_retire(
        retire(1, cycle=4)
    )

    assert result.passed

    assert not monitor.complete
    assert not monitor.overall_pass
    assert monitor.missing_instruction_ids == (2,)


def test_complete_exact_stream_passes():
    monitor = PerformanceMonitor(
        [
            timing(1, retire_cycle=4),
            timing(2, retire_cycle=5),
            timing(3, retire_cycle=6),
        ]
    )

    for instruction_id, cycle in (
        (1, 4),
        (2, 5),
        (3, 6),
    ):
        result = monitor.observe_retire(
            retire(
                instruction_id,
                cycle=cycle,
            )
        )

        assert result.passed

    assert monitor.complete
    assert monitor.overall_pass
    assert monitor.missing_instruction_ids == ()


def test_unknown_instruction_id_is_protocol_error():
    monitor = PerformanceMonitor(
        [timing(1, retire_cycle=4)]
    )

    with pytest.raises(
        PerformanceMonitorProtocolError,
        match="no matching timing expectation",
    ):
        monitor.observe_retire(
            retire(2, cycle=5)
        )


def test_duplicate_retire_is_protocol_error():
    monitor = PerformanceMonitor(
        [timing(1, retire_cycle=4)]
    )

    monitor.observe_retire(
        retire(1, cycle=4)
    )

    with pytest.raises(
        PerformanceMonitorProtocolError,
        match="duplicate performance observation",
    ):
        monitor.observe_retire(
            retire(1, cycle=4)
        )


def test_out_of_order_retire_is_protocol_error():
    monitor = PerformanceMonitor(
        [
            timing(1, retire_cycle=4),
            timing(2, retire_cycle=5),
        ]
    )

    with pytest.raises(
        PerformanceMonitorProtocolError,
        match="retire order violation",
    ):
        monitor.observe_retire(
            retire(2, cycle=5)
        )


def test_expected_stream_must_be_contiguous():
    with pytest.raises(
        ValueError,
        match="must be contiguous",
    ):
        PerformanceMonitor(
            [timing(2, retire_cycle=5)]
        )


def test_lateness_accumulates_after_excess_stall():
    monitor = PerformanceMonitor(
        [
            timing(1, retire_cycle=4),
            timing(2, retire_cycle=5),
            timing(3, retire_cycle=6),
        ]
    )

    # One extra pipeline delay from instruction 2 onward.
    r1 = monitor.observe_retire(
        retire(1, cycle=4)
    )
    r2 = monitor.observe_retire(
        retire(2, cycle=6)
    )
    r3 = monitor.observe_retire(
        retire(3, cycle=7)
    )

    assert r1.delta_cycles == 0
    assert r2.delta_cycles == 1
    assert r3.delta_cycles == 1

    assert monitor.total_excess_cycles == 2
    assert monitor.max_excess_cycles == 1
    assert not monitor.overall_pass
