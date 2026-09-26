from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from research.week10.adaptive.post_instruction_cut import (
    ExecutedInstructionCoverage,
    complete_post_instruction_cut,
)
from research.week13.campaign.invariant_ledger import (
    CampaignInvariantLedger,
    CampaignInvariantViolation,
    CampaignLifecycleSnapshot,
)


class CampaignInfrastructureError(AssertionError):
    """
    Week-13 campaign infrastructure failure.

    This maps to INFRA_INVALID and is not DUT experimental evidence.
    """


@dataclass(
    frozen=True,
    slots=True,
)
class CampaignCutDecision:
    """
    Result of one accepted-instruction post-cut.

    exact_cut=True means all authoritative work for accepted instruction
    N has completed and the caller must stop the sole DUT clock owner
    immediately, before any runtime release/refill or further edge.
    """

    instruction_index: int
    cycle: int
    exact_cut: bool
    snapshot: CampaignLifecycleSnapshot


class CampaignCutDriver:
    """
    Common Week-13 exact-N campaign cut coordinator.

    This class owns:
      - accepted-prefix continuity;
      - hard-cap enforcement;
      - common post-instruction coverage/checkpoint path;
      - Intent-consumer boundary tracking;
      - lifecycle invariant execution;
      - exact-cut marking;
      - final clock-stop postconditions.

    Method-specific stream planning, refill, adaptive epoch handling,
    and terminal suffix cleanup remain outside this class.

    Complexity:
        O(1) driver state with respect to campaign length N.

    Snapshot cost is delegated to the bounded snapshot adapter.
    """

    def __init__(
        self,
        *,
        hard_cap: int,
        coverage: ExecutedInstructionCoverage,
        ledger: CampaignInvariantLedger,
    ) -> None:
        if (
            isinstance(hard_cap, bool)
            or not isinstance(hard_cap, int)
            or hard_cap <= 0
        ):
            raise ValueError(
                "hard_cap must be a positive integer"
            )

        if not isinstance(
            ledger,
            CampaignInvariantLedger,
        ):
            raise TypeError(
                "ledger must be CampaignInvariantLedger"
            )

        if ledger.hard_cap != hard_cap:
            raise ValueError(
                "driver/ledger hard-cap mismatch: "
                f"driver={hard_cap}, "
                f"ledger={ledger.hard_cap}"
            )

        self._hard_cap = hard_cap
        self._coverage = coverage
        self._ledger = ledger

        self._coverage_observed_count = 0
        self._last_accepted_instruction = 0
        self._max_intent_consumer_id = 0

        self._exact_cut_requested = False
        self._final_snapshot: (
            CampaignLifecycleSnapshot | None
        ) = None

    @property
    def hard_cap(self) -> int:
        return self._hard_cap

    @property
    def accepted_count(self) -> int:
        return self._last_accepted_instruction

    @property
    def coverage_observed_count(self) -> int:
        return self._coverage_observed_count

    @property
    def max_intent_consumer_id(self) -> int:
        return self._max_intent_consumer_id

    @property
    def exact_cut_requested(self) -> bool:
        return self._exact_cut_requested

    @property
    def final_snapshot(
        self,
    ) -> CampaignLifecycleSnapshot | None:
        return self._final_snapshot

    def note_clock_edge(
        self,
        *,
        cycle: int,
        edge: str,
    ) -> None:
        """
        Forward DUT-edge evidence to the invariant ledger.

        Any edge reported after exact-cut marking is INFRA_INVALID.
        """
        try:
            self._ledger.note_clock_edge(
                cycle=cycle,
                edge=edge,
            )
        except CampaignInvariantViolation as exc:
            raise CampaignInfrastructureError(
                str(exc)
            ) from exc

    def note_intent_consumer(
        self,
        *,
        consumer_instruction_id: int,
        accepted_prefix: int,
    ) -> None:
        """
        Record one concrete L1/L2 Intent consumer.

        This is called only when an actual Intent hit is registered,
        making max_intent_consumer_id independent from accepted count.
        """
        for name, value in (
            (
                "consumer_instruction_id",
                consumer_instruction_id,
            ),
            (
                "accepted_prefix",
                accepted_prefix,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be a positive integer"
                )

        if consumer_instruction_id > accepted_prefix:
            raise CampaignInfrastructureError(
                "Intent consumer exceeds current accepted prefix: "
                f"consumer={consumer_instruction_id}, "
                f"accepted_prefix={accepted_prefix}"
            )

        self._max_intent_consumer_id = max(
            self._max_intent_consumer_id,
            consumer_instruction_id,
        )

    def complete_accepted_event(
        self,
        *,
        instruction_index: int,
        cycle: int,
        adapter_instruction_count: int,
        observe_coverage: Callable[[], None],
        snapshot_factory: Callable[
            [int],
            CampaignLifecycleSnapshot,
        ],
    ) -> CampaignCutDecision:
        """
        Complete the authoritative post-instruction cut for one accepted
        event.

        Required caller ordering before entry:

            planned-stream identity
            timing expectation
            architectural step
            successor-PC resolution
            functional expectation registration
            performance expectation registration

        observe_coverage() must perform all L1/L2 Intent/Validated work
        for this accepted event. Coverage checkpoint emission therefore
        occurs through the same frozen path for intermediate and final
        checkpoints.
        """
        if self._exact_cut_requested:
            raise CampaignInfrastructureError(
                "accepted event observed after exact cut"
            )

        for name, value in (
            (
                "instruction_index",
                instruction_index,
            ),
            ("cycle", cycle),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be a positive integer"
                )

        if (
            isinstance(
                adapter_instruction_count,
                bool,
            )
            or not isinstance(
                adapter_instruction_count,
                int,
            )
            or adapter_instruction_count < 0
        ):
            raise ValueError(
                "adapter_instruction_count must be "
                "a non-negative integer"
            )

        expected_instruction = (
            self._last_accepted_instruction + 1
        )

        if instruction_index != expected_instruction:
            raise CampaignInfrastructureError(
                "accepted instruction continuity failure: "
                f"expected={expected_instruction}, "
                f"observed={instruction_index}"
            )

        if instruction_index > self._hard_cap:
            raise CampaignInfrastructureError(
                "accepted count exceeded hard cap: "
                f"accepted={instruction_index}, "
                f"hard_cap={self._hard_cap}"
            )

        if (
            adapter_instruction_count
            != instruction_index
        ):
            raise CampaignInfrastructureError(
                "adapter/accepted count mismatch: "
                f"adapter={adapter_instruction_count}, "
                f"accepted={instruction_index}"
            )

        try:
            new_observed_count = (
                complete_post_instruction_cut(
                    observed_count=(
                        self._coverage_observed_count
                    ),
                    instruction_index=(
                        instruction_index
                    ),
                    cycle=cycle,
                    coverage=self._coverage,
                    observe_coverage=observe_coverage,
                )
            )
        except (
            AssertionError,
            ValueError,
        ) as exc:
            raise CampaignInfrastructureError(
                "post-instruction cut failed: "
                f"{exc}"
            ) from exc

        if (
            new_observed_count
            != instruction_index
        ):
            raise CampaignInfrastructureError(
                "coverage observed count does not match "
                "accepted prefix after cut"
            )

        self._coverage_observed_count = (
            new_observed_count
        )

        snapshot = snapshot_factory(
            self._max_intent_consumer_id
        )

        if not isinstance(
            snapshot,
            CampaignLifecycleSnapshot,
        ):
            raise TypeError(
                "snapshot_factory must return "
                "CampaignLifecycleSnapshot"
            )

        if snapshot.accepted != instruction_index:
            raise CampaignInfrastructureError(
                "snapshot accepted count mismatch: "
                f"snapshot={snapshot.accepted}, "
                f"event={instruction_index}"
            )

        if snapshot.cycle != cycle:
            raise CampaignInfrastructureError(
                "snapshot cycle mismatch: "
                f"snapshot={snapshot.cycle}, "
                f"cut_cycle={cycle}"
            )

        try:
            self._ledger.check_snapshot(
                snapshot
            )
        except CampaignInvariantViolation as exc:
            raise CampaignInfrastructureError(
                "campaign lifecycle invariant failed: "
                f"{exc}"
            ) from exc

        self._last_accepted_instruction = (
            instruction_index
        )

        exact_cut = (
            instruction_index
            == self._hard_cap
        )

        if exact_cut:
            try:
                self._ledger.mark_exact_cut(
                    current_cycle=cycle,
                    kill_cycle=cycle,
                    accepted=instruction_index,
                    adapter_instruction_count=(
                        adapter_instruction_count
                    ),
                )
            except CampaignInvariantViolation as exc:
                raise CampaignInfrastructureError(
                    "exact-cut invariant failed: "
                    f"{exc}"
                ) from exc

            self._exact_cut_requested = True
            self._final_snapshot = snapshot

        return CampaignCutDecision(
            instruction_index=(
                instruction_index
            ),
            cycle=cycle,
            exact_cut=exact_cut,
            snapshot=snapshot,
        )

    def finalize_after_clock_stop(
        self,
        *,
        adapter_instruction_count: int,
        clock_task_done: bool,
        clock_is_high: bool,
    ) -> CampaignLifecycleSnapshot:
        """
        Confirm physical exact termination after the caller kills the
        sole clock owner at RisingEdge + ReadOnly.

        Caller may perform a no-edge settling delay before invoking this.
        """
        if not self._exact_cut_requested:
            raise CampaignInfrastructureError(
                "clock-stop finalization requested "
                "before exact cut"
            )

        if self._final_snapshot is None:
            raise CampaignInfrastructureError(
                "exact cut has no final lifecycle snapshot"
            )

        if (
            adapter_instruction_count
            != self._hard_cap
        ):
            raise CampaignInfrastructureError(
                "adapter count changed at termination: "
                f"adapter={adapter_instruction_count}, "
                f"hard_cap={self._hard_cap}"
            )

        if not clock_task_done:
            raise CampaignInfrastructureError(
                "sole clock owner is still active "
                "after exact cut"
            )

        if not clock_is_high:
            raise CampaignInfrastructureError(
                "DUT clock is not frozen HIGH "
                "after exact cut"
            )

        try:
            self._ledger.finalize(
                self._final_snapshot
            )
        except CampaignInvariantViolation as exc:
            raise CampaignInfrastructureError(
                "final campaign invariant failed: "
                f"{exc}"
            ) from exc

        return self._final_snapshot
