import pytest

from research.week5.impl.l1_coverage import L1Hit
from research.week7.hazard_attribution import (
    TimingObservation,
    correlate_hazard,
)
from research.week7.retire_monitor import RetireEvent
from research.week7.timing_oracle_v1 import TimingExpectationV1


def expectation(
    instruction_id,
    *,
    source_a=None,
    source_b=None,
    accept_cycle=2,
    stall=0,
    forward_a=0b10,
    forward_b=0b00,
    retire_cycle=5,
):
    return TimingExpectationV1(
        instruction_id=instruction_id,
        pc=(instruction_id - 1) * 4,
        instruction=0x00128293,
        mnemonic="ADDI",
        accept_cycle=accept_cycle,
        stall_cycles_before_accept=stall,
        retire_cycle=retire_cycle,
        forward_a=forward_a,
        forward_b=forward_b,
        source_a_producer_id=source_a,
        source_b_producer_id=source_b,
        source_a_cycle_age=(
            None if source_a is None else 1
        ),
        source_b_cycle_age=(
            None if source_b is None else 1
        ),
        redirect=False,
        redirect_bubbles=0,
    )


def observation(
    instruction_id,
    *,
    accept_cycle=2,
    stall=0,
    forward_a=0b10,
    forward_b=0b00,
):
    return TimingObservation(
        instruction_id=instruction_id,
        pc=(instruction_id - 1) * 4,
        instruction=0x00128293,
        accept_cycle=accept_cycle,
        stall_cycles_before_accept=stall,
        forward_a=forward_a,
        forward_b=forward_b,
    )


def retire(instruction_id, cycle=5):
    return RetireEvent(
        cycle=cycle,
        valid=True,
        regwrite=True,
        rd=6,
        wdata=8,
        instruction_id=instruction_id,
    )


def test_h01_full_attribution_passes():
    hit = L1Hit(
        bin_id="H01",
        consumer_instruction_index=2,
        producer_instruction_indices=(1,),
        matched_sources=("RS1",),
    )

    result = correlate_hazard(
        hit,
        expectation(
            2,
            source_a=1,
        ),
        observation(2),
        retire(2),
    )

    assert result.passed
    assert result.failed_checks == ()


def test_timing_mismatch_is_attribution_failure():
    hit = L1Hit(
        bin_id="H01",
        consumer_instruction_index=2,
        producer_instruction_indices=(1,),
        matched_sources=("RS1",),
    )

    result = correlate_hazard(
        hit,
        expectation(
            2,
            source_a=1,
        ),
        observation(
            2,
            forward_a=0b01,
        ),
        retire(2),
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {"forward_a"}


def test_retire_cycle_mismatch_is_attribution_failure():
    hit = L1Hit(
        bin_id="H01",
        consumer_instruction_index=2,
        producer_instruction_indices=(1,),
        matched_sources=("RS1",),
    )

    result = correlate_hazard(
        hit,
        expectation(
            2,
            source_a=1,
        ),
        observation(2),
        retire(
            2,
            cycle=6,
        ),
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {"retire_cycle"}


def test_h10_dual_producer_attribution_passes():
    hit = L1Hit(
        bin_id="H10",
        consumer_instruction_index=3,
        producer_instruction_indices=(1, 2),
        matched_sources=("RS1", "RS2"),
    )

    result = correlate_hazard(
        hit,
        expectation(
            3,
            source_a=2,
            source_b=1,
            accept_cycle=3,
            forward_a=0b10,
            forward_b=0b01,
            retire_cycle=6,
        ),
        observation(
            3,
            accept_cycle=3,
            forward_a=0b10,
            forward_b=0b01,
        ),
        retire(
            3,
            cycle=6,
        ),
    )

    assert result.passed


def test_h17_requires_newest_writer():
    hit = L1Hit(
        bin_id="H17",
        consumer_instruction_index=3,
        producer_instruction_indices=(1, 2),
        matched_sources=("RS1",),
    )

    result = correlate_hazard(
        hit,
        expectation(
            3,
            source_a=2,
            accept_cycle=3,
            retire_cycle=6,
        ),
        observation(
            3,
            accept_cycle=3,
        ),
        retire(
            3,
            cycle=6,
        ),
    )

    assert result.passed


def test_h17_old_writer_is_rejected():
    hit = L1Hit(
        bin_id="H17",
        consumer_instruction_index=3,
        producer_instruction_indices=(1, 2),
        matched_sources=("RS1",),
    )

    result = correlate_hazard(
        hit,
        expectation(
            3,
            source_a=1,
            accept_cycle=3,
            retire_cycle=6,
        ),
        observation(
            3,
            accept_cycle=3,
        ),
        retire(
            3,
            cycle=6,
        ),
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {"rs1_newest_producer"}


def test_h18_x0_has_no_architectural_producer():
    hit = L1Hit(
        bin_id="H18",
        consumer_instruction_index=2,
        producer_instruction_indices=(1,),
        matched_sources=("RS1",),
    )

    result = correlate_hazard(
        hit,
        expectation(
            2,
            source_a=None,
            forward_a=0b00,
        ),
        observation(
            2,
            forward_a=0b00,
        ),
        retire(2),
    )

    assert result.passed


def test_h20_unused_raw_rs2_is_not_dependency():
    hit = L1Hit(
        bin_id="H20",
        consumer_instruction_index=2,
        producer_instruction_indices=(1,),
        matched_sources=("RAW_RS2_UNUSED",),
    )

    result = correlate_hazard(
        hit,
        expectation(
            2,
            source_a=None,
            source_b=None,
            forward_a=0b00,
            forward_b=0b00,
        ),
        observation(
            2,
            forward_a=0b00,
            forward_b=0b00,
        ),
        retire(2),
    )

    assert result.passed


def test_consumer_identity_mismatch_raises():
    hit = L1Hit(
        bin_id="H01",
        consumer_instruction_index=2,
        producer_instruction_indices=(1,),
        matched_sources=("RS1",),
    )

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        correlate_hazard(
            hit,
            expectation(
                3,
                source_a=1,
            ),
            observation(2),
            retire(2),
        )


def test_producer_must_precede_consumer():
    hit = L1Hit(
        bin_id="H01",
        consumer_instruction_index=2,
        producer_instruction_indices=(2,),
        matched_sources=("RS1",),
    )

    with pytest.raises(
        ValueError,
        match="producer must precede consumer",
    ):
        correlate_hazard(
            hit,
            expectation(
                2,
                source_a=2,
            ),
            observation(2),
            retire(2),
        )
