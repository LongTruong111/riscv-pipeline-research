import pytest

from research.week5.impl.commit_scoreboard import StoreObservation
from research.week6.expected_retire import ExpectedRetire
from research.week7.retire_monitor import RetireEvent
from research.week7.timing_oracle_v1 import TimingExpectationV1

from research.week8.cross_verdict import (
    CrossVerdictClass,
    CrossVerdictProtocolError,
    combine_verdicts,
)
from research.week8.functional_scoreboard import FunctionalScoreboard
from research.week8.performance_monitor import PerformanceMonitor


EXPECTED_WDATA = 42
EXPECTED_RETIRE_CYCLE = 4


def expected_retire():
    return ExpectedRetire(
        instruction_id=1,
        pc=0,
        instruction=0x02A00293,
        next_pc=4,
        regwrite=True,
        rd=5,
        wdata=EXPECTED_WDATA,
        store_address=None,
        store_data=None,
        store_width_bytes=None,
    )


def timing_expectation():
    return TimingExpectationV1(
        instruction_id=1,
        pc=0,
        instruction=0x02A00293,
        mnemonic="ADDI",
        accept_cycle=1,
        stall_cycles_before_accept=0,
        retire_cycle=EXPECTED_RETIRE_CYCLE,
        forward_a=0,
        forward_b=0,
        source_a_producer_id=None,
        source_b_producer_id=None,
        source_a_cycle_age=None,
        source_b_cycle_age=None,
        redirect=False,
        redirect_bubbles=0,
    )


def observed_retire(
    *,
    wdata=EXPECTED_WDATA,
    cycle=EXPECTED_RETIRE_CYCLE,
):
    return RetireEvent(
        cycle=cycle,
        valid=True,
        regwrite=True,
        rd=5,
        wdata=wdata,
        instruction_id=1,
    )


def evaluate(
    *,
    wdata=EXPECTED_WDATA,
    cycle=EXPECTED_RETIRE_CYCLE,
):
    functional = FunctionalScoreboard(
        [expected_retire()]
    )

    performance = PerformanceMonitor(
        [timing_expectation()]
    )

    # Every verification-valid C-stage instruction receives a
    # store-stage observation. This ADDI is correctly not a store.
    functional.observe_store_stage(
        StoreObservation(
            instruction_index=1,
            write_enable=False,
            address=0,
            data=0,
        )
    )

    retire = observed_retire(
        wdata=wdata,
        cycle=cycle,
    )

    functional_result = functional.observe_retire(
        retire,
        observed_x0=0,
    )

    performance_result = performance.observe_retire(
        retire
    )

    return combine_verdicts(
        functional_result,
        performance_result,
    )


def test_correct_on_time():
    verdict = evaluate()

    assert verdict.functional_pass
    assert verdict.performance_pass
    assert verdict.overall_pass

    assert (
        verdict.classification
        == CrossVerdictClass.CORRECT_ON_TIME
    )

    assert verdict.functional_failed_checks == ()
    assert verdict.timing_delta_cycles == 0


def test_wrong_wdata_but_on_time_is_functional_only_fail():
    verdict = evaluate(
        wdata=99,
        cycle=EXPECTED_RETIRE_CYCLE,
    )

    assert not verdict.functional_pass
    assert verdict.performance_pass
    assert not verdict.overall_pass

    assert (
        verdict.classification
        == CrossVerdictClass.FUNCTIONAL_ONLY_FAIL
    )

    assert verdict.functional_failed_checks == (
        "write_data",
    )

    assert verdict.timing_delta_cycles == 0


def test_correct_wdata_but_late_is_performance_only_fail():
    verdict = evaluate(
        wdata=EXPECTED_WDATA,
        cycle=EXPECTED_RETIRE_CYCLE + 1,
    )

    assert verdict.functional_pass
    assert not verdict.performance_pass
    assert not verdict.overall_pass

    assert (
        verdict.classification
        == CrossVerdictClass.PERFORMANCE_ONLY_FAIL
    )

    assert verdict.functional_failed_checks == ()
    assert verdict.timing_delta_cycles == 1


def test_wrong_wdata_and_late_fails_both():
    verdict = evaluate(
        wdata=99,
        cycle=EXPECTED_RETIRE_CYCLE + 2,
    )

    assert not verdict.functional_pass
    assert not verdict.performance_pass
    assert not verdict.overall_pass

    assert (
        verdict.classification
        == (
            CrossVerdictClass
            .FUNCTIONAL_AND_PERFORMANCE_FAIL
        )
    )

    assert verdict.functional_failed_checks == (
        "write_data",
    )

    assert verdict.timing_delta_cycles == 2


def test_early_retire_is_performance_only_when_data_is_correct():
    verdict = evaluate(
        wdata=EXPECTED_WDATA,
        cycle=EXPECTED_RETIRE_CYCLE - 1,
    )

    assert verdict.functional_pass
    assert not verdict.performance_pass

    assert (
        verdict.classification
        == CrossVerdictClass.PERFORMANCE_ONLY_FAIL
    )

    assert verdict.timing_delta_cycles == -1


def test_functional_failure_does_not_change_timing_delta():
    on_time = evaluate(
        wdata=99,
        cycle=EXPECTED_RETIRE_CYCLE,
    )

    late = evaluate(
        wdata=99,
        cycle=EXPECTED_RETIRE_CYCLE + 3,
    )

    assert on_time.functional_failed_checks == (
        "write_data",
    )

    assert late.functional_failed_checks == (
        "write_data",
    )

    assert on_time.timing_delta_cycles == 0
    assert late.timing_delta_cycles == 3


def test_instruction_id_mismatch_is_protocol_error():
    functional = FunctionalScoreboard(
        [expected_retire()]
    )

    functional.observe_store_stage(
        StoreObservation(
            instruction_index=1,
            write_enable=False,
            address=0,
            data=0,
        )
    )

    functional_result = functional.observe_retire(
        observed_retire(),
        observed_x0=0,
    )

    # Construct a timing result for another instruction only to
    # verify correlation protection.
    from research.week8.performance_monitor import PerformanceResult

    performance_result = PerformanceResult(
        instruction_id=2,
        expected_retire_cycle=5,
        observed_retire_cycle=5,
        delta_cycles=0,
    )

    with pytest.raises(
        CrossVerdictProtocolError,
        match="instruction_id mismatch",
    ):
        combine_verdicts(
            functional_result,
            performance_result,
        )
