import pytest

from research.week5.impl.directed_cases import (
    DIRECTED_CASES,
)
from research.week7.retire_monitor import (
    RetireEvent,
)
from research.week7.timing_oracle_v1 import (
    build_timing_schedule_v1,
)
from research.week8.performance_monitor import (
    PerformanceMonitor,
)
from research.week9.benchmark.streaming_timing import (
    StreamingPerformanceMonitor,
    StreamingTimingOracleV1,
)


def build_program(words):
    return {
        index * 4: instruction
        for index, instruction
        in enumerate(words)
    }


@pytest.mark.parametrize(
    "case_id",
    sorted(DIRECTED_CASES),
)
def test_streaming_timing_matches_frozen_oracle(
    case_id,
):
    case = DIRECTED_CASES[case_id]

    program = build_program(case.words)

    frozen = build_timing_schedule_v1(
        program
    )

    streaming = StreamingTimingOracleV1(
        program
    )

    observed = tuple(
        streaming.next_expectation()
        for _ in range(
            frozen.instruction_count
        )
    )

    assert observed == frozen.expectations
    assert (
        streaming.generated_count
        == frozen.instruction_count
    )
    assert streaming.writer_count <= 31


@pytest.mark.parametrize(
    "case_id",
    sorted(DIRECTED_CASES),
)
def test_streaming_performance_matches_frozen(
    case_id,
):
    case = DIRECTED_CASES[case_id]

    frozen_schedule = (
        build_timing_schedule_v1(
            build_program(case.words)
        )
    )

    frozen = PerformanceMonitor(
        frozen_schedule.expectations
    )

    streaming = StreamingPerformanceMonitor()

    for expectation in (
        frozen_schedule.expectations
    ):
        streaming.register_expectation(
            expectation
        )

        retire = RetireEvent(
            cycle=expectation.retire_cycle,
            valid=True,
            regwrite=False,
            rd=0,
            wdata=0,
            instruction_id=(
                expectation.instruction_id
            ),
        )

        frozen_result = (
            frozen.observe_retire(retire)
        )

        streaming_result = (
            streaming.observe_retire(
                retire
            )
        )

        assert (
            streaming_result
            == frozen_result
        )

    assert streaming.complete
    assert streaming.overall_pass
    assert streaming.pending_count == 0


def test_streaming_performance_preserves_late_delta():
    case = DIRECTED_CASES["T01"]

    schedule = build_timing_schedule_v1(
        build_program(case.words)
    )

    expectation = schedule.expectations[0]

    frozen = PerformanceMonitor(
        (expectation,)
    )

    streaming = StreamingPerformanceMonitor()

    streaming.register_expectation(
        expectation
    )

    retire = RetireEvent(
        cycle=expectation.retire_cycle + 1,
        valid=True,
        regwrite=False,
        rd=0,
        wdata=0,
        instruction_id=1,
    )

    assert (
        streaming.observe_retire(retire)
        == frozen.observe_retire(retire)
    )

    assert streaming.failed_count == 1
    assert streaming.late_count == 1
    assert streaming.total_excess_cycles == 1
    assert streaming.max_excess_cycles == 1
