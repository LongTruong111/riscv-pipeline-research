from random import Random

import pytest

from research.week5.impl.rv32_encode import (
    add,
    addi,
    auipc,
    jal,
    jalr,
    lui,
    lw,
    sw,
)

from research.week10.adaptive.register_policy import (
    TargetSelection,
)
from research.week10.adaptive.template_library import (
    ArmID,
)
from research.week10.adaptive.template_realizer import (
    ALU_PRODUCER_VALUE,
    JUMP_LOCAL_TARGET_OFFSET,
    LOAD_OFFSET,
    SPECIAL_IMM20,
    STORE_DATA_VALUE,
    STORE_OFFSET,
    TemplateRealizer,
    TemplateVariant,
)

class ScriptedRandom(Random):
    """
    Controlled RNG for deterministic variant-selection tests.

    __new__ deliberately consumes choice_indices instead of forwarding
    the list into random.Random construction.
    """

    def __new__(cls, choice_indices):
        del choice_indices
        return Random.__new__(cls)

    def __init__(self, choice_indices):
        Random.__init__(self, 0)
        self._choice_indices = list(choice_indices)

    def choice(self, sequence):
        if not sequence:
            raise AssertionError(
                "choice() received an empty sequence"
            )

        if not self._choice_indices:
            raise AssertionError(
                "unexpected choice() call"
            )

        index = self._choice_indices.pop(0)

        return sequence[index % len(sequence)]


class NoChoiceRandom(Random):
    def __new__(cls):
        return Random.__new__(cls)

    def __init__(self):
        Random.__init__(self, 0)

    def choice(self, sequence):
        raise AssertionError(
            "choice() must not be called"
        )

def rd(word):
    return (word >> 7) & 0x1F


def rs1(word):
    return (word >> 15) & 0x1F


def rs2(word):
    return (word >> 20) & 0x1F


def test_a0_rs1_variant():
    realizer = TemplateRealizer(
        ScriptedRandom([0])
    )

    result = realizer.realize(
        ArmID.A0,
        TargetSelection(d1=7),
    )

    destination = 1

    assert result.variant is TemplateVariant.RS1
    assert result.words == (
        addi(7, 0, ALU_PRODUCER_VALUE),
        addi(destination, 7, 1),
    )

    assert result.d1_producer_word_index == 0
    assert result.consumer_word_index == 1
    assert result.expected_executed_instruction_count == 2


def test_a0_rs2_variant():
    result = TemplateRealizer(
        ScriptedRandom([1])
    ).realize(
        ArmID.A0,
        TargetSelection(d1=7),
    )

    assert result.variant is TemplateVariant.RS2
    assert result.words[1] == add(
        1,
        0,
        7,
    )


def test_a1_has_one_executed_structural_filler():
    result = TemplateRealizer(
        ScriptedRandom([0])
    ).realize(
        ArmID.A1,
        TargetSelection(d2=7),
    )

    assert result.structural_word_indices == (1,)
    assert result.expected_executed_word_indices == (
        0,
        1,
        2,
    )
    assert result.d2_producer_word_index == 0
    assert result.consumer_word_index == 2

    # Structural filler must not overwrite target register.
    assert rd(result.words[1]) != 7


def test_a2_is_load_d1():
    result = TemplateRealizer(
        ScriptedRandom([0])
    ).realize(
        ArmID.A2,
        TargetSelection(d1=8),
    )

    assert result.words[0] == lw(
        8,
        0,
        LOAD_OFFSET,
    )

    assert result.d1_producer_word_index == 0
    assert result.consumer_word_index == 1


def test_a2_rs2_variant_reads_target_on_rs2():
    result = TemplateRealizer(
        ScriptedRandom([1])
    ).realize(
        ArmID.A2,
        TargetSelection(d1=8),
    )

    assert result.variant is TemplateVariant.RS2
    assert rs1(result.words[1]) == 0
    assert rs2(result.words[1]) == 8


def test_a3_load_d2_has_structural_filler():
    result = TemplateRealizer(
        ScriptedRandom([0])
    ).realize(
        ArmID.A3,
        TargetSelection(d2=9),
    )

    assert result.words[0] == lw(
        9,
        0,
        LOAD_OFFSET,
    )

    assert result.structural_word_indices == (1,)
    assert result.d2_producer_word_index == 0
    assert result.consumer_word_index == 2


def test_a4_realizes_independent_d2_and_d1_producers():
    result = TemplateRealizer(
        Random(1)
    ).realize(
        ArmID.A4,
        TargetSelection(
            d1=7,
            d2=13,
        ),
    )

    destination = 1

    assert result.variant is TemplateVariant.DUAL

    assert result.words == (
        addi(13, 0, 10),
        addi(7, 0, 20),
        add(destination, 7, 13),
    )

    assert result.d2_producer_word_index == 0
    assert result.d1_producer_word_index == 1
    assert result.consumer_word_index == 2

    # Newer producer does not read older d2 target.
    assert rs1(result.words[1]) == 0


def test_a5_lui_variant():
    result = TemplateRealizer(
        ScriptedRandom([0])
    ).realize(
        ArmID.A5,
        TargetSelection(d1=5),
    )

    assert result.variant is TemplateVariant.LUI
    assert result.words[0] == lui(
        5,
        SPECIAL_IMM20,
    )


def test_a5_auipc_variant():
    result = TemplateRealizer(
        ScriptedRandom([1])
    ).realize(
        ArmID.A5,
        TargetSelection(d1=5),
    )

    assert result.variant is TemplateVariant.AUIPC
    assert result.words[0] == auipc(
        5,
        SPECIAL_IMM20,
    )


@pytest.mark.parametrize(
    "choice_index, expected_variant",
    [
        (0, TemplateVariant.LUI),
        (1, TemplateVariant.AUIPC),
    ],
)
def test_a6_special_d2_variants(
    choice_index,
    expected_variant,
):
    result = TemplateRealizer(
        ScriptedRandom([choice_index])
    ).realize(
        ArmID.A6,
        TargetSelection(d2=6),
    )

    assert result.variant is expected_variant
    assert result.structural_word_indices == (1,)
    assert result.d2_producer_word_index == 0
    assert result.consumer_word_index == 2
    assert rd(result.words[1]) != 6


def test_a7_jal_variant_at_low_pc():
    result = TemplateRealizer(
        ScriptedRandom([0])
    ).realize(
        ArmID.A7,
        TargetSelection(d1=5),
        start_pc=0,
    )

    assert result.variant is TemplateVariant.JAL

    assert result.words[0] == jal(
        5,
        JUMP_LOCAL_TARGET_OFFSET,
    )

    assert result.expected_executed_word_indices == (
        0,
        3,
    )

    assert result.structural_word_indices == (
        1,
        2,
    )

    assert result.consumer_word_index == 3
    assert result.pc_for_word(3) == 12


def test_a7_jalr_variant_when_absolute_target_is_legal():
    start_pc = 100

    result = TemplateRealizer(
        ScriptedRandom([1])
    ).realize(
        ArmID.A7,
        TargetSelection(d1=5),
        start_pc=start_pc,
    )

    target_pc = (
        start_pc
        + JUMP_LOCAL_TARGET_OFFSET
    )

    assert result.variant is TemplateVariant.JALR

    assert result.words[0] == jalr(
        5,
        0,
        target_pc,
    )

    assert result.pc_for_word(
        result.consumer_word_index
    ) == target_pc

    assert result.expected_executed_word_indices == (
        0,
        3,
    )


def test_a7_high_pc_uses_only_legal_jal_without_rng_choice():
    result = TemplateRealizer(
        NoChoiceRandom()
    ).realize(
        ArmID.A7,
        TargetSelection(d1=5),
        start_pc=4096,
    )

    assert result.variant is TemplateVariant.JAL

    assert result.words[0] == jal(
        5,
        JUMP_LOCAL_TARGET_OFFSET,
    )


def test_a7_fallthrough_words_do_not_write_link_register():
    result = TemplateRealizer(
        ScriptedRandom([0])
    ).realize(
        ArmID.A7,
        TargetSelection(d1=5),
    )

    assert rd(result.words[1]) != 5
    assert rd(result.words[2]) != 5


def test_a8_store_data_is_architectural_rs2_target():
    result = TemplateRealizer(
        Random(1)
    ).realize(
        ArmID.A8,
        TargetSelection(d1=11),
    )

    assert result.variant is TemplateVariant.STORE_DATA

    assert result.words == (
        addi(
            11,
            0,
            STORE_DATA_VALUE,
        ),
        sw(
            11,
            0,
            STORE_OFFSET,
        ),
    )

    store_word = result.words[1]

    assert rs1(store_word) == 0
    assert rs2(store_word) == 11

    assert result.d1_producer_word_index == 0
    assert result.consumer_word_index == 1


def test_a9_newest_writer_is_active_d1_producer():
    result = TemplateRealizer(
        Random(1)
    ).realize(
        ArmID.A9,
        TargetSelection(d1=12),
    )

    assert result.variant is TemplateVariant.PRIORITY

    assert result.words == (
        addi(12, 0, 1),
        addi(12, 0, 2),
        addi(1, 12, 0),
    )

    assert result.shadowed_writer_word_indices == (0,)
    assert result.d1_producer_word_index == 1
    assert result.d2_producer_word_index is None
    assert result.consumer_word_index == 2


def test_a9_consumer_reads_same_target_written_twice():
    result = TemplateRealizer(
        Random(1)
    ).realize(
        ArmID.A9,
        TargetSelection(d1=17),
    )

    assert rd(result.words[0]) == 17
    assert rd(result.words[1]) == 17
    assert rs1(result.words[2]) == 17


@pytest.mark.parametrize(
    "arm_id, target",
    [
        (
            ArmID.A0,
            TargetSelection(d2=5),
        ),
        (
            ArmID.A1,
            TargetSelection(d1=5),
        ),
        (
            ArmID.A4,
            TargetSelection(d1=5),
        ),
        (
            ArmID.A7,
            TargetSelection(d2=5),
        ),
    ],
)
def test_wrong_target_shape_is_rejected(
    arm_id,
    target,
):
    with pytest.raises(ValueError):
        TemplateRealizer(
            Random(1)
        ).realize(
            arm_id,
            target,
        )


@pytest.mark.parametrize(
    "bad_pc",
    [-4, 2, 6],
)
def test_invalid_start_pc_is_rejected(
    bad_pc,
):
    with pytest.raises(ValueError):
        TemplateRealizer(
            Random(1)
        ).realize(
            ArmID.A0,
            TargetSelection(d1=5),
            start_pc=bad_pc,
        )


def test_all_realized_words_fit_32_bits():
    cases = (
        (
            ArmID.A0,
            TargetSelection(d1=5),
        ),
        (
            ArmID.A1,
            TargetSelection(d2=5),
        ),
        (
            ArmID.A2,
            TargetSelection(d1=6),
        ),
        (
            ArmID.A3,
            TargetSelection(d2=6),
        ),
        (
            ArmID.A4,
            TargetSelection(
                d1=7,
                d2=8,
            ),
        ),
        (
            ArmID.A5,
            TargetSelection(d1=9),
        ),
        (
            ArmID.A6,
            TargetSelection(d2=10),
        ),
        (
            ArmID.A7,
            TargetSelection(d1=11),
        ),
        (
            ArmID.A8,
            TargetSelection(d1=12),
        ),
        (
            ArmID.A9,
            TargetSelection(d1=13),
        ),
    )

    for arm_id, target in cases:
        result = TemplateRealizer(
            Random(123)
        ).realize(
            arm_id,
            target,
        )

        assert result.words

        assert all(
            0 <= word <= 0xFFFFFFFF
            for word in result.words
        )


def test_same_seed_same_inputs_produce_same_templates():
    realizer_a = TemplateRealizer(
        Random(20260921)
    )

    realizer_b = TemplateRealizer(
        Random(20260921)
    )

    cases = (
        (
            ArmID.A0,
            TargetSelection(d1=5),
        ),
        (
            ArmID.A1,
            TargetSelection(d2=6),
        ),
        (
            ArmID.A2,
            TargetSelection(d1=7),
        ),
        (
            ArmID.A3,
            TargetSelection(d2=8),
        ),
        (
            ArmID.A5,
            TargetSelection(d1=9),
        ),
        (
            ArmID.A6,
            TargetSelection(d2=10),
        ),
        (
            ArmID.A7,
            TargetSelection(d1=11),
        ),
    )

    trace_a = [
        realizer_a.realize(
            arm_id,
            target,
            start_pc=100,
        )
        for arm_id, target in cases
    ]

    trace_b = [
        realizer_b.realize(
            arm_id,
            target,
            start_pc=100,
        )
        for arm_id, target in cases
    ]

    assert trace_a == trace_b


def test_no_template_uses_x0_as_positive_destination():
    cases = (
        (
            ArmID.A0,
            TargetSelection(d1=1),
        ),
        (
            ArmID.A1,
            TargetSelection(d2=2),
        ),
        (
            ArmID.A2,
            TargetSelection(d1=3),
        ),
        (
            ArmID.A3,
            TargetSelection(d2=4),
        ),
        (
            ArmID.A4,
            TargetSelection(
                d1=5,
                d2=6,
            ),
        ),
        (
            ArmID.A5,
            TargetSelection(d1=7),
        ),
        (
            ArmID.A6,
            TargetSelection(d2=8),
        ),
        (
            ArmID.A7,
            TargetSelection(d1=9),
        ),
        (
            ArmID.A8,
            TargetSelection(d1=10),
        ),
        (
            ArmID.A9,
            TargetSelection(d1=11),
        ),
    )

    for arm_id, target in cases:
        result = TemplateRealizer(
            Random(123)
        ).realize(
            arm_id,
            target,
            start_pc=100,
        )

        for index in (
            value
            for value in (
                result.d1_producer_word_index,
                result.d2_producer_word_index,
            )
            if value is not None
        ):
            assert rd(result.words[index]) != 0
