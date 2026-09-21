import pytest

from research.week5.impl.directed_cases import (
    DIRECTED_CASES,
)
from research.week5.impl.rv32_encode import (
    add,
    addi,
)
from research.week9.benchmark.streaming_timing import (
    StreamingTimingOracleV1,
)
from research.week10.adaptive.campaign_runner import (
    IMEM_WORD_CAPACITY,
)
from research.week10.adaptive.mutable_timing_oracle import (
    BoundedMutableTimingOracleV1,
)
from research.week7.timing_oracle_v1 import (
    build_timing_schedule_v1,
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
def test_mutable_oracle_matches_frozen_week9_static_semantics(
    case_id,
):
    case = DIRECTED_CASES[
        case_id
    ]

    program = build_program(
        case.words
    )

    frozen_schedule = (
        build_timing_schedule_v1(
            program
        )
    )

    frozen_streaming = (
        StreamingTimingOracleV1(
            program
        )
    )

    mutable = (
        BoundedMutableTimingOracleV1(
            program
        )
    )

    frozen_results = tuple(
        frozen_streaming.next_expectation()
        for _ in range(
            frozen_schedule.instruction_count
        )
    )

    mutable_results = tuple(
        mutable.next_expectation()
        for _ in range(
            frozen_schedule.instruction_count
        )
    )

    assert (
        frozen_results
        == frozen_schedule.expectations
    )

    assert (
        mutable_results
        == frozen_schedule.expectations
    )

    assert (
        mutable.generated_count
        == frozen_schedule.instruction_count
    )

    assert (
        mutable.writer_count
        == frozen_streaming.writer_count
    )

def test_append_preserves_cross_boundary_writer_state():
    """
    A producer appears at the end of the initial program.

    Its consumer is appended only after the producer expectation has
    already been generated.

    The resulting timing expectation must still match a frozen oracle
    that knew the complete program from the beginning.
    """
    words = (
        addi(
            1,
            0,
            1,
        ),
        addi(
            5,
            0,
            7,
        ),
        add(
            6,
            5,
            0,
        ),
    )

    full_program = (
        build_program(
            words
        )
    )

    frozen = (
        StreamingTimingOracleV1(
            full_program
        )
    )

    mutable = (
        BoundedMutableTimingOracleV1(
            {
                0: words[0],
                4: words[1],
            }
        )
    )

    expected_1 = (
        frozen.next_expectation()
    )
    expected_2 = (
        frozen.next_expectation()
    )

    observed_1 = (
        mutable.next_expectation()
    )
    observed_2 = (
        mutable.next_expectation()
    )

    assert observed_1 == expected_1
    assert observed_2 == expected_2

    mutable.append_program(
        {
            8: words[2],
        }
    )

    expected_3 = (
        frozen.next_expectation()
    )

    observed_3 = (
        mutable.next_expectation()
    )

    assert observed_3 == expected_3

    assert (
        mutable.generated_count
        == 3
    )

    assert (
        mutable.program_word_count
        == 3
    )


def test_append_is_atomic_on_invalid_gap():
    words = (
        addi(
            1,
            0,
            1,
        ),
        addi(
            2,
            0,
            2,
        ),
    )

    oracle = (
        BoundedMutableTimingOracleV1(
            {
                0: words[0],
            }
        )
    )

    before_count = (
        oracle.program_word_count
    )

    with pytest.raises(
        ValueError,
        match="physically contiguous",
    ):
        oracle.append_program(
            {
                8: words[1],
            }
        )

    assert (
        oracle.program_word_count
        == before_count
    )


def test_existing_pc_cannot_be_overwritten():
    first = addi(
        1,
        0,
        1,
    )

    replacement = addi(
        1,
        0,
        2,
    )

    oracle = (
        BoundedMutableTimingOracleV1(
            {
                0: first,
            }
        )
    )

    with pytest.raises(
        ValueError,
        match="cannot overwrite",
    ):
        oracle.append_program(
            {
                0: replacement,
            }
        )

    first_expectation = (
        oracle.next_expectation()
    )

    assert (
        first_expectation.instruction
        == first
    )


def test_append_rejects_pc_outside_imem_window():
    first = addi(
        1,
        0,
        1,
    )

    second = addi(
        2,
        0,
        2,
    )

    oracle = (
        BoundedMutableTimingOracleV1(
            {
                0: first,
            }
        )
    )

    with pytest.raises(
        ValueError,
        match="9-bit IMEM window",
    ):
        oracle.append_program(
            {
                512: second,
            }
        )


def test_program_capacity_is_bounded_to_128_words():
    instruction = addi(
        1,
        0,
        1,
    )

    program = {
        index * 4: instruction
        for index in range(
            IMEM_WORD_CAPACITY
        )
    }

    oracle = (
        BoundedMutableTimingOracleV1(
            program
        )
    )

    assert (
        oracle.program_word_count
        == IMEM_WORD_CAPACITY
    )

    assert (
        oracle.remaining_word_capacity
        == 0
    )


def test_constructor_rejects_out_of_window_initial_pc():
    instruction = addi(
        1,
        0,
        1,
    )

    with pytest.raises(
        ValueError,
        match="9-bit IMEM window",
    ):
        BoundedMutableTimingOracleV1(
            {
                0: instruction,
                512: instruction,
            }
        )
