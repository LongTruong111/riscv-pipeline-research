from __future__ import annotations

from random import Random

import pytest

from research.week13.pure_random.campaign_seed import (
    build_campaign_rngs,
)
from research.week13.pure_random.family_sampler import (
    FAMILY_ORDER,
    InstructionFamily,
    sample_family,
)


PILOT_ROOT_1 = 11001


def test_family_order_matches_frozen_addendum():
    assert FAMILY_ORDER == (
        InstructionFamily.ADD,
        InstructionFamily.ADDI,
        InstructionFamily.LW,
        InstructionFamily.SW,
        InstructionFamily.BRANCH,
        InstructionFamily.JAL,
        InstructionFamily.JALR,
        InstructionFamily.LUI,
        InstructionFamily.AUIPC,
    )

    assert len(FAMILY_ORDER) == 9
    assert len(set(FAMILY_ORDER)) == 9


def test_known_answer_family_trace_for_11001():
    """
    Frozen deterministic trace for root seed 11001.

    The expected sequence is stored explicitly rather than generated
    using the implementation under test.
    """
    rngs = build_campaign_rngs(
        PILOT_ROOT_1
    )

    observed = tuple(
        sample_family(
            rngs.family_rng
        )
        for _ in range(20)
    )

    expected = (
        InstructionFamily.ADD,
        InstructionFamily.LW,
        InstructionFamily.JALR,
        InstructionFamily.LW,
        InstructionFamily.ADDI,
        InstructionFamily.JALR,
        InstructionFamily.BRANCH,
        InstructionFamily.JAL,
        InstructionFamily.ADDI,
        InstructionFamily.LW,
        InstructionFamily.JALR,
        InstructionFamily.LW,
        InstructionFamily.SW,
        InstructionFamily.SW,
        InstructionFamily.AUIPC,
        InstructionFamily.JALR,
        InstructionFamily.AUIPC,
        InstructionFamily.JAL,
        InstructionFamily.AUIPC,
        InstructionFamily.JAL,
    )

    assert observed == expected


def test_same_root_reproduces_family_trace():
    first = build_campaign_rngs(
        PILOT_ROOT_1
    )

    second = build_campaign_rngs(
        PILOT_ROOT_1
    )

    first_trace = tuple(
        sample_family(
            first.family_rng
        )
        for _ in range(128)
    )

    second_trace = tuple(
        sample_family(
            second.family_rng
        )
        for _ in range(128)
    )

    assert first_trace == second_trace


def test_operand_rng_perturbation_does_not_change_family_trace():
    """
    Critical ownership invariant:

    arbitrary operand-stream consumption must not perturb future
    family selection.
    """
    baseline = build_campaign_rngs(
        PILOT_ROOT_1
    )

    perturbed = build_campaign_rngs(
        PILOT_ROOT_1
    )

    # Consume arbitrary operand draws only.
    for _ in range(1000):
        perturbed.operand_rng.getrandbits(
            64
        )

    baseline_trace = tuple(
        sample_family(
            baseline.family_rng
        )
        for _ in range(256)
    )

    perturbed_trace = tuple(
        sample_family(
            perturbed.family_rng
        )
        for _ in range(256)
    )

    assert perturbed_trace == baseline_trace


def test_family_draw_consumes_family_rng():
    """
    One family draw must advance the family stream.
    """
    baseline = build_campaign_rngs(
        PILOT_ROOT_1
    )

    consumed = build_campaign_rngs(
        PILOT_ROOT_1
    )

    sample_family(
        consumed.family_rng
    )

    baseline_next = sample_family(
        baseline.family_rng
    )

    consumed_next = sample_family(
        consumed.family_rng
    )

    # Frozen seed 11001 gives different first and second draws.
    assert (
        baseline_next
        == InstructionFamily.ADD
    )

    assert (
        consumed_next
        == InstructionFamily.LW
    )


@pytest.mark.parametrize(
    "invalid",
    (
        None,
        123,
        True,
        "rng",
    ),
)
def test_invalid_rng_is_rejected(
    invalid,
):
    with pytest.raises(
        TypeError,
        match="family_rng must be random.Random",
    ):
        sample_family(
            invalid  # type: ignore[arg-type]
        )


def test_direct_random_instance_is_supported():
    """
    The sampler depends only on the Random interface and does not
    require campaign state.
    """
    rng = Random(12345)

    result = sample_family(
        rng
    )

    assert result in FAMILY_ORDER
