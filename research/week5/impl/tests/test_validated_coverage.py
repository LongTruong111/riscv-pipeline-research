from research.week5.impl.l1_coverage import L1Hit
from research.week5.impl.validated_coverage import (
    L1ValidatedCoverageCollector,
)


def hit(
    bin_id,
    consumer,
    producers,
    sources=("RS1",),
):
    return L1Hit(
        bin_id=bin_id,
        consumer_instruction_index=consumer,
        producer_instruction_indices=tuple(producers),
        matched_sources=tuple(sources),
    )


def record_base(
    collector,
    instruction_indices,
    *,
    failed=None,
):
    failed = failed or set()
    outcomes = []

    for instruction_index in instruction_indices:
        for kind in (
            "pc",
            "store",
            "writeback",
        ):
            outcomes.extend(
                collector.record_architectural_result(
                    instruction_index=instruction_index,
                    kind=kind,
                    passed=(
                        (
                            instruction_index,
                            kind,
                        )
                        not in failed
                    ),
                )
            )

    return tuple(outcomes)

def test_initial_state():
    collector = L1ValidatedCoverageCollector()

    assert collector.validated_bins == 0
    assert collector.validated_coverage == 0.0
    assert collector.pending_hits == 0
    assert collector.rejected_hits == 0


def test_control_failure_rejects_immediately():
    collector = L1ValidatedCoverageCollector()

    outcomes = collector.register_hit(
        hit(
            "H20",
            consumer=2,
            producers=(1,),
            sources=("RAW_RS2_UNUSED",),
        ),
        control_passed=False,
    )

    assert len(outcomes) == 1
    assert not outcomes[0].validated
    assert not outcomes[0].control_passed
    assert outcomes[0].architectural_passed is None

    assert collector.pending_hits == 0
    assert collector.validation_attempt_count["H20"] == 1
    assert collector.rejected_hit_count["H20"] == 1
    assert not collector.validated_seen["H20"]


def test_control_and_architecture_pass_promotes_hit():
    collector = L1ValidatedCoverageCollector()

    outcomes = collector.register_hit(
        hit(
            "H01",
            consumer=2,
            producers=(1,),
        ),
        control_passed=True,
    )

    assert outcomes == ()
    assert collector.pending_hits == 1

    outcomes = record_base(
        collector,
        (1, 2),
    )

    assert len(outcomes) == 1

    result = outcomes[0]

    assert result.bin_id == "H01"
    assert result.control_passed
    assert result.architectural_passed
    assert result.validated

    assert collector.pending_hits == 0
    assert collector.validated_seen["H01"]
    assert collector.validated_hit_count["H01"] == 1
    assert collector.validated_bins == 1


def test_architectural_failure_rejects_hit():
    collector = L1ValidatedCoverageCollector()

    collector.register_hit(
        hit(
            "H11",
            consumer=2,
            producers=(1,),
        ),
        control_passed=True,
    )

    outcomes = record_base(
        collector,
        (1, 2),
        failed={
            (
                2,
                "writeback",
            ),
        },
    )

    assert len(outcomes) == 1

    result = outcomes[0]

    assert not result.validated
    assert result.control_passed
    assert result.architectural_passed is False

    assert (
        2,
        "writeback",
    ) in result.failed_architectural_checks

    assert not collector.validated_seen["H11"]
    assert collector.rejected_hit_count["H11"] == 1


def test_h18_requires_x0_evidence():
    collector = L1ValidatedCoverageCollector()

    collector.register_hit(
        hit(
            "H18",
            consumer=2,
            producers=(1,),
        ),
        control_passed=True,
    )

    outcomes = record_base(
        collector,
        (1, 2),
    )

    # H18 cannot be promoted before x0 state evidence exists.
    assert outcomes == ()
    assert collector.pending_hits == 1

    outcomes = collector.record_architectural_result(
        instruction_index=1,
        kind="x0",
        passed=True,
    )

    assert outcomes == ()
    assert collector.pending_hits == 1

    outcomes = collector.record_architectural_result(
        instruction_index=2,
        kind="x0",
        passed=False,
    )

    assert len(outcomes) == 1

    result = outcomes[0]

    assert not result.validated
    assert result.architectural_passed is False

    assert (
        2,
        "x0",
    ) in result.failed_architectural_checks

    assert not collector.validated_seen["H18"]


def test_later_good_hit_can_validate_bin_after_earlier_failure():
    collector = L1ValidatedCoverageCollector()

    first = collector.register_hit(
        hit(
            "H20",
            consumer=2,
            producers=(1,),
            sources=("RAW_RS2_UNUSED",),
        ),
        control_passed=False,
    )

    assert len(first) == 1
    assert not first[0].validated
    assert not collector.validated_seen["H20"]

    collector.register_hit(
        hit(
            "H20",
            consumer=4,
            producers=(3,),
            sources=("RAW_RS2_UNUSED",),
        ),
        control_passed=True,
    )

    second = record_base(
        collector,
        (3, 4),
    )

    assert len(second) == 1
    assert second[0].validated

    assert collector.validation_attempt_count["H20"] == 2
    assert collector.rejected_hit_count["H20"] == 1
    assert collector.validated_hit_count["H20"] == 1
    assert collector.validated_seen["H20"]


def test_prune_bounds_old_architectural_results():
    collector = L1ValidatedCoverageCollector()

    for instruction_index in range(1, 21):
        collector.record_architectural_result(
            instruction_index=instruction_index,
            kind="pc",
            passed=True,
        )

    assert collector.architectural_cache_entries == 20

    collector.prune(
        latest_instruction_index=20
    )

    # Retain indices 16..20.
    assert collector.architectural_cache_entries == 5
