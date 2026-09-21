from random import Random

import pytest

from research.week5.impl.coverage_model import (
    L2Hit,
    l2_bin_index,
)

from research.week10.adaptive.provenance import (
    AttributionRegistry,
    AttributionWitness,
    build_template_witnesses,
)
from research.week10.adaptive.register_policy import (
    TargetSelection,
)
from research.week10.adaptive.template_library import (
    ArmID,
    Distance,
)
from research.week10.adaptive.template_realizer import (
    TemplateRealizer,
)


def make_hit(
    *,
    distance,
    register,
    producer,
    consumer,
):
    return L2Hit(
        bin_index=l2_bin_index(
            distance,
            register,
        ),
        distance=distance,
        register=register,
        producer_instruction_index=producer,
        consumer_instruction_index=consumer,
        producer_type="ALU_RESULT",
        consumer_type="ALU",
    )


def realize(
    arm_id,
    target,
    *,
    start_pc=0,
):
    return TemplateRealizer(
        Random(20260921)
    ).realize(
        arm_id,
        target,
        start_pc=start_pc,
    )


def test_a0_builds_exact_d1_witness():
    template = realize(
        ArmID.A0,
        TargetSelection(d1=5),
    )

    witnesses = build_template_witnesses(
        template,
        template_instance_id=1,
        first_executed_instruction_index=100,
    )

    assert len(witnesses) == 1

    witness = witnesses[0]

    assert witness.arm_id is ArmID.A0
    assert witness.distance is Distance.D1
    assert witness.register == 5
    assert witness.producer_instruction_index == 100
    assert witness.consumer_instruction_index == 101


def test_a1_structural_filler_produces_d2_witness():
    template = realize(
        ArmID.A1,
        TargetSelection(d2=6),
    )

    witness = build_template_witnesses(
        template,
        template_instance_id=2,
        first_executed_instruction_index=200,
    )[0]

    assert witness.distance is Distance.D2
    assert witness.register == 6
    assert witness.producer_instruction_index == 200
    assert witness.consumer_instruction_index == 202


def test_a4_builds_two_exact_witnesses():
    template = realize(
        ArmID.A4,
        TargetSelection(
            d1=7,
            d2=13,
        ),
    )

    witnesses = build_template_witnesses(
        template,
        template_instance_id=3,
        first_executed_instruction_index=300,
    )

    assert len(witnesses) == 2

    by_distance = {
        witness.distance: witness
        for witness in witnesses
    }

    d1 = by_distance[Distance.D1]
    d2 = by_distance[Distance.D2]

    assert d1.register == 7
    assert d1.producer_instruction_index == 301
    assert d1.consumer_instruction_index == 302

    assert d2.register == 13
    assert d2.producer_instruction_index == 300
    assert d2.consumer_instruction_index == 302


def test_a7_flushed_words_do_not_increase_executed_distance():
    template = realize(
        ArmID.A7,
        TargetSelection(d1=9),
        start_pc=100,
    )

    assert (
        template.expected_executed_word_indices
        == (0, 3)
    )

    witness = build_template_witnesses(
        template,
        template_instance_id=4,
        first_executed_instruction_index=400,
    )[0]

    assert witness.distance is Distance.D1
    assert witness.producer_instruction_index == 400
    assert witness.consumer_instruction_index == 401


def test_a9_shadowed_writer_is_not_a_witness():
    template = realize(
        ArmID.A9,
        TargetSelection(d1=12),
    )

    assert (
        template.shadowed_writer_word_indices
        == (0,)
    )

    witnesses = build_template_witnesses(
        template,
        template_instance_id=5,
        first_executed_instruction_index=500,
    )

    assert len(witnesses) == 1

    witness = witnesses[0]

    # word 0 -> instruction 500 is the shadowed writer.
    # word 1 -> instruction 501 is the newest active writer.
    # word 2 -> instruction 502 is the consumer.
    assert witness.producer_instruction_index == 501
    assert witness.consumer_instruction_index == 502
    assert witness.distance is Distance.D1


def test_exact_hit_matches_witness():
    witness = AttributionWitness(
        arm_id=ArmID.A0,
        template_instance_id=1,
        distance=Distance.D1,
        register=5,
        producer_instruction_index=10,
        consumer_instruction_index=11,
    )

    hit = make_hit(
        distance=1,
        register=5,
        producer=10,
        consumer=11,
    )

    assert witness.matches_hit(hit)


def test_same_bin_incidental_hit_does_not_match():
    witness = AttributionWitness(
        arm_id=ArmID.A0,
        template_instance_id=1,
        distance=Distance.D1,
        register=5,
        producer_instruction_index=10,
        consumer_instruction_index=11,
    )

    # Same frozen L2 bin (d1, x5), different template provenance.
    incidental = make_hit(
        distance=1,
        register=5,
        producer=20,
        consumer=21,
    )

    assert not witness.matches_hit(
        incidental
    )


def test_registry_consumes_exact_match_once():
    registry = AttributionRegistry()

    witness = AttributionWitness(
        arm_id=ArmID.A0,
        template_instance_id=1,
        distance=Distance.D1,
        register=5,
        producer_instruction_index=10,
        consumer_instruction_index=11,
    )

    registry.register(witness)

    hit = make_hit(
        distance=1,
        register=5,
        producer=10,
        consumer=11,
    )

    assert registry.pending_count == 1

    assert (
        registry.consume_match(hit)
        == witness
    )

    assert registry.pending_count == 0

    assert registry.consume_match(hit) is None


def test_registry_keeps_witness_on_incidental_same_bin():
    registry = AttributionRegistry()

    witness = AttributionWitness(
        arm_id=ArmID.A0,
        template_instance_id=1,
        distance=Distance.D1,
        register=5,
        producer_instruction_index=10,
        consumer_instruction_index=11,
    )

    registry.register(witness)

    incidental = make_hit(
        distance=1,
        register=5,
        producer=20,
        consumer=21,
    )

    assert (
        registry.consume_match(
            incidental
        )
        is None
    )

    assert registry.pending_count == 1


def test_registry_supports_a4_two_witnesses_same_consumer():
    template = realize(
        ArmID.A4,
        TargetSelection(
            d1=7,
            d2=13,
        ),
    )

    witnesses = build_template_witnesses(
        template,
        template_instance_id=10,
        first_executed_instruction_index=100,
    )

    registry = AttributionRegistry()
    registry.register_many(witnesses)

    assert registry.pending_count == 2
    assert registry.pending_consumer_count == 1

    d1_hit = make_hit(
        distance=1,
        register=7,
        producer=101,
        consumer=102,
    )

    d2_hit = make_hit(
        distance=2,
        register=13,
        producer=100,
        consumer=102,
    )

    assert (
        registry.consume_match(
            d1_hit
        )
        is not None
    )

    assert registry.pending_count == 1

    assert (
        registry.consume_match(
            d2_hit
        )
        is not None
    )

    assert registry.pending_count == 0


def test_prune_removes_unrealized_witness():
    registry = AttributionRegistry()

    registry.register(
        AttributionWitness(
            arm_id=ArmID.A0,
            template_instance_id=1,
            distance=Distance.D1,
            register=5,
            producer_instruction_index=10,
            consumer_instruction_index=11,
        )
    )

    assert registry.prune(
        latest_instruction_index=10
    ) == 0

    assert registry.pending_count == 1

    assert registry.prune(
        latest_instruction_index=11
    ) == 1

    assert registry.pending_count == 0


def test_prune_does_not_remove_future_witness():
    registry = AttributionRegistry()

    registry.register(
        AttributionWitness(
            arm_id=ArmID.A1,
            template_instance_id=1,
            distance=Distance.D2,
            register=6,
            producer_instruction_index=20,
            consumer_instruction_index=22,
        )
    )

    assert registry.prune(
        latest_instruction_index=21
    ) == 0

    assert registry.pending_count == 1


def test_duplicate_registration_is_rejected():
    registry = AttributionRegistry()

    witness = AttributionWitness(
        arm_id=ArmID.A0,
        template_instance_id=1,
        distance=Distance.D1,
        register=5,
        producer_instruction_index=10,
        consumer_instruction_index=11,
    )

    registry.register(witness)

    with pytest.raises(ValueError):
        registry.register(witness)


def test_invalid_witness_distance_is_rejected():
    with pytest.raises(ValueError):
        AttributionWitness(
            arm_id=ArmID.A1,
            template_instance_id=1,
            distance=Distance.D2,
            register=5,
            producer_instruction_index=10,
            consumer_instruction_index=11,
        )


def test_template_instance_id_must_be_positive():
    with pytest.raises(ValueError):
        AttributionWitness(
            arm_id=ArmID.A0,
            template_instance_id=0,
            distance=Distance.D1,
            register=5,
            producer_instruction_index=10,
            consumer_instruction_index=11,
        )
