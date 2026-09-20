import pytest

from research.week5.impl.l1_coverage import L1Hit
from research.week5.impl.validated_coverage import (
    L1ValidationOutcome,
)
from research.week7.hazard_attribution import (
    AttributionCheck,
    HazardAttribution,
)
from research.week8.performance_monitor import (
    PerformanceResult,
)

from research.week9.coverage_collector import (
    CoverageCollector,
)
from research.week9.live_coverage_coordinator import (
    LiveCoverageCoordinator,
)
from research.week9.validated_attribution import (
    ValidationStatus,
)


def make_hit(
    *,
    bin_id="H01",
    consumer_id=2,
    producer_ids=(1,),
    sources=("RS1",),
):
    return L1Hit(
        bin_id=bin_id,
        consumer_instruction_index=consumer_id,
        producer_instruction_indices=tuple(
            producer_ids
        ),
        matched_sources=tuple(sources),
    )


def make_validation(
    *,
    bin_id="H01",
    consumer_id=2,
    producer_ids=(1,),
    control_passed=True,
    architectural_passed=True,
    validated=True,
    failed_arch=(),
):
    return L1ValidationOutcome(
        bin_id=bin_id,
        consumer_instruction_index=consumer_id,
        producer_instruction_indices=tuple(
            producer_ids
        ),
        control_passed=control_passed,
        architectural_passed=architectural_passed,
        validated=validated,
        failed_architectural_checks=tuple(
            failed_arch
        ),
    )


def make_hazard(
    *,
    bin_id="H01",
    consumer_id=2,
    producer_ids=(1,),
    source="RS1",
    retire_delta=0,
):
    forward_name = (
        "forward_a"
        if source == "RS1"
        else "forward_b"
    )

    return HazardAttribution(
        bin_id=bin_id,
        consumer_instruction_id=consumer_id,
        producer_instruction_ids=tuple(
            producer_ids
        ),
        matched_sources=(source,),
        checks=(
            AttributionCheck(
                name=forward_name,
                expected=2,
                observed=2,
            ),
            AttributionCheck(
                name="retire_cycle",
                expected=5,
                observed=5 + retire_delta,
            ),
        ),
    )


def make_performance(
    *,
    instruction_id=2,
    delta=0,
):
    return PerformanceResult(
        instruction_id=instruction_id,
        expected_retire_cycle=5,
        observed_retire_cycle=5 + delta,
        delta_cycles=delta,
    )


def test_register_intent_records_coverage_and_pending_hit():
    coverage = CoverageCollector()

    coordinator = LiveCoverageCoordinator(
        coverage=coverage
    )

    coordinator.register_l1_intent(
        make_hit(),
        cycle=2,
        wall_ns=100,
    )

    state = coverage.l1_state["H01"]

    assert state.intent_seen is True
    assert state.intent_first.instruction_id == 2
    assert state.intent_first.cycle == 2
    assert state.intent_first.wall_ns == 100

    assert coordinator.pending_hit_count == 1


def test_authoritative_validation_promotes_before_diagnostics_complete():
    coverage = CoverageCollector()

    coordinator = LiveCoverageCoordinator(
        coverage=coverage
    )

    coordinator.register_l1_intent(
        make_hit(),
        cycle=2,
        wall_ns=100,
    )

    records = coordinator.record_validation(
        make_validation(),
        resolution_cycle=5,
        wall_ns=180,
    )

    # Coverage promotion does not wait for optional Week-7/8
    # diagnostic completion.
    assert records == ()

    state = coverage.l1_state["H01"]

    assert state.validated_seen is True
    assert state.validated_first.instruction_id == 2
    assert state.validated_first.cycle == 5
    assert state.validated_first.wall_ns == 180

    # The concrete hit remains transiently pending until its
    # hazard/performance diagnostics are correlated.
    assert coordinator.pending_hit_count == 1


def test_full_evidence_emits_final_record_and_releases_hit():
    coverage = CoverageCollector()

    coordinator = LiveCoverageCoordinator(
        coverage=coverage
    )

    coordinator.register_l1_intent(
        make_hit(),
        cycle=2,
        wall_ns=100,
    )

    assert coordinator.record_validation(
        make_validation(),
        resolution_cycle=5,
        wall_ns=180,
    ) == ()

    assert coordinator.record_hazard(
        make_hazard()
    ) == ()

    records = coordinator.record_performance(
        make_performance()
    )

    assert len(records) == 1

    record = records[0]

    assert record.intent_bin == "H01"
    assert record.validated is True
    assert record.validated_bin == "H01"

    assert (
        record.status
        == ValidationStatus.REALIZED_CORRECTLY
    )

    assert coordinator.pending_hit_count == 0


def test_producer_architectural_failure_blocks_promotion():
    coverage = CoverageCollector()

    coordinator = LiveCoverageCoordinator(
        coverage=coverage
    )

    coordinator.register_l1_intent(
        make_hit(),
        cycle=2,
        wall_ns=100,
    )

    coordinator.record_validation(
        make_validation(
            architectural_passed=False,
            validated=False,
            failed_arch=(
                (1, "writeback"),
            ),
        ),
        resolution_cycle=5,
        wall_ns=180,
    )

    coordinator.record_hazard(
        make_hazard()
    )

    records = coordinator.record_performance(
        make_performance()
    )

    assert len(records) == 1

    record = records[0]

    assert record.validated is False
    assert record.validated_bin is None

    assert (
        record.status
        == ValidationStatus.FUNCTIONAL_MISMATCH
    )

    assert (
        "1:writeback"
        in record.failed_functional_checks
    )

    assert (
        coverage.l1_state["H01"].validated_seen
        is False
    )

    assert coordinator.pending_hit_count == 0


def test_later_timing_mismatch_does_not_erase_frozen_validation():
    coverage = CoverageCollector()

    coordinator = LiveCoverageCoordinator(
        coverage=coverage
    )

    coordinator.register_l1_intent(
        make_hit(),
        cycle=2,
        wall_ns=100,
    )

    coordinator.record_validation(
        make_validation(),
        resolution_cycle=5,
        wall_ns=180,
    )

    coordinator.record_hazard(
        make_hazard(
            retire_delta=1,
        )
    )

    records = coordinator.record_performance(
        make_performance(
            delta=1,
        )
    )

    assert len(records) == 1

    record = records[0]

    assert record.validated is True
    assert record.validated_bin == "H01"

    assert (
        record.status
        == ValidationStatus.TIMING_MISMATCH
    )

    assert (
        coverage.l1_state["H01"].validated_seen
        is True
    )

    assert coordinator.pending_hit_count == 0


def test_diagnostic_evidence_order_does_not_change_result():
    coverage = CoverageCollector()

    coordinator = LiveCoverageCoordinator(
        coverage=coverage
    )

    coordinator.register_l1_intent(
        make_hit(),
        cycle=2,
        wall_ns=100,
    )

    assert coordinator.record_performance(
        make_performance()
    ) == ()

    assert coordinator.record_hazard(
        make_hazard()
    ) == ()

    records = coordinator.record_validation(
        make_validation(),
        resolution_cycle=5,
        wall_ns=180,
    )

    assert len(records) == 1

    record = records[0]

    assert record.validated is True

    assert (
        record.status
        == ValidationStatus.REALIZED_CORRECTLY
    )

    assert coordinator.pending_hit_count == 0


def test_multiple_bins_for_one_consumer_finalize_independently():
    coverage = CoverageCollector()

    coordinator = LiveCoverageCoordinator(
        coverage=coverage
    )

    hit_a = make_hit(
        bin_id="H01",
        sources=("RS1",),
    )

    hit_b = make_hit(
        bin_id="H02",
        sources=("RS2",),
    )

    coordinator.register_l1_intent(
        hit_a,
        cycle=2,
        wall_ns=100,
    )

    coordinator.register_l1_intent(
        hit_b,
        cycle=2,
        wall_ns=100,
    )

    assert coordinator.pending_hit_count == 2

    coordinator.record_validation(
        make_validation(
            bin_id="H01",
        ),
        resolution_cycle=5,
        wall_ns=180,
    )

    coordinator.record_validation(
        make_validation(
            bin_id="H02",
        ),
        resolution_cycle=5,
        wall_ns=180,
    )

    coordinator.record_performance(
        make_performance()
    )

    first = coordinator.record_hazard(
        make_hazard(
            bin_id="H01",
            source="RS1",
        )
    )

    second = coordinator.record_hazard(
        make_hazard(
            bin_id="H02",
            source="RS2",
        )
    )

    assert len(first) == 1
    assert len(second) == 1

    assert first[0].intent_bin == "H01"
    assert second[0].intent_bin == "H02"

    assert coordinator.pending_hit_count == 0


def test_unregistered_validation_is_rejected():
    coordinator = LiveCoverageCoordinator(
        coverage=CoverageCollector()
    )

    with pytest.raises(ValueError):
        coordinator.record_validation(
            make_validation(),
            resolution_cycle=5,
            wall_ns=180,
        )


def test_duplicate_intent_registration_is_rejected():
    coordinator = LiveCoverageCoordinator(
        coverage=CoverageCollector()
    )

    hit = make_hit()

    coordinator.register_l1_intent(
        hit,
        cycle=2,
        wall_ns=100,
    )

    with pytest.raises(ValueError):
        coordinator.register_l1_intent(
            hit,
            cycle=2,
            wall_ns=100,
        )

def test_long_stream_does_not_accumulate_transient_state():
    coverage = CoverageCollector()

    coordinator = LiveCoverageCoordinator(
        coverage=coverage
    )

    max_pending = 0
    max_performance = 0

    instruction_count = 10_000

    for offset in range(instruction_count):
        consumer_id = offset + 2
        producer_id = consumer_id - 1

        hit = make_hit(
            consumer_id=consumer_id,
            producer_ids=(producer_id,),
        )

        validation = make_validation(
            consumer_id=consumer_id,
            producer_ids=(producer_id,),
        )

        hazard = make_hazard(
            consumer_id=consumer_id,
            producer_ids=(producer_id,),
        )

        performance = make_performance(
            instruction_id=consumer_id,
        )

        coordinator.register_l1_intent(
            hit,
            cycle=consumer_id,
            wall_ns=consumer_id * 10,
        )

        # Deliberately deliver performance first so that the
        # coordinator must retain it temporarily.
        assert coordinator.record_performance(
            performance
        ) == ()

        max_pending = max(
            max_pending,
            coordinator.pending_hit_count,
        )

        max_performance = max(
            max_performance,
            coordinator.retained_performance_count,
        )

        assert coordinator.record_hazard(
            hazard
        ) == ()

        records = coordinator.record_validation(
            validation,
            resolution_cycle=consumer_id + 3,
            wall_ns=consumer_id * 10 + 5,
        )

        assert len(records) == 1

        # Every completed concrete hit must release all
        # transient evidence before the next iteration.
        assert coordinator.pending_hit_count == 0
        assert coordinator.retained_performance_count == 0

    assert max_pending <= 1
    assert max_performance <= 1

    state = coverage.l1_state["H01"]

    assert state.intent_seen is True
    assert state.validated_seen is True

    # First-hit metadata must remain immutable despite 10k
    # later occurrences of the same bin.
    assert state.intent_first.instruction_id == 2
    assert state.validated_first.instruction_id == 2


def test_shared_performance_is_retained_until_last_sibling_hit_finishes():
    coverage = CoverageCollector()

    coordinator = LiveCoverageCoordinator(
        coverage=coverage
    )

    hit_a = make_hit(
        bin_id="H01",
        sources=("RS1",),
    )

    hit_b = make_hit(
        bin_id="H02",
        sources=("RS2",),
    )

    coordinator.register_l1_intent(
        hit_a,
        cycle=2,
        wall_ns=100,
    )

    coordinator.register_l1_intent(
        hit_b,
        cycle=2,
        wall_ns=100,
    )

    # One retirement-performance result belongs to the shared
    # consumer and must remain available until both hits finish.
    assert coordinator.record_performance(
        make_performance()
    ) == ()

    assert coordinator.pending_hit_count == 2
    assert coordinator.retained_performance_count == 1

    coordinator.record_validation(
        make_validation(
            bin_id="H01",
        ),
        resolution_cycle=5,
        wall_ns=180,
    )

    records_a = coordinator.record_hazard(
        make_hazard(
            bin_id="H01",
            source="RS1",
        )
    )

    assert len(records_a) == 1
    assert coordinator.pending_hit_count == 1

    # H02 still needs the same performance result.
    assert coordinator.retained_performance_count == 1

    coordinator.record_validation(
        make_validation(
            bin_id="H02",
        ),
        resolution_cycle=5,
        wall_ns=180,
    )

    records_b = coordinator.record_hazard(
        make_hazard(
            bin_id="H02",
            source="RS2",
        )
    )

    assert len(records_b) == 1

    assert coordinator.pending_hit_count == 0
    assert coordinator.retained_performance_count == 0


def test_unknown_performance_cannot_accumulate_state():
    coordinator = LiveCoverageCoordinator(
        coverage=CoverageCollector()
    )

    with pytest.raises(ValueError):
        coordinator.record_performance(
            make_performance(
                instruction_id=99,
            )
        )

    assert coordinator.pending_hit_count == 0
    assert coordinator.retained_performance_count == 0
