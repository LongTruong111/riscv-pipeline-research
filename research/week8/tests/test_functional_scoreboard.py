import pytest

from research.week5.impl.commit_scoreboard import StoreObservation
from research.week6.expected_retire import ExpectedRetire
from research.week7.retire_monitor import RetireEvent
from research.week8.functional_scoreboard import (
    FunctionalScoreboard,
    FunctionalScoreboardProtocolError,
)


def expected(
    instruction_id,
    *,
    regwrite=True,
    rd=5,
    wdata=42,
    store_address=None,
    store_data=None,
    store_width_bytes=None,
):
    return ExpectedRetire(
        instruction_id=instruction_id,
        pc=(instruction_id - 1) * 4,
        instruction=0x00000013,
        next_pc=instruction_id * 4,
        regwrite=regwrite,
        rd=rd if regwrite else None,
        wdata=wdata if regwrite else None,
        store_address=store_address,
        store_data=store_data,
        store_width_bytes=store_width_bytes,
    )


def retire(
    instruction_id,
    *,
    regwrite=True,
    rd=5,
    wdata=42,
    cycle=100,
):
    return RetireEvent(
        cycle=cycle,
        valid=True,
        regwrite=regwrite,
        rd=rd,
        wdata=wdata,
        instruction_id=instruction_id,
    )


def store_observation(
    instruction_id,
    *,
    write_enable=False,
    address=0,
    data=0,
):
    return StoreObservation(
        instruction_index=instruction_id,
        write_enable=write_enable,
        address=address,
        data=data,
    )


def prepare(
    scoreboard,
    instruction_id,
    *,
    write_enable=False,
    address=0,
    data=0,
):
    scoreboard.observe_store_stage(
        store_observation(
            instruction_id,
            write_enable=write_enable,
            address=address,
            data=data,
        )
    )


def test_correct_register_write_passes():
    scoreboard = FunctionalScoreboard(
        [expected(1)]
    )

    prepare(scoreboard, 1)

    result = scoreboard.observe_retire(
        retire(1),
        observed_x0=0,
    )

    assert result.passed
    assert scoreboard.checked_count == 1
    assert scoreboard.passed_count == 1
    assert scoreboard.failed_count == 0
    assert scoreboard.complete


def test_wrong_wdata_fails_functionally():
    scoreboard = FunctionalScoreboard(
        [expected(1, wdata=42)]
    )

    prepare(scoreboard, 1)

    result = scoreboard.observe_retire(
        retire(
            1,
            wdata=99,
            # Cycle is irrelevant to functional verdict.
            cycle=999,
        ),
        observed_x0=0,
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {"write_data"}


def test_wrong_rd_fails():
    scoreboard = FunctionalScoreboard(
        [expected(1, rd=5)]
    )

    prepare(scoreboard, 1)

    result = scoreboard.observe_retire(
        retire(
            1,
            rd=6,
        ),
        observed_x0=0,
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {"write_rd"}


def test_missing_write_enable_fails():
    scoreboard = FunctionalScoreboard(
        [expected(1)]
    )

    prepare(scoreboard, 1)

    result = scoreboard.observe_retire(
        retire(
            1,
            regwrite=False,
        ),
        observed_x0=0,
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {"write_enable"}


def test_nonwriter_without_physical_write_passes():
    scoreboard = FunctionalScoreboard(
        [
            expected(
                1,
                regwrite=False,
            )
        ]
    )

    prepare(scoreboard, 1)

    result = scoreboard.observe_retire(
        retire(
            1,
            regwrite=False,
            rd=0,
            wdata=0,
        ),
        observed_x0=0,
    )

    assert result.passed


def test_unexpected_nonzero_register_write_fails():
    scoreboard = FunctionalScoreboard(
        [
            expected(
                1,
                regwrite=False,
            )
        ]
    )

    prepare(scoreboard, 1)

    result = scoreboard.observe_retire(
        retire(
            1,
            regwrite=True,
            rd=7,
            wdata=123,
        ),
        observed_x0=0,
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {
        "unexpected_architectural_write"
    }


def test_physical_x0_write_is_checked_via_x0_state():
    scoreboard = FunctionalScoreboard(
        [
            expected(
                1,
                regwrite=False,
            )
        ]
    )

    prepare(scoreboard, 1)

    result = scoreboard.observe_retire(
        retire(
            1,
            regwrite=True,
            rd=0,
            wdata=123,
        ),
        observed_x0=0,
    )

    # Physical rd=x0 write alone is not an architectural write failure.
    assert result.passed


def test_x0_corruption_fails():
    scoreboard = FunctionalScoreboard(
        [
            expected(
                1,
                regwrite=False,
            )
        ]
    )

    prepare(scoreboard, 1)

    result = scoreboard.observe_retire(
        retire(
            1,
            regwrite=True,
            rd=0,
            wdata=7,
        ),
        observed_x0=7,
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {"architectural_x0"}


def test_correct_store_passes():
    scoreboard = FunctionalScoreboard(
        [
            expected(
                1,
                regwrite=False,
                store_address=100,
                store_data=55,
                store_width_bytes=4,
            )
        ]
    )

    prepare(
        scoreboard,
        1,
        write_enable=True,
        address=100,
        data=55,
    )

    result = scoreboard.observe_retire(
        retire(
            1,
            regwrite=False,
            rd=0,
            wdata=0,
        ),
        observed_x0=0,
    )

    assert result.passed


def test_wrong_store_data_fails():
    scoreboard = FunctionalScoreboard(
        [
            expected(
                1,
                regwrite=False,
                store_address=100,
                store_data=55,
                store_width_bytes=4,
            )
        ]
    )

    prepare(
        scoreboard,
        1,
        write_enable=True,
        address=100,
        data=99,
    )

    result = scoreboard.observe_retire(
        retire(
            1,
            regwrite=False,
        ),
        observed_x0=0,
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {"store_data"}


def test_unexpected_store_fails():
    scoreboard = FunctionalScoreboard(
        [
            expected(
                1,
                regwrite=False,
            )
        ]
    )

    prepare(
        scoreboard,
        1,
        write_enable=True,
        address=0,
        data=123,
    )

    result = scoreboard.observe_retire(
        retire(
            1,
            regwrite=False,
        ),
        observed_x0=0,
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {"unexpected_store"}


def test_expected_store_outside_dut_range_fails_without_truncation():
    scoreboard = FunctionalScoreboard(
        [
            expected(
                1,
                regwrite=False,
                store_address=0x400,
                store_data=55,
                store_width_bytes=4,
            )
        ]
    )

    prepare(
        scoreboard,
        1,
        write_enable=True,
        address=0,
        data=55,
    )

    result = scoreboard.observe_retire(
        retire(
            1,
            regwrite=False,
        ),
        observed_x0=0,
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {
        "store_address_in_dut_range"
    }


def test_missing_store_stage_observation_is_protocol_error():
    scoreboard = FunctionalScoreboard(
        [expected(1)]
    )

    with pytest.raises(
        FunctionalScoreboardProtocolError,
        match="missing C-stage store observation",
    ):
        scoreboard.observe_retire(
            retire(1),
            observed_x0=0,
        )


def test_duplicate_store_stage_observation_is_protocol_error():
    scoreboard = FunctionalScoreboard(
        [expected(1)]
    )

    prepare(scoreboard, 1)

    with pytest.raises(
        FunctionalScoreboardProtocolError,
        match="duplicate store-stage observation",
    ):
        prepare(scoreboard, 1)


def test_duplicate_retire_is_protocol_error():
    scoreboard = FunctionalScoreboard(
        [expected(1)]
    )

    prepare(scoreboard, 1)

    scoreboard.observe_retire(
        retire(1),
        observed_x0=0,
    )

    # A second store observation is necessary only to reach the
    # duplicate-retire guard rather than the missing-store guard.
    prepare(scoreboard, 1)

    with pytest.raises(
        FunctionalScoreboardProtocolError,
        match="duplicate functional retirement",
    ):
        scoreboard.observe_retire(
            retire(1),
            observed_x0=0,
        )


def test_unknown_instruction_id_is_protocol_error():
    scoreboard = FunctionalScoreboard(
        [expected(1)]
    )

    with pytest.raises(
        FunctionalScoreboardProtocolError,
        match="no matching ExpectedRetire",
    ):
        prepare(scoreboard, 2)


def test_expected_stream_must_be_contiguous():
    with pytest.raises(
        ValueError,
        match="must be contiguous",
    ):
        FunctionalScoreboard(
            [expected(2)]
        )
