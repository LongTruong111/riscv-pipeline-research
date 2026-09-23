from research.week11.integrated_sequence import (
    WEEK11_INTEGRATED_INSTRUCTION_COUNT,
    build_week11_integrated_sequence,
)
from research.week7.timing_oracle_v1 import build_timing_schedule_v1


def build_program(words):
    return {
        index * 4: instruction
        for index, instruction in enumerate(words)
    }


def test_integrated_sequence_is_exactly_50_instructions():
    words = build_week11_integrated_sequence()

    assert len(words) == WEEK11_INTEGRATED_INSTRUCTION_COUNT
    assert WEEK11_INTEGRATED_INSTRUCTION_COUNT == 50


def test_integrated_sequence_is_supported_by_timing_oracle():
    words = build_week11_integrated_sequence()

    schedule = build_timing_schedule_v1(
        build_program(words),
        max_instructions=50,
    )

    assert schedule.instruction_count == 50


def test_integrated_sequence_expected_load_use_stalls():
    schedule = build_timing_schedule_v1(
        build_program(build_week11_integrated_sequence()),
        max_instructions=50,
    )

    stalled_ids = {
        item.instruction_id
        for item in schedule.expectations
        if item.stall_cycles_before_accept != 0
    }

    assert stalled_ids == {
        7,
        10,
        24,
        27,
        29,
        40,
        47,
    }

    assert schedule.total_stall_cycles == 7
