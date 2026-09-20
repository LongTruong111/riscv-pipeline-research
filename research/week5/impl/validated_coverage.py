from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .l1_coverage import (
    L1_BIN_COUNT,
    L1_BIN_IDS,
    L1Hit,
)


_BASE_ARCHITECTURAL_KINDS = (
    "pc",
    "store",
    "writeback",
)

_X0_REQUIRED_BINS = frozenset(
    (
        "H18",
        "H19",
    )
)

_VALID_ARCHITECTURAL_KINDS = frozenset(
    (
        "pc",
        "store",
        "writeback",
        "x0",
    )
)


@dataclass(frozen=True, slots=True)
class L1ValidationOutcome:
    """
    Final validation result for one concrete L1 Intent hit.

    One bin may have multiple Intent hits across a campaign. A failed hit
    does not permanently close the bin: a later independently validated hit
    may still promote that bin to Validated Coverage.
    """

    bin_id: str
    consumer_instruction_index: int
    producer_instruction_indices: Tuple[int, ...]

    control_passed: bool
    architectural_passed: Optional[bool]

    validated: bool

    missing_architectural_checks: Tuple[
        Tuple[int, str], ...
    ] = ()

    failed_architectural_checks: Tuple[
        Tuple[int, str], ...
    ] = ()


class L1ValidatedCoverageCollector:
    """
    Per-hit promotion layer:

        IntentHit
          + control realization PASS
          + required architectural realization PASS
          -> ValidatedHit

    Intent classification remains external and unchanged.

    Architectural requirements
    --------------------------
    For every producer and consumer participating in the hit:

        - executed PC must be correct;
        - register-write behavior must be correct;
        - store behavior must be correct.

    H18/H19 additionally require architectural x0 == 0.

    x0 is deliberately NOT made a global requirement for every hazard bin.
    Otherwise one persistent x0 corruption could incorrectly invalidate
    unrelated later hazard observations.
    """

    def __init__(self) -> None:
        self.validated_seen: Dict[str, bool] = {
            bin_id: False
            for bin_id in L1_BIN_IDS
        }

        self.validation_attempt_count: Dict[str, int] = {
            bin_id: 0
            for bin_id in L1_BIN_IDS
        }

        self.validated_hit_count: Dict[str, int] = {
            bin_id: 0
            for bin_id in L1_BIN_IDS
        }

        self.rejected_hit_count: Dict[str, int] = {
            bin_id: 0
            for bin_id in L1_BIN_IDS
        }

        # Architectural results indexed by executed instruction index:
        #
        #   {
        #       instruction_index: {
        #           "pc": True,
        #           "store": True,
        #           "writeback": False,
        #           "x0": True,
        #       }
        #   }
        #
        # This cache is explicitly prunable for long campaigns.
        self._architectural_results: Dict[
            int,
            Dict[str, bool],
        ] = {}

        # Only control-PASS hits need to wait for architectural evidence.
        self._pending_by_consumer: Dict[
            int,
            List[L1Hit],
        ] = {}

    def reset(self) -> None:
        for bin_id in L1_BIN_IDS:
            self.validated_seen[bin_id] = False
            self.validation_attempt_count[bin_id] = 0
            self.validated_hit_count[bin_id] = 0
            self.rejected_hit_count[bin_id] = 0

        self._architectural_results.clear()
        self._pending_by_consumer.clear()

    @property
    def validated_bins(self) -> int:
        return sum(self.validated_seen.values())

    @property
    def validated_coverage(self) -> float:
        return self.validated_bins / L1_BIN_COUNT

    @property
    def pending_hits(self) -> int:
        return sum(
            len(hits)
            for hits in self._pending_by_consumer.values()
        )

    @property
    def rejected_hits(self) -> int:
        return sum(self.rejected_hit_count.values())

    @property
    def architectural_cache_entries(self) -> int:
        return len(self._architectural_results)

    @staticmethod
    def _participant_indices(
        hit: L1Hit,
    ) -> Tuple[int, ...]:
        """
        Return unique producer(s) followed by consumer.
        """
        ordered: List[int] = []

        for instruction_index in (
            *hit.producer_instruction_indices,
            hit.consumer_instruction_index,
        ):
            if instruction_index not in ordered:
                ordered.append(instruction_index)

        return tuple(ordered)

    @classmethod
    def _required_checks(
        cls,
        hit: L1Hit,
    ) -> Tuple[Tuple[int, str], ...]:
        kinds = list(_BASE_ARCHITECTURAL_KINDS)

        if hit.bin_id in _X0_REQUIRED_BINS:
            kinds.append("x0")

        return tuple(
            (
                instruction_index,
                kind,
            )
            for instruction_index
            in cls._participant_indices(hit)
            for kind in kinds
        )

    def _evaluate_architecture(
        self,
        hit: L1Hit,
    ) -> Optional[L1ValidationOutcome]:
        missing = []

        for instruction_index, kind in self._required_checks(hit):
            per_instruction = self._architectural_results.get(
                instruction_index
            )

            if (
                per_instruction is None
                or kind not in per_instruction
            ):
                missing.append(
                    (
                        instruction_index,
                        kind,
                    )
                )

        if missing:
            return None

        failed = tuple(
            (
                instruction_index,
                kind,
            )
            for instruction_index, kind
            in self._required_checks(hit)
            if not self._architectural_results[
                instruction_index
            ][kind]
        )

        architectural_passed = not failed
        validated = architectural_passed

        if validated:
            self.validated_hit_count[hit.bin_id] += 1
            self.validated_seen[hit.bin_id] = True
        else:
            self.rejected_hit_count[hit.bin_id] += 1

        return L1ValidationOutcome(
            bin_id=hit.bin_id,
            consumer_instruction_index=(
                hit.consumer_instruction_index
            ),
            producer_instruction_indices=(
                hit.producer_instruction_indices
            ),
            control_passed=True,
            architectural_passed=architectural_passed,
            validated=validated,
            failed_architectural_checks=failed,
        )

    def _try_finalize_consumer(
        self,
        consumer_instruction_index: int,
    ) -> Tuple[L1ValidationOutcome, ...]:
        pending = self._pending_by_consumer.get(
            consumer_instruction_index
        )

        if not pending:
            return ()

        outcomes: List[L1ValidationOutcome] = []
        still_pending: List[L1Hit] = []

        for hit in pending:
            result = self._evaluate_architecture(hit)

            if result is None:
                still_pending.append(hit)
            else:
                outcomes.append(result)

        if still_pending:
            self._pending_by_consumer[
                consumer_instruction_index
            ] = still_pending
        else:
            del self._pending_by_consumer[
                consumer_instruction_index
            ]

        return tuple(outcomes)

    def _try_finalize_all(
        self,
    ) -> Tuple[L1ValidationOutcome, ...]:
        outcomes: List[L1ValidationOutcome] = []

        for consumer_instruction_index in tuple(
            self._pending_by_consumer
        ):
            outcomes.extend(
                self._try_finalize_consumer(
                    consumer_instruction_index
                )
            )

        return tuple(outcomes)

    def register_hit(
        self,
        hit: L1Hit,
        *,
        control_passed: bool,
    ) -> Tuple[L1ValidationOutcome, ...]:
        if hit.bin_id not in self.validated_seen:
            raise ValueError(
                f"unknown L1 bin: {hit.bin_id}"
            )

        self.validation_attempt_count[hit.bin_id] += 1

        if not control_passed:
            self.rejected_hit_count[hit.bin_id] += 1

            return (
                L1ValidationOutcome(
                    bin_id=hit.bin_id,
                    consumer_instruction_index=(
                        hit.consumer_instruction_index
                    ),
                    producer_instruction_indices=(
                        hit.producer_instruction_indices
                    ),
                    control_passed=False,
                    architectural_passed=None,
                    validated=False,
                ),
            )

        self._pending_by_consumer.setdefault(
            hit.consumer_instruction_index,
            [],
        ).append(hit)

        return self._try_finalize_consumer(
            hit.consumer_instruction_index
        )

    def record_architectural_result(
        self,
        *,
        instruction_index: int,
        kind: str,
        passed: bool,
    ) -> Tuple[L1ValidationOutcome, ...]:
        if instruction_index <= 0:
            raise ValueError(
                "instruction_index must be positive"
            )

        if kind not in _VALID_ARCHITECTURAL_KINDS:
            raise ValueError(
                f"unsupported architectural result kind: {kind}"
            )

        per_instruction = self._architectural_results.setdefault(
            instruction_index,
            {},
        )

        if kind in per_instruction:
            previous = per_instruction[kind]

            if previous != bool(passed):
                raise ValueError(
                    "conflicting architectural result for "
                    f"instruction_index={instruction_index}, "
                    f"kind={kind}: previous={previous}, "
                    f"new={bool(passed)}"
                )

            # Idempotent duplicate.
            return ()

        per_instruction[kind] = bool(passed)

        return self._try_finalize_all()

    def prune(
        self,
        *,
        latest_instruction_index: int,
    ) -> None:
        """
        Bound architectural-result memory for long campaigns.

        L1 only references dependencies through d3. Keeping the latest
        five executed indices gives margin beyond the frozen attribution
        distance, while any index still referenced by a pending hit is
        retained regardless of age.

        Thus cache size is O(1) with respect to campaign length, apart
        from the bounded number of in-flight pending hits.
        """
        if latest_instruction_index <= 0:
            raise ValueError(
                "latest_instruction_index must be positive"
            )

        retained_by_pending = set()

        for hits in self._pending_by_consumer.values():
            for hit in hits:
                retained_by_pending.update(
                    self._participant_indices(hit)
                )

        oldest_recent = max(
            1,
            latest_instruction_index - 4,
        )

        for instruction_index in tuple(
            self._architectural_results
        ):
            if (
                instruction_index < oldest_recent
                and instruction_index
                not in retained_by_pending
            ):
                del self._architectural_results[
                    instruction_index
                ]
