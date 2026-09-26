from __future__ import annotations

from typing import Iterable, Tuple

from research.week5.impl.validated_coverage import (
    L1ValidatedCoverageCollector,
)
from research.week7.retire_monitor import (
    RetireMonitor,
)
from research.week7.timing_oracle_v1 import (
    RETIRE_LATENCY,
)
from research.week9.benchmark.streaming_functional import (
    StreamingFunctionalScoreboard,
)
from research.week9.benchmark.streaming_timing import (
    StreamingPerformanceMonitor,
)
from research.week10.l2_realization import (
    L2ValidatedCoverageChecker,
)

from research.week13.campaign.invariant_ledger import (
    CampaignLifecycleSnapshot,
    HitLifecycleSnapshot,
)


# Frozen timing authority.
#
# Do not duplicate the literal value here. The Week-7 timing oracle
# defines the accepted-to-retire latency used by the campaign.
CAMPAIGN_MAX_IN_FLIGHT_DEPTH = RETIRE_LATENCY


class SnapshotAdapterProtocolError(RuntimeError):
    """
    Raised when a frozen checker no longer exposes the state layout
    required by the Week-13 campaign snapshot adapter.

    This is infrastructure failure evidence, not DUT evidence.
    """


def _unique_positive_ids(
    values: Iterable[int],
    *,
    context: str,
) -> Tuple[int, ...]:
    result = []

    for value in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
        ):
            raise SnapshotAdapterProtocolError(
                f"{context}: participant IDs must be "
                f"positive integers, got {value!r}"
            )

        if value not in result:
            result.append(value)

    if not result:
        raise SnapshotAdapterProtocolError(
            f"{context}: pending hit has no participants"
        )

    return tuple(result)


def _l1_pending_participants(
    checker: L1ValidatedCoverageCollector,
) -> Tuple[Tuple[int, ...], ...]:
    """
    Extract participant IDs from unresolved L1 hits.

    Private-state access is deliberately isolated in this function so
    frozen Week-5 implementation coupling is explicit and testable.
    """
    pending = getattr(
        checker,
        "_pending_by_consumer",
        None,
    )

    if not isinstance(pending, dict):
        raise SnapshotAdapterProtocolError(
            "L1 _pending_by_consumer layout is unavailable"
        )

    result = []

    for consumer_id, hits in pending.items():
        if not isinstance(hits, list):
            raise SnapshotAdapterProtocolError(
                "L1 pending-hit bucket must be a list"
            )

        for hit in hits:
            try:
                hit_consumer = (
                    hit.consumer_instruction_index
                )
                producers = (
                    hit.producer_instruction_indices
                )
            except AttributeError as exc:
                raise SnapshotAdapterProtocolError(
                    "L1 pending-hit layout changed"
                ) from exc

            if hit_consumer != consumer_id:
                raise SnapshotAdapterProtocolError(
                    "L1 pending consumer key does not "
                    "match hit consumer: "
                    f"key={consumer_id}, "
                    f"hit={hit_consumer}"
                )

            result.append(
                _unique_positive_ids(
                    (
                        *producers,
                        hit_consumer,
                    ),
                    context="L1 pending hit",
                )
            )

    if len(result) != checker.pending_hits:
        raise SnapshotAdapterProtocolError(
            "L1 private/public pending counts disagree: "
            f"private={len(result)}, "
            f"public={checker.pending_hits}"
        )

    return tuple(result)


def _l2_pending_participants(
    checker: L2ValidatedCoverageChecker,
) -> Tuple[Tuple[int, ...], ...]:
    """
    Extract participant IDs from unresolved L2 required checks.

    Each _PendingHit already contains the authoritative required-check
    set for its producer and consumer. Repeated check kinds are reduced
    to unique instruction IDs.

    Private-state access is isolated here and guarded mechanically.
    """
    pending = getattr(
        checker,
        "_pending_by_consumer",
        None,
    )

    if not isinstance(pending, dict):
        raise SnapshotAdapterProtocolError(
            "L2 _pending_by_consumer layout is unavailable"
        )

    result = []

    for consumer_id, items in pending.items():
        if not isinstance(items, list):
            raise SnapshotAdapterProtocolError(
                "L2 pending-hit bucket must be a list"
            )

        for item in items:
            try:
                required_checks = item.required_checks
            except AttributeError as exc:
                raise SnapshotAdapterProtocolError(
                    "L2 pending-hit layout changed"
                ) from exc

            participant_ids = (
                _unique_positive_ids(
                    (
                        instruction_id
                        for instruction_id, _
                        in required_checks
                    ),
                    context="L2 pending hit",
                )
            )

            if consumer_id not in participant_ids:
                raise SnapshotAdapterProtocolError(
                    "L2 pending consumer key is absent "
                    "from required-check participants: "
                    f"consumer={consumer_id}, "
                    f"participants={participant_ids}"
                )

            result.append(
                participant_ids
            )

    if len(result) != checker.pending_hits:
        raise SnapshotAdapterProtocolError(
            "L2 private/public pending counts disagree: "
            f"private={len(result)}, "
            f"public={checker.pending_hits}"
        )

    return tuple(result)


def _l1_hit_snapshot(
    checker: L1ValidatedCoverageCollector,
) -> HitLifecycleSnapshot:
    registered = sum(
        checker.validation_attempt_count.values()
    )

    validated = sum(
        checker.validated_hit_count.values()
    )

    rejected = sum(
        checker.rejected_hit_count.values()
    )

    pending_participants = (
        _l1_pending_participants(
            checker
        )
    )

    return HitLifecycleSnapshot(
        registered=registered,
        validated=validated,
        rejected=rejected,
        pending=checker.pending_hits,
        pending_participants=(
            pending_participants
        ),
        # Frozen L1 prune() removes only stale architectural-result
        # cache entries. It contains no unresolved-hit prune path.
        pruned_mid_run=0,
    )


def _l2_hit_snapshot(
    checker: L2ValidatedCoverageChecker,
) -> HitLifecycleSnapshot:
    pending_participants = (
        _l2_pending_participants(
            checker
        )
    )

    return HitLifecycleSnapshot(
        registered=checker.attempt_count,
        validated=checker.validated_hit_count,
        rejected=checker.rejected_hit_count,
        pending=checker.pending_hits,
        pending_participants=(
            pending_participants
        ),
        # Frozen L2 prune() removes only stale architectural-result
        # cache entries. It contains no unresolved-hit prune path.
        pruned_mid_run=0,
    )


def build_campaign_lifecycle_snapshot(
    *,
    cycle: int,
    accepted: int,
    max_intent_consumer_id: int,
    retire_monitor: RetireMonitor,
    functional: StreamingFunctionalScoreboard,
    performance: StreamingPerformanceMonitor,
    l1_validated: L1ValidatedCoverageCollector,
    l2_validated: L2ValidatedCoverageChecker,
) -> CampaignLifecycleSnapshot:
    """
    Build one stable Week-13 lifecycle snapshot from authoritative
    frozen verification state.

    No campaign-length history is copied.

    Time:
        O(20 + P_L1 + P_L2)

    Since L1 has a frozen 20-bin domain and each pending hit has a
    bounded participant/check set, this is O(P_L1 + P_L2).

    Additional memory:
        O(P_L1 + P_L2)

    with P_L1/P_L2 bounded by unresolved live verification state.
    """
    if not isinstance(
        retire_monitor,
        RetireMonitor,
    ):
        raise TypeError(
            "retire_monitor must be RetireMonitor"
        )

    if not isinstance(
        functional,
        StreamingFunctionalScoreboard,
    ):
        raise TypeError(
            "functional must be "
            "StreamingFunctionalScoreboard"
        )

    if not isinstance(
        performance,
        StreamingPerformanceMonitor,
    ):
        raise TypeError(
            "performance must be "
            "StreamingPerformanceMonitor"
        )

    if not isinstance(
        l1_validated,
        L1ValidatedCoverageCollector,
    ):
        raise TypeError(
            "l1_validated must be "
            "L1ValidatedCoverageCollector"
        )

    if not isinstance(
        l2_validated,
        L2ValidatedCoverageChecker,
    ):
        raise TypeError(
            "l2_validated must be "
            "L2ValidatedCoverageChecker"
        )

    return CampaignLifecycleSnapshot(
        cycle=cycle,
        accepted=accepted,
        retired_checked=(
            retire_monitor.retired_count
        ),
        functional_checked=(
            functional.checked_count
        ),
        functional_pending=(
            functional.pending_expected_count
        ),
        performance_checked=(
            performance.checked_count
        ),
        performance_pending=(
            performance.pending_count
        ),
        max_intent_consumer_id=(
            max_intent_consumer_id
        ),
        l1=_l1_hit_snapshot(
            l1_validated
        ),
        l2=_l2_hit_snapshot(
            l2_validated
        ),
    )
