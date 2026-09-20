"""Bounded Week-9 live L1 coverage coordination.

This module owns correlation state only.

It does NOT:
- classify L1 semantics;
- recompute frozen Week-5 realization;
- recompute Week-7 hazard attribution;
- recompute Week-8 retirement performance.

Authoritative frozen Validated Coverage comes only from
L1ValidationOutcome.

The coordinator:
1. records L1 Intent metadata;
2. accepts authoritative Week-5 validation outcomes;
3. promotes coverage immediately when frozen validation succeeds;
4. correlates optional Week-7/Week-8 diagnostic evidence;
5. emits one final ValidatedAttributionRecord per concrete L1 hit;
6. releases transient per-hit state after final attribution.

For a correctly operating live pipeline, retained state is bounded by
the number of unresolved/in-flight concrete hits, not campaign length.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from research.week5.impl.l1_coverage import L1Hit
from research.week5.impl.validated_coverage import (
    L1ValidationOutcome,
)
from research.week7.hazard_attribution import (
    HazardAttribution,
)
from research.week8.performance_monitor import (
    PerformanceResult,
)

from research.week9.coverage_collector import (
    CoverageCollector,
)
from research.week9.coverage_promotion import (
    promote_l1_attribution,
)
from research.week9.validated_attribution import (
    ValidatedAttributionRecord,
    attribute_l1_hit,
)


@dataclass(frozen=True, slots=True)
class _HitKey:
    """Identity of one concrete L1 Intent hit."""

    bin_id: str
    consumer_instruction_id: int
    producer_instruction_ids: Tuple[int, ...]
    matched_sources: Tuple[str, ...]


@dataclass(slots=True)
class _PendingHit:
    """Transient evidence for one concrete L1 hit."""

    hit: L1Hit
    validation: Optional[L1ValidationOutcome] = None
    hazard: Optional[HazardAttribution] = None


class LiveCoverageCoordinator:
    """Correlate frozen validation and independent diagnostic evidence.

    Complexity:
        Register/lookup for one concrete hit:
            O(1) average dictionary access.

        Performance-result fanout:
            O(H_consumer), where H_consumer is the number of L1 hits
            associated with one consumer. The frozen L1 model bounds
            this independently of campaign length.

        Campaign:
            O(N).

    Retained state:
        pending concrete hits + performance evidence for consumers that
        still have unresolved hits.

    Therefore, under the frozen bounded pipeline/hazard model and timely
    evidence delivery, retained coordinator state is O(1) with respect
    to campaign length.
    """

    def __init__(
        self,
        *,
        coverage: CoverageCollector,
    ) -> None:
        if not isinstance(coverage, CoverageCollector):
            raise TypeError(
                "coverage must be a CoverageCollector"
            )

        self.coverage = coverage

        self._pending: Dict[
            _HitKey,
            _PendingHit,
        ] = {}

        # One PerformanceResult belongs to an instruction/consumer and
        # may therefore serve multiple L1 hits produced by that same
        # instruction.
        self._performance_by_consumer: Dict[
            int,
            PerformanceResult,
        ] = {}

    @property
    def pending_hit_count(self) -> int:
        return len(self._pending)

    @property
    def retained_performance_count(self) -> int:
        return len(self._performance_by_consumer)

    @staticmethod
    def _key_from_hit(
        hit: L1Hit,
    ) -> _HitKey:
        return _HitKey(
            bin_id=hit.bin_id,
            consumer_instruction_id=(
                hit.consumer_instruction_index
            ),
            producer_instruction_ids=tuple(
                hit.producer_instruction_indices
            ),
            matched_sources=tuple(
                hit.matched_sources
            ),
        )

    @staticmethod
    def _key_from_hazard(
        hazard: HazardAttribution,
    ) -> _HitKey:
        return _HitKey(
            bin_id=hazard.bin_id,
            consumer_instruction_id=(
                hazard.consumer_instruction_id
            ),
            producer_instruction_ids=tuple(
                hazard.producer_instruction_ids
            ),
            matched_sources=tuple(
                hazard.matched_sources
            ),
        )

    def _keys_for_consumer(
        self,
        instruction_id: int,
    ) -> Tuple[_HitKey, ...]:
        return tuple(
            key
            for key in self._pending
            if (
                key.consumer_instruction_id
                == instruction_id
            )
        )

    def _find_validation_key(
        self,
        validation: L1ValidationOutcome,
    ) -> _HitKey:
        """Resolve a validation outcome to exactly one pending hit.

        L1ValidationOutcome does not carry matched_sources, so identity
        is resolved using bin + consumer + producer identities.

        If that identity is ambiguous, silently choosing a hit would
        corrupt attribution, therefore ambiguity is a protocol error.
        """

        matches = tuple(
            key
            for key in self._pending
            if (
                key.bin_id == validation.bin_id
                and key.consumer_instruction_id
                == validation.consumer_instruction_index
                and key.producer_instruction_ids
                == tuple(
                    validation.producer_instruction_indices
                )
            )
        )

        if not matches:
            raise ValueError(
                "validation has no registered L1 Intent hit: "
                f"bin={validation.bin_id}, "
                "consumer="
                f"{validation.consumer_instruction_index}, "
                "producers="
                f"{validation.producer_instruction_indices}"
            )

        if len(matches) != 1:
            raise ValueError(
                "validation identity is ambiguous across "
                "multiple registered L1 hits"
            )

        return matches[0]

    def _maybe_release_performance(
        self,
        instruction_id: int,
    ) -> None:
        if not self._keys_for_consumer(
            instruction_id
        ):
            self._performance_by_consumer.pop(
                instruction_id,
                None,
            )

    def _try_finalize(
        self,
        key: _HitKey,
    ) -> Tuple[
        ValidatedAttributionRecord,
        ...,
    ]:
        pending = self._pending.get(key)

        if pending is None:
            return ()

        if pending.validation is None:
            return ()

        if pending.hazard is None:
            return ()

        performance = (
            self._performance_by_consumer.get(
                key.consumer_instruction_id
            )
        )

        if performance is None:
            return ()

        record = attribute_l1_hit(
            bin_id=key.bin_id,
            instruction_id=(
                key.consumer_instruction_id
            ),
            validation=pending.validation,
            hazard=pending.hazard,
            performance=performance,
        )

        # Final attribution is complete. Discard all per-hit transient
        # evidence immediately.
        del self._pending[key]

        self._maybe_release_performance(
            key.consumer_instruction_id
        )

        return (record,)

    def register_l1_intent(
        self,
        hit: L1Hit,
        *,
        cycle: int,
        wall_ns: int,
    ) -> None:
        """Register one concrete L1 Intent hit."""

        if not isinstance(hit, L1Hit):
            raise TypeError(
                "hit must be an L1Hit"
            )

        key = self._key_from_hit(hit)

        if key in self._pending:
            raise ValueError(
                "duplicate concrete L1 Intent registration"
            )

        # CoverageCollector performs metadata validation and preserves
        # immutable first-hit semantics.
        self.coverage.record_l1_intent(
            hit.bin_id,
            instruction_id=(
                hit.consumer_instruction_index
            ),
            cycle=cycle,
            wall_ns=wall_ns,
        )

        self._pending[key] = _PendingHit(
            hit=hit
        )

    def record_validation(
        self,
        validation: L1ValidationOutcome,
        *,
        resolution_cycle: int,
        wall_ns: int,
    ) -> Tuple[
        ValidatedAttributionRecord,
        ...,
    ]:
        """Record authoritative frozen Week-5 validation evidence."""

        if not isinstance(
            validation,
            L1ValidationOutcome,
        ):
            raise TypeError(
                "validation must be an "
                "L1ValidationOutcome"
            )

        key = self._find_validation_key(
            validation
        )

        pending = self._pending[key]

        if pending.validation is not None:
            raise ValueError(
                "duplicate validation evidence for "
                "concrete L1 hit"
            )

        # Construct a partial attribution record solely to route the
        # authoritative frozen validation outcome into coverage
        # promotion. Diagnostic evidence is allowed to remain unresolved.
        partial = attribute_l1_hit(
            bin_id=key.bin_id,
            instruction_id=(
                key.consumer_instruction_id
            ),
            validation=validation,
        )

        promote_l1_attribution(
            self.coverage,
            partial,
            resolution_cycle=resolution_cycle,
            wall_ns=wall_ns,
        )

        pending.validation = validation

        return self._try_finalize(key)

    def record_hazard(
        self,
        hazard: HazardAttribution,
    ) -> Tuple[
        ValidatedAttributionRecord,
        ...,
    ]:
        """Record Week-7 hazard/timing attribution for one concrete hit."""

        if not isinstance(
            hazard,
            HazardAttribution,
        ):
            raise TypeError(
                "hazard must be a HazardAttribution"
            )

        key = self._key_from_hazard(
            hazard
        )

        try:
            pending = self._pending[key]
        except KeyError as exc:
            raise ValueError(
                "hazard attribution has no registered "
                "L1 Intent hit"
            ) from exc

        if pending.hazard is not None:
            raise ValueError(
                "duplicate hazard evidence for "
                "concrete L1 hit"
            )

        pending.hazard = hazard

        return self._try_finalize(key)

    def record_performance(
        self,
        performance: PerformanceResult,
    ) -> Tuple[
        ValidatedAttributionRecord,
        ...,
    ]:
        """Record Week-8 retirement timing for one consumer instruction.

        One retirement result can complete multiple L1 hits belonging to
        the same consumer.
        """

        if not isinstance(
            performance,
            PerformanceResult,
        ):
            raise TypeError(
                "performance must be a PerformanceResult"
            )

        instruction_id = (
            performance.instruction_id
        )

        keys = self._keys_for_consumer(
            instruction_id
        )

        if not keys:
            raise ValueError(
                "performance result has no pending "
                "registered L1 Intent hit"
            )

        if (
            instruction_id
            in self._performance_by_consumer
        ):
            raise ValueError(
                "duplicate performance evidence for "
                f"instruction_id={instruction_id}"
            )

        self._performance_by_consumer[
            instruction_id
        ] = performance

        records = []

        # Use the snapshot because successful finalization mutates
        # self._pending.
        for key in keys:
            records.extend(
                self._try_finalize(key)
            )

        # If none of the remaining hits for this consumer can ever use
        # the performance result because all have completed, release it.
        self._maybe_release_performance(
            instruction_id
        )

        return tuple(records)
