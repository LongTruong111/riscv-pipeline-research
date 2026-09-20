import pytest

from research.week5.impl.coverage_model import (
    L2CoverageCollector,
    l2_bin_index,
)
from research.week5.impl.execution_event import ExecutionEvent


def event(
    index,
    *,
    rs1=0,
    rs2=0,
    rd=0,
    uses_rs1=False,
    uses_rs2=False,
    writes_rd=False,
    producer_type="NONE",
    consumer_type="NONE",
):
    return ExecutionEvent(
        instruction_index=index,
        cycle=index,
        pc=((index - 1) * 4) & 0x1FF,
        instruction=0x00000013,
        rs1=rs1,
        rs2=rs2,
        rd=rd,
        uses_rs1=uses_rs1,
        uses_rs2=uses_rs2,
        writes_rd=writes_rd,
        producer_type=producer_type,
        consumer_type=consumer_type,
    )


def test_frozen_bin_index_mapping():
    assert l2_bin_index(1, 1) == 0
    assert l2_bin_index(1, 31) == 30
    assert l2_bin_index(2, 1) == 31
    assert l2_bin_index(2, 31) == 61


def test_d1_dependency_hits_expected_bin():
    cov = L2CoverageCollector()

    cov.observe(
        event(
            1,
            rd=5,
            writes_rd=True,
            producer_type="ALU_RESULT",
        )
    )

    hits = cov.observe(
        event(
            2,
            rs1=5,
            uses_rs1=True,
            consumer_type="RS1_ONLY",
        )
    )

    assert len(hits) == 1
    assert hits[0].distance == 1
    assert hits[0].register == 5
    assert hits[0].bin_index == l2_bin_index(1, 5)
    assert cov.intent_bins == 1


def test_d2_dependency_hits_expected_bin():
    cov = L2CoverageCollector()

    cov.observe(
        event(
            1,
            rd=31,
            writes_rd=True,
            producer_type="ALU_RESULT",
        )
    )

    cov.observe(event(2))

    hits = cov.observe(
        event(
            3,
            rs2=31,
            uses_rs2=True,
            consumer_type="RS1_RS2",
        )
    )

    assert len(hits) == 1
    assert hits[0].distance == 2
    assert hits[0].register == 31
    assert hits[0].bin_index == 61


def test_x0_never_creates_positive_l2_dependency():
    cov = L2CoverageCollector()

    cov.observe(
        event(
            1,
            rd=0,
            writes_rd=True,
            producer_type="ALU_RESULT",
        )
    )

    hits = cov.observe(
        event(
            2,
            rs1=0,
            uses_rs1=True,
            consumer_type="RS1_ONLY",
        )
    )

    assert hits == ()
    assert cov.intent_bins == 0


def test_latest_writer_shadows_older_writer():
    cov = L2CoverageCollector()

    cov.observe(
        event(
            1,
            rd=5,
            writes_rd=True,
            producer_type="ALU_RESULT",
        )
    )

    cov.observe(
        event(
            2,
            rd=5,
            writes_rd=True,
            producer_type="ALU_RESULT",
        )
    )

    hits = cov.observe(
        event(
            3,
            rs1=5,
            uses_rs1=True,
            consumer_type="RS1_ONLY",
        )
    )

    assert len(hits) == 1
    assert hits[0].distance == 1
    assert hits[0].producer_instruction_index == 2

    assert cov.intent_seen[l2_bin_index(1, 5)]
    assert not cov.intent_seen[l2_bin_index(2, 5)]


def test_same_register_in_rs1_and_rs2_counts_once():
    cov = L2CoverageCollector()

    cov.observe(
        event(
            1,
            rd=7,
            writes_rd=True,
            producer_type="ALU_RESULT",
        )
    )

    hits = cov.observe(
        event(
            2,
            rs1=7,
            rs2=7,
            uses_rs1=True,
            uses_rs2=True,
            consumer_type="RS1_RS2",
        )
    )

    index = l2_bin_index(1, 7)

    assert len(hits) == 1
    assert cov.intent_hit_count[index] == 1


def test_dual_source_consumer_can_create_d1_and_d2_hits():
    cov = L2CoverageCollector()

    cov.observe(
        event(
            1,
            rd=1,
            writes_rd=True,
            producer_type="ALU_RESULT",
        )
    )

    cov.observe(
        event(
            2,
            rd=2,
            writes_rd=True,
            producer_type="ALU_RESULT",
        )
    )

    hits = cov.observe(
        event(
            3,
            rs1=2,
            rs2=1,
            uses_rs1=True,
            uses_rs2=True,
            consumer_type="RS1_RS2",
        )
    )

    got = {(hit.distance, hit.register) for hit in hits}

    assert got == {
        (1, 2),
        (2, 1),
    }


def test_read_before_write_when_instruction_uses_and_writes_same_register():
    cov = L2CoverageCollector()

    cov.observe(
        event(
            1,
            rd=5,
            writes_rd=True,
            producer_type="ALU_RESULT",
        )
    )

    hits = cov.observe(
        event(
            2,
            rs1=5,
            rd=5,
            uses_rs1=True,
            writes_rd=True,
            producer_type="ALU_RESULT",
            consumer_type="RS1_ONLY",
        )
    )

    assert len(hits) == 1
    assert hits[0].producer_instruction_index == 1

    next_hits = cov.observe(
        event(
            3,
            rs1=5,
            uses_rs1=True,
            consumer_type="RS1_ONLY",
        )
    )

    assert len(next_hits) == 1
    assert next_hits[0].producer_instruction_index == 2


def test_validated_promotion_is_separate_from_intent():
    cov = L2CoverageCollector()

    cov.observe(
        event(
            1,
            rd=5,
            writes_rd=True,
            producer_type="IMM",
        )
    )

    hits = cov.observe(
        event(
            2,
            rs1=5,
            uses_rs1=True,
            consumer_type="RS1_ONLY",
        )
    )

    index = l2_bin_index(1, 5)

    assert cov.intent_seen[index]
    assert not cov.validated_seen[index]

    cov.promote_validated(hits)

    assert cov.validated_seen[index]
    assert cov.validated_hit_count[index] == 1


def test_non_contiguous_execution_stream_is_rejected():
    cov = L2CoverageCollector()

    cov.observe(event(1))

    with pytest.raises(ValueError):
        cov.observe(event(3))
