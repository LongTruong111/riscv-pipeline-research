import pytest

from research.week7.retire_monitor import (
    RetireMonitor,
    RetireProtocolError,
    RetireTag,
)


def tag(instruction_id):
    return RetireTag(
        instruction_id=instruction_id,
        pc=(instruction_id - 1) * 4,
        instruction=0x00000013,
    )


def observe_idle(monitor, cycle):
    return monitor.observe_falling_edge(
        cycle=cycle,
        regwrite=False,
        rd=0,
        wdata=0,
    )


def test_empty_pipeline_does_not_retire():
    monitor = RetireMonitor()

    assert observe_idle(monitor, 1) is None
    assert monitor.retired_count == 0


def test_single_instruction_retires_once():
    monitor = RetireMonitor()

    # Accepted into B.
    monitor.advance_pipeline(tag(1))
    assert observe_idle(monitor, 1) is None

    # B -> C.
    monitor.advance_pipeline(None)
    assert observe_idle(monitor, 2) is None

    # C -> D.
    monitor.advance_pipeline(None)

    event = monitor.observe_falling_edge(
        cycle=3,
        regwrite=True,
        rd=5,
        wdata=42,
    )

    assert event is not None
    assert event.valid
    assert event.instruction_id == 1
    assert event.cycle == 3
    assert event.regwrite
    assert event.rd == 5
    assert event.wdata == 42
    assert monitor.retired_count == 1

    # Same D tag cannot retire twice.
    assert observe_idle(monitor, 3) is None
    assert monitor.retired_count == 1


def test_back_to_back_instructions_retire_in_order():
    monitor = RetireMonitor()

    monitor.advance_pipeline(tag(1))
    assert observe_idle(monitor, 1) is None

    monitor.advance_pipeline(tag(2))
    assert observe_idle(monitor, 2) is None

    monitor.advance_pipeline(tag(3))

    e1 = monitor.observe_falling_edge(
        cycle=3,
        regwrite=True,
        rd=1,
        wdata=11,
    )

    assert e1.instruction_id == 1

    monitor.advance_pipeline(None)

    e2 = monitor.observe_falling_edge(
        cycle=4,
        regwrite=True,
        rd=2,
        wdata=22,
    )

    assert e2.instruction_id == 2

    monitor.advance_pipeline(None)

    e3 = monitor.observe_falling_edge(
        cycle=5,
        regwrite=True,
        rd=3,
        wdata=33,
    )

    assert e3.instruction_id == 3
    assert monitor.retired_count == 3


def test_stall_bubble_does_not_duplicate_retirement():
    monitor = RetireMonitor()

    # I1 accepted.
    monitor.advance_pipeline(tag(1))
    assert observe_idle(monitor, 1) is None

    # Stall: no new accepted instruction.
    monitor.advance_pipeline(None)
    assert observe_idle(monitor, 2) is None

    # Consumer accepted after stall.
    monitor.advance_pipeline(tag(2))

    e1 = monitor.observe_falling_edge(
        cycle=3,
        regwrite=True,
        rd=5,
        wdata=10,
    )

    assert e1.instruction_id == 1

    monitor.advance_pipeline(None)
    assert observe_idle(monitor, 4) is None

    monitor.advance_pipeline(None)

    e2 = monitor.observe_falling_edge(
        cycle=5,
        regwrite=True,
        rd=6,
        wdata=11,
    )

    assert e2.instruction_id == 2
    assert monitor.retired_count == 2


def test_flush_bubble_never_retires():
    monitor = RetireMonitor()

    # Executed redirect instruction.
    monitor.advance_pipeline(tag(1))
    assert observe_idle(monitor, 1) is None

    # Flush cycle: wrong-path IF/ID instruction is NOT admitted.
    monitor.advance_pipeline(None)
    assert observe_idle(monitor, 2) is None

    monitor.advance_pipeline(None)

    event = monitor.observe_falling_edge(
        cycle=3,
        regwrite=False,
        rd=0,
        wdata=0,
    )

    assert event is not None
    assert event.instruction_id == 1

    # No wrong-path instruction follows it.
    monitor.advance_pipeline(None)
    assert observe_idle(monitor, 4) is None

    assert monitor.retired_count == 1


def test_non_regwrite_instruction_is_still_valid_retirement():
    monitor = RetireMonitor()

    monitor.advance_pipeline(tag(1))
    monitor.advance_pipeline(None)
    monitor.advance_pipeline(None)

    event = monitor.observe_falling_edge(
        cycle=3,
        regwrite=False,
        rd=0,
        wdata=0,
    )

    assert event is not None
    assert event.valid
    assert not event.regwrite
    assert event.instruction_id == 1


def test_regwrite_without_valid_tag_is_protocol_error():
    monitor = RetireMonitor()

    with pytest.raises(
        RetireProtocolError,
        match="without a valid D-stage",
    ):
        monitor.observe_falling_edge(
            cycle=1,
            regwrite=True,
            rd=5,
            wdata=10,
        )


def test_duplicate_instruction_id_is_rejected():
    monitor = RetireMonitor()

    monitor.advance_pipeline(tag(1))
    monitor.advance_pipeline(None)
    monitor.advance_pipeline(None)

    first = monitor.observe_falling_edge(
        cycle=3,
        regwrite=True,
        rd=5,
        wdata=1,
    )

    assert first.instruction_id == 1

    # Inject an invalid duplicate tag.
    monitor.advance_pipeline(tag(1))
    monitor.advance_pipeline(None)
    monitor.advance_pipeline(None)

    with pytest.raises(
        RetireProtocolError,
        match="order violation",
    ):
        monitor.observe_falling_edge(
            cycle=6,
            regwrite=True,
            rd=5,
            wdata=1,
        )


def test_skipped_instruction_id_is_rejected():
    monitor = RetireMonitor()

    monitor.advance_pipeline(tag(2))
    monitor.advance_pipeline(None)
    monitor.advance_pipeline(None)

    with pytest.raises(
        RetireProtocolError,
        match="expected instruction_id=1",
    ):
        monitor.observe_falling_edge(
            cycle=3,
            regwrite=True,
            rd=5,
            wdata=1,
        )


def test_stage_tag_order_is_explicit():
    monitor = RetireMonitor()

    assert monitor.stage_instruction_ids == (
        None,
        None,
        None,
    )

    monitor.advance_pipeline(tag(1))

    assert monitor.stage_instruction_ids == (
        1,
        None,
        None,
    )

    monitor.advance_pipeline(tag(2))

    assert monitor.stage_instruction_ids == (
        2,
        1,
        None,
    )

    monitor.advance_pipeline(tag(3))

    assert monitor.stage_instruction_ids == (
        3,
        2,
        1,
    )


def test_reset_clears_tags_and_retire_state():
    monitor = RetireMonitor()

    monitor.advance_pipeline(tag(1))
    monitor.advance_pipeline(None)
    monitor.advance_pipeline(None)

    event = monitor.observe_falling_edge(
        cycle=3,
        regwrite=True,
        rd=5,
        wdata=7,
    )

    assert event.instruction_id == 1
    assert monitor.retired_count == 1

    monitor.reset()

    assert monitor.retired_count == 0
    assert monitor.stage_instruction_ids == (
        None,
        None,
        None,
    )
