import pytest

from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week5.impl.commit_scoreboard import (
    StoreObservation,
)
from research.week5.impl.directed_cases import (
    DIRECTED_CASES,
)
from research.week6.expected_retire import (
    ExpectedRetire,
)
from research.week7.retire_monitor import (
    RetireEvent,
)
from research.week7.timing_oracle_v1 import (
    _decode_checked,
    _execution_event,
    build_timing_schedule_v1,
)
from research.week8.functional_scoreboard import (
    FunctionalScoreboard,
)
from research.week9.benchmark.streaming_functional import (
    StreamingFunctionalScoreboard,
)


def build_program(words):
    return {
        index * 4: instruction
        for index, instruction
        in enumerate(words)
    }


def build_expected_retires(case_id):
    case = DIRECTED_CASES[case_id]

    schedule = build_timing_schedule_v1(
        build_program(case.words)
    )

    model = RV32ArchitecturalModel()

    expected = []

    for timing in schedule.expectations:
        decoded = _decode_checked(
            timing.instruction
        )

        event = _execution_event(
            instruction_id=(
                timing.instruction_id
            ),
            cycle=timing.accept_cycle,
            pc=timing.pc,
            instruction=(
                timing.instruction
            ),
            decoded=decoded,
        )

        step = model.step(event)

        assert step.pc_match

        expected.append(
            ExpectedRetire
            .from_architectural_step(
                step
            )
        )

    return (
        tuple(expected),
        schedule,
    )


def matching_store_observation(expected):
    if expected.store_address is None:
        return StoreObservation(
            instruction_index=(
                expected.instruction_id
            ),
            write_enable=False,
            address=0,
            data=0,
            instruction=expected.instruction,
        )

    assert expected.store_address <= 0x1FF

    assert expected.store_data is not None

    return StoreObservation(
        instruction_index=(
            expected.instruction_id
        ),
        write_enable=True,
        address=expected.store_address,
        data=expected.store_data,
        instruction=expected.instruction,
    )


def matching_retire(expected, timing):
    return RetireEvent(
        cycle=timing.retire_cycle,
        valid=True,
        regwrite=expected.regwrite,
        rd=(
            0
            if expected.rd is None
            else expected.rd
        ),
        wdata=(
            0
            if expected.wdata is None
            else expected.wdata
        ),
        instruction_id=(
            expected.instruction_id
        ),
    )


@pytest.mark.parametrize(
    "case_id",
    sorted(DIRECTED_CASES),
)
def test_streaming_functional_matches_frozen(
    case_id,
):
    expected_retires, schedule = (
        build_expected_retires(
            case_id
        )
    )

    frozen = FunctionalScoreboard(
        expected_retires
    )

    streaming = (
        StreamingFunctionalScoreboard()
    )

    max_pending_expected = 0
    max_pending_store = 0

    for expected, timing in zip(
        expected_retires,
        schedule.expectations,
        strict=True,
    ):
        streaming.register_expected(
            expected
        )

        max_pending_expected = max(
            max_pending_expected,
            streaming.pending_expected_count,
        )

        store = (
            matching_store_observation(
                expected
            )
        )

        frozen.observe_store_stage(
            store
        )

        streaming.observe_store_stage(
            store
        )

        max_pending_store = max(
            max_pending_store,
            streaming.pending_store_count,
        )

        retire = matching_retire(
            expected,
            timing,
        )

        frozen_result = (
            frozen.observe_retire(
                retire,
                observed_x0=0,
            )
        )

        streaming_result = (
            streaming.observe_retire(
                retire,
                observed_x0=0,
            )
        )

        assert (
            streaming_result
            == frozen_result
        )

    assert streaming.complete
    assert streaming.overall_pass

    assert (
        streaming.checked_count
        == len(expected_retires)
    )

    # Test drives one instruction at a time;
    # retained state must not accumulate.
    assert max_pending_expected == 1
    assert max_pending_store == 1

    assert (
        streaming.pending_expected_count
        == 0
    )

    assert streaming.pending_store_count == 0


def test_streaming_functional_preserves_write_data_failure():
    expected_retires, schedule = (
        build_expected_retires("T01")
    )

    expected = next(
        item
        for item in expected_retires
        if item.regwrite
    )

    timing = next(
        item
        for item in schedule.expectations
        if (
            item.instruction_id
            == expected.instruction_id
        )
    )

    frozen = FunctionalScoreboard(
        expected_retires
    )

    streaming = (
        StreamingFunctionalScoreboard()
    )

    # Advance prior instructions identically.
    for prior, prior_timing in zip(
        expected_retires,
        schedule.expectations,
        strict=True,
    ):
        streaming.register_expected(
            prior
        )

        store = (
            matching_store_observation(
                prior
            )
        )

        frozen.observe_store_stage(
            store
        )

        streaming.observe_store_stage(
            store
        )

        retire = matching_retire(
            prior,
            prior_timing,
        )

        if (
            prior.instruction_id
            == expected.instruction_id
        ):
            retire = RetireEvent(
                cycle=retire.cycle,
                valid=True,
                regwrite=retire.regwrite,
                rd=retire.rd,
                wdata=(
                    retire.wdata + 1
                ) & 0xFFFFFFFF,
                instruction_id=(
                    retire.instruction_id
                ),
            )

            frozen_result = (
                frozen.observe_retire(
                    retire,
                    observed_x0=0,
                )
            )

            streaming_result = (
                streaming.observe_retire(
                    retire,
                    observed_x0=0,
                )
            )

            assert (
                streaming_result
                == frozen_result
            )

            assert not streaming_result.passed

            assert any(
                check.name == "write_data"
                and not check.passed
                for check
                in streaming_result.checks
            )

            return

        frozen.observe_retire(
            retire,
            observed_x0=0,
        )

        streaming.observe_retire(
            retire,
            observed_x0=0,
        )

    raise AssertionError(
        "test case contained no register write"
    )
