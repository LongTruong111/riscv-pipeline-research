import pytest

from research.week5.impl.rv32_encode import (
    add,
    addi,
    jal,
    jalr,
)
from research.week9.benchmark.streaming_timing import (
    StreamingTimingOracleV1,
)
from research.week10.adaptive.campaign_runner import (
    IMEM_WORD_CAPACITY,
)
from research.week10.adaptive.wrap_aware_timing_oracle import (
    WrapAwareMutableTimingOracleV1,
)


def build_full_program(
    instruction: int,
) -> dict[int, int]:
    return {
        logical_word * 4: instruction
        for logical_word in range(
            IMEM_WORD_CAPACITY
        )
    }


def test_wrap_aware_oracle_matches_frozen_semantics_before_wrap():
    program = {
        0: addi(
            5,
            0,
            7,
        ),
        4: add(
            6,
            5,
            0,
        ),
    }

    frozen = StreamingTimingOracleV1(
        program
    )

    wrapped = (
        WrapAwareMutableTimingOracleV1(
            program
        )
    )

    assert (
        wrapped.next_expectation()
        == frozen.next_expectation()
    )

    assert (
        wrapped.next_expectation()
        == frozen.next_expectation()
    )

    assert wrapped.generated_count == 2
    assert wrapped.writer_count == 2


def test_live_physical_slot_must_be_released_before_reuse():
    filler = addi(
        0,
        0,
        0,
    )

    replacement = addi(
        1,
        0,
        9,
    )

    oracle = (
        WrapAwareMutableTimingOracleV1(
            build_full_program(
                filler
            )
        )
    )

    assert (
        oracle.program_word_count
        == IMEM_WORD_CAPACITY
    )

    assert (
        oracle.logical_owner_for_pc(
            0
        )
        == 0
    )

    assert (
        oracle.generation_for_pc(
            0
        )
        == 0
    )

    with pytest.raises(
        ValueError,
        match="live physical timing slot",
    ):
        oracle.append_program(
            {
                0: replacement,
            },
            first_logical_word_index=(
                IMEM_WORD_CAPACITY
            ),
        )

    # Consume logical word zero before its runtime-style release.
    first = oracle.next_expectation()

    assert first.instruction_id == 1
    assert first.pc == 0
    assert first.instruction == filler

    oracle.release_logical_words(
        first_logical_word_index=0,
        word_count=1,
    )

    assert (
        oracle.logical_owner_for_pc(
            0
        )
        is None
    )

    oracle.append_program(
        {
            0: replacement,
        },
        first_logical_word_index=(
            IMEM_WORD_CAPACITY
        ),
    )

    assert (
        oracle.program_word_count
        == IMEM_WORD_CAPACITY
    )

    assert (
        oracle.logical_owner_for_pc(
            0
        )
        == IMEM_WORD_CAPACITY
    )

    assert (
        oracle.generation_for_pc(
            0
        )
        == 1
    )


def test_writer_history_survives_508_to_zero_wrap_and_slot_reuse():
    filler = addi(
        0,
        0,
        0,
    )

    producer = addi(
        5,
        0,
        7,
    )

    consumer = add(
        6,
        5,
        0,
    )

    program = build_full_program(
        filler
    )

    program[508] = producer

    oracle = (
        WrapAwareMutableTimingOracleV1(
            program
        )
    )

    expectations = [
        oracle.next_expectation()
        for _ in range(
            IMEM_WORD_CAPACITY
        )
    ]

    producer_expectation = (
        expectations[-1]
    )

    assert (
        producer_expectation
        .instruction_id
        == 128
    )

    assert (
        producer_expectation.pc
        == 508
    )

    # Physical fetch state wraps, while timing/writer state remains live.
    assert oracle.expected_pc == 0

    oracle.release_logical_words(
        first_logical_word_index=0,
        word_count=IMEM_WORD_CAPACITY,
    )

    assert oracle.program_word_count == 0

    oracle.append_program(
        {
            0: consumer,
        },
        first_logical_word_index=128,
    )

    consumer_expectation = (
        oracle.next_expectation()
    )

    assert (
        consumer_expectation
        .instruction_id
        == 129
    )

    assert consumer_expectation.pc == 0

    assert (
        consumer_expectation
        .source_a_producer_id
        == 128
    )

    assert (
        consumer_expectation
        .source_a_cycle_age
        == 1
    )

    # Frozen forwarding contract:
    # age 1 -> EX/MEM -> selector 0b10.
    assert (
        consumer_expectation.forward_a
        == 0b10
    )


def test_program_backing_remains_bounded_across_three_generations():
    filler = addi(
        0,
        0,
        0,
    )

    oracle = (
        WrapAwareMutableTimingOracleV1(
            build_full_program(
                filler
            )
        )
    )

    total_logical_words = (
        IMEM_WORD_CAPACITY
        * 3
    )

    for logical_word_index in range(
        total_logical_words
    ):
        expectation = (
            oracle.next_expectation()
        )

        assert (
            expectation.instruction_id
            == logical_word_index + 1
        )

        assert (
            expectation.pc
            == (
                logical_word_index
                % IMEM_WORD_CAPACITY
            )
            * 4
        )

        oracle.release_logical_words(
            first_logical_word_index=(
                logical_word_index
            ),
            word_count=1,
        )

        future_logical_word = (
            logical_word_index
            + IMEM_WORD_CAPACITY
        )

        if (
            future_logical_word
            < total_logical_words
        ):
            future_pc = (
                future_logical_word
                % IMEM_WORD_CAPACITY
            ) * 4

            oracle.append_program(
                {
                    future_pc: filler,
                },
                first_logical_word_index=(
                    future_logical_word
                ),
            )

        assert (
            oracle.program_word_count
            <= IMEM_WORD_CAPACITY
        )

    assert (
        oracle.generated_count
        == total_logical_words
    )

    assert (
        oracle.next_append_logical_word_index
        == total_logical_words
    )

    assert (
        oracle.next_release_logical_word_index
        == total_logical_words
    )

    assert oracle.program_word_count == 0

    # 384 sequential instructions ends again after PC 508.
    assert oracle.expected_pc == 0

@pytest.mark.parametrize(
    (
        "producer_word",
        "expected_mnemonic",
    ),
    (
        (
            jal(
                5,
                12,
            ),
            "JAL",
        ),
        (
            jalr(
                5,
                0,
                520,
            ),
            "JALR",
        ),
    ),
)
def test_a7_link_dependency_survives_physical_pc_wrap(
    producer_word,
    expected_mnemonic,
):
    """
    A7 cross-wrap timing proof.

    Logical image around the boundary:

        logical 127 -> PC 508 : JAL/JALR x5, target
        logical 128 -> PC   0 : flushed fall-through
        logical 129 -> PC   4 : flushed fall-through
        logical 130 -> PC   8 : ADDI x6,x5,1 target consumer

    Executed-program order is therefore:

        producer
        consumer

    so the architectural dependency distance is d1.

    Control redirect introduces two admission bubbles, therefore the
    producer cycle age at the consumer is 3 and the consumer reads the
    link value from RF rather than EX/MEM or MEM/WB.
    """

    filler = addi(
        0,
        0,
        0,
    )

    first_fallthrough = addi(
        20,
        0,
        9,
    )

    second_fallthrough = addi(
        21,
        0,
        10,
    )

    consumer = addi(
        6,
        5,
        1,
    )

    initial_program = {
        logical_word * 4: filler
        for logical_word in range(
            IMEM_WORD_CAPACITY
        )
    }

    initial_program[
        508
    ] = producer_word

    oracle = (
        WrapAwareMutableTimingOracleV1(
            initial_program
        )
    )

    # ----------------------------------------------------------
    # Consume and release physical slots 0, 4, and 8 before they
    # are reused by logical words 128, 129, and 130.
    # ----------------------------------------------------------
    for logical_word_index in range(
        3
    ):
        expectation = (
            oracle.next_expectation()
        )

        assert (
            expectation.instruction_id
            == logical_word_index + 1
        )

        assert (
            expectation.pc
            == logical_word_index * 4
        )

        oracle.release_logical_words(
            first_logical_word_index=(
                logical_word_index
            ),
            word_count=1,
        )

    assert (
        oracle.program_word_count
        == IMEM_WORD_CAPACITY - 3
    )

    # ----------------------------------------------------------
    # Patch the three image words beyond logical word 127.
    #
    # The first two are wrong-path fall-through instructions.
    # Only the target at logical word 130 may execute.
    # ----------------------------------------------------------
    oracle.append_program(
        {
            0: first_fallthrough,
            4: second_fallthrough,
            8: consumer,
        },
        first_logical_word_index=128,
    )

    assert (
        oracle.program_word_count
        == IMEM_WORD_CAPACITY
    )

    assert (
        oracle.logical_owner_for_pc(
            0
        )
        == 128
    )

    assert (
        oracle.logical_owner_for_pc(
            4
        )
        == 129
    )

    assert (
        oracle.logical_owner_for_pc(
            8
        )
        == 130
    )

    assert (
        oracle.generation_for_pc(
            8
        )
        == 1
    )

    # ----------------------------------------------------------
    # Advance through logical words 3..126.
    # ----------------------------------------------------------
    for logical_word_index in range(
        3,
        127,
    ):
        expectation = (
            oracle.next_expectation()
        )

        assert (
            expectation.pc
            == logical_word_index * 4
        )

        assert (
            expectation.instruction
            == filler
        )

    # ----------------------------------------------------------
    # Producer executes at the final physical IMEM word.
    # ----------------------------------------------------------
    producer_expectation = (
        oracle.next_expectation()
    )

    assert (
        producer_expectation.instruction_id
        == 128
    )

    assert producer_expectation.pc == 508

    assert (
        producer_expectation.instruction
        == producer_word
    )

    assert (
        producer_expectation.mnemonic
        == expected_mnemonic
    )

    assert producer_expectation.redirect

    assert (
        producer_expectation.redirect_bubbles
        == 2
    )

    # Both JAL and JALR target architectural address 520.
    #
    # The wrap-aware architectural fetch state must therefore become:
    #
    #     520 & 0x1ff = 8
    assert oracle.expected_pc == 8

    # ----------------------------------------------------------
    # The two physical words at PC 0 and PC 4 are image words only.
    # They must be skipped by redirect and must not consume executed
    # instruction IDs.
    # ----------------------------------------------------------
    target_expectation = (
        oracle.next_expectation()
    )

    assert (
        target_expectation.instruction_id
        == 129
    )

    assert target_expectation.pc == 8

    assert (
        target_expectation.instruction
        == consumer
    )

    assert (
        target_expectation.mnemonic
        == "ADDI"
    )

    # Executed-program-order dependency:
    #
    #   producer ID 128
    #   consumer ID 129
    #
    # => architectural d1.
    assert (
        target_expectation.source_a_producer_id
        == 128
    )

    # Redirect contributes two admission bubbles:
    #
    # producer accept = C
    # target accept   = C + 3
    assert (
        target_expectation.accept_cycle
        == (
            producer_expectation.accept_cycle
            + 3
        )
    )

    assert (
        target_expectation.source_a_cycle_age
        == 3
    )

    # age >= 3 -> RF.
    assert (
        target_expectation.forward_a
        == 0b00
    )

    assert (
        target_expectation.stall_cycles_before_accept
        == 0
    )

    # Image words = 131 logical words,
    # accepted instructions = 129 because two fall-through words flush.
    assert (
        oracle.next_append_logical_word_index
        == 131
    )

    assert (
        oracle.generated_count
        == 129
    )

    # Consumer at physical PC 8 then advances sequentially to PC 12.
    assert oracle.expected_pc == 12
