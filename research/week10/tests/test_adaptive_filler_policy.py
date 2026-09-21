import pytest

from research.week5.impl.rv32_encode import lui
from research.week10.adaptive.filler_policy import (
    CampaignFillerScheduler,
    FILLER_LUI_IMM20,
    FillerConstructionError,
    FillerKind,
    POSITIVE_REGISTERS,
    TARGETED_INSTRUCTIONS_PER_FILLER,
    build_filler_instruction,
    select_auxiliary_register,
)


def test_filler_ratio_constant_is_four_to_one():
    assert TARGETED_INSTRUCTIONS_PER_FILLER == 4


def test_positive_filler_register_domain_excludes_x0():
    assert POSITIVE_REGISTERS == tuple(range(1, 32))
    assert 0 not in POSITIVE_REGISTERS


def test_auxiliary_selection_uses_lowest_legal_register():
    assert select_auxiliary_register() == 1

    assert select_auxiliary_register({1, 2, 3}) == 4


def test_auxiliary_selection_never_returns_x0():
    register = select_auxiliary_register({1, 2, 3})

    assert register != 0
    assert 1 <= register <= 31


def test_auxiliary_selection_respects_protected_target():
    register = select_auxiliary_register({1})

    assert register == 2


def test_auxiliary_selection_can_reach_x31():
    protected = set(range(1, 31))

    assert select_auxiliary_register(protected) == 31


def test_auxiliary_selection_fails_if_all_positive_registers_protected():
    with pytest.raises(FillerConstructionError):
        select_auxiliary_register(set(range(1, 32)))


@pytest.mark.parametrize("invalid_register", [-1, 32, 99])
def test_invalid_protected_register_is_rejected(
    invalid_register,
):
    with pytest.raises(ValueError):
        select_auxiliary_register({invalid_register})


def test_structural_filler_is_source_independent_lui():
    filler = build_filler_instruction(
        kind=FillerKind.STRUCTURAL_D2,
        protected_registers={5},
    )

    assert filler.kind is FillerKind.STRUCTURAL_D2
    assert filler.rd == 1
    assert filler.reads == ()
    assert filler.writes == (1,)
    assert filler.word == lui(1, FILLER_LUI_IMM20)


def test_campaign_filler_is_source_independent_lui():
    filler = build_filler_instruction(
        kind=FillerKind.CAMPAIGN_BACKGROUND,
        protected_registers={1, 2},
    )

    assert filler.kind is FillerKind.CAMPAIGN_BACKGROUND
    assert filler.rd == 3
    assert filler.reads == ()
    assert filler.writes == (3,)
    assert filler.word == lui(3, FILLER_LUI_IMM20)


def test_filler_never_writes_protected_register():
    protected = {1, 2, 3, 4, 5}

    filler = build_filler_instruction(
        kind=FillerKind.STRUCTURAL_D2,
        protected_registers=protected,
    )

    assert filler.rd not in protected


def test_filler_never_writes_x0():
    filler = build_filler_instruction(
        kind=FillerKind.CAMPAIGN_BACKGROUND,
    )

    assert filler.rd != 0
    assert 0 not in filler.writes


def test_scheduler_initial_state():
    scheduler = CampaignFillerScheduler()

    assert scheduler.targeted_instruction_count == 0
    assert scheduler.scheduled_filler_count == 0
    assert scheduler.total_scheduled_instructions == 0
    assert scheduler.filler_fraction == 0.0


def test_scheduler_emits_one_filler_after_four_targeted_instructions():
    scheduler = CampaignFillerScheduler()

    due = scheduler.schedule_after_template(4)

    assert due == 1
    assert scheduler.targeted_instruction_count == 4
    assert scheduler.scheduled_filler_count == 1
    assert scheduler.total_scheduled_instructions == 5
    assert scheduler.filler_fraction == pytest.approx(0.20)


def test_scheduler_does_not_split_three_instruction_template():
    scheduler = CampaignFillerScheduler()

    due = scheduler.schedule_after_template(3)

    assert due == 0
    assert scheduler.targeted_instruction_count == 3
    assert scheduler.scheduled_filler_count == 0


def test_scheduler_accumulates_across_template_boundaries():
    scheduler = CampaignFillerScheduler()

    assert scheduler.schedule_after_template(2) == 0

    # Cumulative targeted instructions = 5.
    assert scheduler.schedule_after_template(3) == 1

    assert scheduler.targeted_instruction_count == 5
    assert scheduler.scheduled_filler_count == 1


def test_scheduler_can_schedule_multiple_fillers_after_large_template():
    scheduler = CampaignFillerScheduler()

    due = scheduler.schedule_after_template(9)

    assert due == 2
    assert scheduler.targeted_instruction_count == 9
    assert scheduler.scheduled_filler_count == 2


def test_scheduler_matches_floor_cumulative_ratio():
    scheduler = CampaignFillerScheduler()

    template_lengths = [2, 3, 2, 3, 3, 2, 4]

    for length in template_lengths:
        scheduler.schedule_after_template(length)

        expected_fillers = (
            scheduler.targeted_instruction_count // 4
        )

        assert (
            scheduler.scheduled_filler_count
            == expected_fillers
        )


def test_scheduler_never_exceeds_twenty_percent_filler():
    scheduler = CampaignFillerScheduler()

    for _ in range(100):
        scheduler.schedule_after_template(3)

        assert scheduler.filler_fraction <= 0.20


@pytest.mark.parametrize("invalid_count", [0, -1, -10])
def test_scheduler_rejects_nonpositive_template_length(
    invalid_count,
):
    scheduler = CampaignFillerScheduler()

    with pytest.raises(ValueError):
        scheduler.schedule_after_template(invalid_count)


def test_scheduler_rejects_impossible_initial_accounting():
    with pytest.raises(ValueError):
        CampaignFillerScheduler(
            targeted_instruction_count=3,
            scheduled_filler_count=1,
        )


def test_two_equal_sequences_produce_identical_schedule():
    scheduler_a = CampaignFillerScheduler()
    scheduler_b = CampaignFillerScheduler()

    lengths = [2, 3, 3, 2, 4, 2, 3, 5]

    trace_a = [
        scheduler_a.schedule_after_template(length)
        for length in lengths
    ]

    trace_b = [
        scheduler_b.schedule_after_template(length)
        for length in lengths
    ]

    assert trace_a == trace_b
    assert scheduler_a == scheduler_b
