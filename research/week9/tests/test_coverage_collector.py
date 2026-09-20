import pytest

from research.week9.coverage_collector import CoverageCollector


def test_l1_universe_is_exactly_20_bins():
    collector = CoverageCollector()

    assert len(collector.l1_bins) == 20
    assert collector.l1_bins == tuple(f"H{i:02d}" for i in range(1, 21))


def test_l2_universe_is_exactly_62_bins():
    collector = CoverageCollector()

    assert len(collector.l2_bins) == 62

    expected = {
        (distance, register)
        for distance in ("d1", "d2")
        for register in range(1, 32)
    }

    assert set(collector.l2_bins) == expected


def test_l2_excludes_x0():
    collector = CoverageCollector()

    assert all(register != 0 for _, register in collector.l2_bins)


def test_first_l1_intent_hit_is_immutable():
    collector = CoverageCollector()

    collector.record_l1_intent(
        "H01",
        instruction_id=10,
        cycle=15,
        wall_ns=1000,
    )

    collector.record_l1_intent(
        "H01",
        instruction_id=20,
        cycle=30,
        wall_ns=2000,
    )

    state = collector.l1_state["H01"]

    assert state.intent_seen is True
    assert state.intent_first.instruction_id == 10
    assert state.intent_first.cycle == 15
    assert state.intent_first.wall_ns == 1000


def test_first_l1_validated_hit_is_independent_from_first_intent_hit():
    collector = CoverageCollector()

    collector.record_l1_intent(
        "H01",
        instruction_id=10,
        cycle=15,
        wall_ns=1000,
    )

    # First intended occurrence is not validated.
    collector.record_l1_intent(
        "H01",
        instruction_id=20,
        cycle=30,
        wall_ns=2000,
    )

    # A later occurrence successfully validates the same bin.
    collector.record_l1_validated(
        "H01",
        instruction_id=20,
        cycle=33,
        wall_ns=2500,
    )

    state = collector.l1_state["H01"]

    assert state.intent_first.instruction_id == 10
    assert state.validated_seen is True
    assert state.validated_first.instruction_id == 20
    assert state.validated_first.cycle == 33
    assert state.validated_first.wall_ns == 2500


def test_duplicate_validated_hit_does_not_overwrite_first_hit():
    collector = CoverageCollector()

    collector.record_l1_intent(
        "H03",
        instruction_id=8,
        cycle=9,
        wall_ns=50,
    )

    collector.record_l1_validated(
        "H03",
        instruction_id=8,
        cycle=12,
        wall_ns=100,
    )

    collector.record_l1_validated(
        "H03",
        instruction_id=50,
        cycle=90,
        wall_ns=999,
    )

    state = collector.l1_state["H03"]

    assert state.validated_first.instruction_id == 8
    assert state.validated_first.cycle == 12
    assert state.validated_first.wall_ns == 100

def test_l2_first_hit_tracking():
    collector = CoverageCollector()

    collector.record_l2_intent(
        "d2",
        31,
        instruction_id=42,
        cycle=100,
        wall_ns=5000,
    )

    state = collector.l2_state[("d2", 31)]

    assert state.intent_seen is True
    assert state.intent_first.instruction_id == 42
    assert state.intent_first.cycle == 100
    assert state.intent_first.wall_ns == 5000


@pytest.mark.parametrize(
    "distance,register",
    [
        ("d0", 1),
        ("d3", 1),
        ("d1", 0),
        ("d1", 32),
    ],
)
def test_invalid_l2_bin_is_rejected(distance, register):
    collector = CoverageCollector()

    with pytest.raises(ValueError):
        collector.record_l2_intent(
            distance,
            register,
            instruction_id=1,
            cycle=1,
            wall_ns=1,
        )


def test_invalid_l1_bin_is_rejected():
    collector = CoverageCollector()

    with pytest.raises(ValueError):
        collector.record_l1_intent(
            "H21",
            instruction_id=1,
            cycle=1,
            wall_ns=1,
        )


def test_checkpoint_exactly_every_1000_executed_instructions():
    collector = CoverageCollector(checkpoint_interval=1000)

    for instruction_id in range(1, 2501):
        collector.record_instruction(
            instruction_id=instruction_id,
            cycle=instruction_id + 3,
        )

    assert [cp.executed_instructions for cp in collector.checkpoints] == [
        1000,
        2000,
    ]


def test_checkpoint_contains_coverage_snapshot():
    collector = CoverageCollector(checkpoint_interval=1000)

    collector.record_l1_intent(
        "H01",
        instruction_id=1,
        cycle=1,
        wall_ns=100,
    )
    collector.record_l1_validated(
        "H01",
        instruction_id=1,
        cycle=4,
        wall_ns=200,
    )

    collector.record_l2_intent(
        "d1",
        5,
        instruction_id=2,
        cycle=2,
        wall_ns=300,
    )

    for instruction_id in range(1, 1001):
        collector.record_instruction(
            instruction_id=instruction_id,
            cycle=instruction_id + 3,
        )

    checkpoint = collector.checkpoints[0]

    assert checkpoint.executed_instructions == 1000
    assert checkpoint.l1_intent_count == 1
    assert checkpoint.l1_validated_count == 1
    assert checkpoint.l2_intent_count == 1
    assert checkpoint.l2_validated_count == 0


def test_instruction_ids_must_be_strictly_contiguous():
    collector = CoverageCollector()

    collector.record_instruction(instruction_id=1, cycle=4)

    with pytest.raises(ValueError):
        collector.record_instruction(instruction_id=3, cycle=6)


def test_same_semantic_stream_produces_same_deterministic_state():
    def build_collector(wall_offset):
        collector = CoverageCollector(checkpoint_interval=1000)

        collector.record_l1_intent(
            "H06",
            instruction_id=2,
            cycle=3,
            wall_ns=100 + wall_offset,
        )
        collector.record_l1_validated(
            "H06",
            instruction_id=2,
            cycle=6,
            wall_ns=200 + wall_offset,
        )
        collector.record_l2_intent(
            "d1",
            7,
            instruction_id=2,
            cycle=3,
            wall_ns=300 + wall_offset,
        )

        for instruction_id in range(1, 1001):
            collector.record_instruction(
                instruction_id=instruction_id,
                cycle=instruction_id + 3,
            )

        return collector

    a = build_collector(0)
    b = build_collector(999999)

    # Wall time is deliberately excluded from deterministic comparison.
    assert a.deterministic_snapshot() == b.deterministic_snapshot()


def test_l1_validated_before_intent_is_rejected():
    collector = CoverageCollector()

    with pytest.raises(ValueError):
        collector.record_l1_validated(
            "H01",
            instruction_id=1,
            cycle=4,
            wall_ns=100,
        )


def test_l2_validated_before_intent_is_rejected():
    collector = CoverageCollector()

    with pytest.raises(ValueError):
        collector.record_l2_validated(
            "d1",
            5,
            instruction_id=1,
            cycle=4,
            wall_ns=100,
        )


def test_checkpoint_can_be_streamed_without_retention():
    emitted = []

    collector = CoverageCollector(
        checkpoint_interval=1000,
        retain_checkpoints=False,
        checkpoint_sink=emitted.append,
    )

    for instruction_id in range(1, 2001):
        collector.record_instruction(
            instruction_id=instruction_id,
            cycle=instruction_id + 3,
        )

    assert collector.checkpoints == []
    assert [
        cp.executed_instructions
        for cp in emitted
    ] == [1000, 2000]


def test_checkpoint_streaming_does_not_change_coverage_state():
    emitted = []

    collector = CoverageCollector(
        checkpoint_interval=1000,
        retain_checkpoints=False,
        checkpoint_sink=emitted.append,
    )

    collector.record_l1_intent(
        "H01",
        instruction_id=1,
        cycle=1,
        wall_ns=100,
    )

    collector.record_l1_validated(
        "H01",
        instruction_id=1,
        cycle=4,
        wall_ns=200,
    )

    for instruction_id in range(1, 1001):
        collector.record_instruction(
            instruction_id=instruction_id,
            cycle=instruction_id + 3,
        )

    assert collector.l1_state["H01"].intent_seen is True
    assert collector.l1_state["H01"].validated_seen is True

    assert len(emitted) == 1
    assert emitted[0].l1_intent_count == 1
    assert emitted[0].l1_validated_count == 1
