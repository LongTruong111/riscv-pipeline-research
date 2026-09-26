from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple


class CampaignInvariantViolation(AssertionError):
    """
    Week-13 infrastructure invariant violation.

    A violation of this class is INFRA_INVALID evidence, not a DUT
    experimental failure.
    """


def _require_non_negative_int(
    name: str,
    value: int,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise ValueError(
            f"{name} must be a non-negative integer"
        )


@dataclass(
    frozen=True,
    slots=True,
)
class HitLifecycleSnapshot:
    """
    Aggregate authoritative hit lifecycle at one stable campaign cut.

    pending_participants contains one tuple per pending concrete hit.
    Each tuple lists the accepted instruction IDs participating in that
    hit. The tuple is audit evidence only and is bounded by unresolved
    live coverage state, not campaign length.
    """

    registered: int
    validated: int
    rejected: int
    pending: int

    pending_participants: Tuple[
        Tuple[int, ...],
        ...,
    ] = ()

    pruned_mid_run: int = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("registered", self.registered),
            ("validated", self.validated),
            ("rejected", self.rejected),
            ("pending", self.pending),
            (
                "pruned_mid_run",
                self.pruned_mid_run,
            ),
        ):
            _require_non_negative_int(
                name,
                value,
            )

        if (
            len(self.pending_participants)
            != self.pending
        ):
            raise ValueError(
                "pending_participants must contain "
                "exactly one entry per pending hit"
            )

        for participants in (
            self.pending_participants
        ):
            if not participants:
                raise ValueError(
                    "pending hit must have at least "
                    "one participant"
                )

            for instruction_id in participants:
                if (
                    isinstance(
                        instruction_id,
                        bool,
                    )
                    or not isinstance(
                        instruction_id,
                        int,
                    )
                    or instruction_id <= 0
                ):
                    raise ValueError(
                        "pending participant IDs "
                        "must be positive integers"
                    )


@dataclass(
    frozen=True,
    slots=True,
)
class CampaignLifecycleSnapshot:
    """
    Stable campaign lifecycle state.

    This snapshot is taken only after all checker mutations belonging
    to the observation point have completed.
    """

    cycle: int

    accepted: int
    retired_checked: int

    functional_checked: int
    functional_pending: int

    performance_checked: int
    performance_pending: int

    max_intent_consumer_id: int

    l1: HitLifecycleSnapshot
    l2: HitLifecycleSnapshot

    def __post_init__(self) -> None:
        for name, value in (
            ("cycle", self.cycle),
            ("accepted", self.accepted),
            (
                "retired_checked",
                self.retired_checked,
            ),
            (
                "functional_checked",
                self.functional_checked,
            ),
            (
                "functional_pending",
                self.functional_pending,
            ),
            (
                "performance_checked",
                self.performance_checked,
            ),
            (
                "performance_pending",
                self.performance_pending,
            ),
            (
                "max_intent_consumer_id",
                self.max_intent_consumer_id,
            ),
        ):
            _require_non_negative_int(
                name,
                value,
            )


class CampaignInvariantLedger:
    """
    Campaign-wide exact-cut and lifecycle proof ledger.

    Retained state is scalar only. No campaign-length event history is
    retained.

    Per-snapshot complexity:
        O(P1 + P2)

    where P1/P2 are the numbers of currently pending L1/L2 hits.
    Those are bounded by unresolved live verification state, so memory
    remains O(1) with respect to campaign length.
    """

    def __init__(
        self,
        *,
        hard_cap: int,
        max_in_flight_depth: int,
    ) -> None:
        if (
            isinstance(hard_cap, bool)
            or not isinstance(hard_cap, int)
            or hard_cap <= 0
        ):
            raise ValueError(
                "hard_cap must be a positive integer"
            )

        if (
            isinstance(
                max_in_flight_depth,
                bool,
            )
            or not isinstance(
                max_in_flight_depth,
                int,
            )
            or max_in_flight_depth <= 0
        ):
            raise ValueError(
                "max_in_flight_depth must be "
                "a positive integer"
            )

        self._hard_cap = hard_cap
        self._max_in_flight_depth = (
            max_in_flight_depth
        )

        self._last_cycle = 0
        self._last_accepted = 0
        self._last_retired_checked = 0

        self._cut_marked = False
        self._cut_cycle: int | None = None
        self._kill_cycle: int | None = None

        self._post_cut_clock_edges = 0

        self._max_observed_in_flight = 0

    @property
    def hard_cap(self) -> int:
        return self._hard_cap

    @property
    def max_in_flight_depth(self) -> int:
        return self._max_in_flight_depth

    @property
    def cut_marked(self) -> bool:
        return self._cut_marked

    @property
    def cut_cycle(self) -> int | None:
        return self._cut_cycle

    @property
    def kill_cycle(self) -> int | None:
        return self._kill_cycle

    @property
    def post_cut_clock_edges(self) -> int:
        return self._post_cut_clock_edges

    @property
    def max_observed_in_flight(self) -> int:
        return self._max_observed_in_flight

    def note_clock_edge(
        self,
        *,
        cycle: int,
        edge: str,
    ) -> None:
        """
        Record one DUT clock transition.

        The final accepted RisingEdge is recorded before mark_exact_cut().
        Therefore every edge observed after cut_marked is necessarily a
        forbidden post-cut edge.
        """
        _require_non_negative_int(
            "cycle",
            cycle,
        )

        if cycle <= 0:
            raise ValueError(
                "cycle must be positive"
            )

        if edge not in {
            "rising",
            "falling",
        }:
            raise ValueError(
                "edge must be 'rising' or 'falling'"
            )

        if self._cut_marked:
            self._post_cut_clock_edges += 1

            raise CampaignInvariantViolation(
                "post-cut clock edge observed: "
                f"cycle={cycle}, edge={edge}, "
                f"cut_cycle={self._cut_cycle}"
            )

    @staticmethod
    def _check_hit_lifecycle(
        *,
        name: str,
        hits: HitLifecycleSnapshot,
        accepted: int,
        retired_checked: int,
    ) -> None:
        if (
            hits.registered
            != (
                hits.validated
                + hits.rejected
                + hits.pending
            )
        ):
            raise CampaignInvariantViolation(
                f"{name} hit conservation failed: "
                f"registered={hits.registered}, "
                f"validated={hits.validated}, "
                f"rejected={hits.rejected}, "
                f"pending={hits.pending}"
            )

        if hits.pruned_mid_run != 0:
            raise CampaignInvariantViolation(
                f"{name} unresolved hit pruning "
                "occurred mid-run: "
                f"count={hits.pruned_mid_run}"
            )

        for participants in (
            hits.pending_participants
        ):
            if any(
                participant > accepted
                for participant in participants
            ):
                raise CampaignInvariantViolation(
                    f"{name} pending hit references "
                    "instruction beyond accepted prefix: "
                    f"participants={participants}, "
                    f"accepted={accepted}"
                )

            if not any(
                retired_checked
                < participant
                <= accepted
                for participant in participants
            ):
                raise CampaignInvariantViolation(
                    f"{name} pending hit has no "
                    "participant in unresolved accepted tail: "
                    f"participants={participants}, "
                    f"retired_checked="
                    f"{retired_checked}, "
                    f"accepted={accepted}"
                )

    def check_snapshot(
        self,
        snapshot: CampaignLifecycleSnapshot,
    ) -> None:
        """
        Assert all stable lifecycle invariants for one observation cut.
        """
        if not isinstance(
            snapshot,
            CampaignLifecycleSnapshot,
        ):
            raise TypeError(
                "snapshot must be "
                "CampaignLifecycleSnapshot"
            )

        if snapshot.cycle < self._last_cycle:
            raise CampaignInvariantViolation(
                "cycle counter regressed: "
                f"last={self._last_cycle}, "
                f"current={snapshot.cycle}"
            )

        if (
            snapshot.accepted
            < self._last_accepted
        ):
            raise CampaignInvariantViolation(
                "accepted counter regressed: "
                f"last={self._last_accepted}, "
                f"current={snapshot.accepted}"
            )

        if (
            snapshot.retired_checked
            < self._last_retired_checked
        ):
            raise CampaignInvariantViolation(
                "retired_checked counter regressed: "
                f"last={self._last_retired_checked}, "
                f"current="
                f"{snapshot.retired_checked}"
            )

        if snapshot.accepted > self._hard_cap:
            raise CampaignInvariantViolation(
                "accepted count exceeded hard cap: "
                f"accepted={snapshot.accepted}, "
                f"hard_cap={self._hard_cap}"
            )

        if (
            snapshot.retired_checked
            > snapshot.accepted
        ):
            raise CampaignInvariantViolation(
                "retired_checked exceeds accepted: "
                f"retired_checked="
                f"{snapshot.retired_checked}, "
                f"accepted={snapshot.accepted}"
            )

        in_flight = (
            snapshot.accepted
            - snapshot.retired_checked
        )

        if (
            snapshot.functional_checked
            != snapshot.retired_checked
        ):
            raise CampaignInvariantViolation(
                "functional checked count does not "
                "match retired_checked: "
                f"functional_checked="
                f"{snapshot.functional_checked}, "
                f"retired_checked="
                f"{snapshot.retired_checked}"
            )

        if (
            snapshot.performance_checked
            != snapshot.retired_checked
        ):
            raise CampaignInvariantViolation(
                "performance checked count does not "
                "match retired_checked: "
                f"performance_checked="
                f"{snapshot.performance_checked}, "
                f"retired_checked="
                f"{snapshot.retired_checked}"
            )

        if (
            snapshot.functional_pending
            != in_flight
        ):
            raise CampaignInvariantViolation(
                "functional pending conservation "
                "failed: "
                f"pending="
                f"{snapshot.functional_pending}, "
                f"in_flight={in_flight}"
            )

        if (
            snapshot.performance_pending
            != in_flight
        ):
            raise CampaignInvariantViolation(
                "performance pending conservation "
                "failed: "
                f"pending="
                f"{snapshot.performance_pending}, "
                f"in_flight={in_flight}"
            )

        if in_flight > self._max_in_flight_depth:
            raise CampaignInvariantViolation(
                "in-flight depth exceeded frozen "
                "bound: "
                f"in_flight={in_flight}, "
                f"bound="
                f"{self._max_in_flight_depth}"
            )

        if (
            snapshot.max_intent_consumer_id
            > snapshot.accepted
        ):
            raise CampaignInvariantViolation(
                "Intent consumer exceeds accepted "
                "prefix: "
                f"max_intent_consumer_id="
                f"{snapshot.max_intent_consumer_id}, "
                f"accepted={snapshot.accepted}"
            )

        self._check_hit_lifecycle(
            name="L1",
            hits=snapshot.l1,
            accepted=snapshot.accepted,
            retired_checked=(
                snapshot.retired_checked
            ),
        )

        self._check_hit_lifecycle(
            name="L2",
            hits=snapshot.l2,
            accepted=snapshot.accepted,
            retired_checked=(
                snapshot.retired_checked
            ),
        )

        self._max_observed_in_flight = max(
            self._max_observed_in_flight,
            in_flight,
        )

        self._last_cycle = snapshot.cycle
        self._last_accepted = snapshot.accepted
        self._last_retired_checked = (
            snapshot.retired_checked
        )

    def mark_exact_cut(
        self,
        *,
        current_cycle: int,
        kill_cycle: int,
        accepted: int,
        adapter_instruction_count: int,
    ) -> None:
        """
        Freeze authoritative exact-N cut after all post-instruction
        observers/checkpoint work for instruction N has completed.
        """
        for name, value in (
            ("current_cycle", current_cycle),
            ("kill_cycle", kill_cycle),
            ("accepted", accepted),
            (
                "adapter_instruction_count",
                adapter_instruction_count,
            ),
        ):
            _require_non_negative_int(
                name,
                value,
            )

        if self._cut_marked:
            raise CampaignInvariantViolation(
                "exact cut marked more than once"
            )

        if accepted != self._hard_cap:
            raise CampaignInvariantViolation(
                "exact cut marked at wrong accepted "
                "count: "
                f"accepted={accepted}, "
                f"hard_cap={self._hard_cap}"
            )

        if (
            adapter_instruction_count
            != self._hard_cap
        ):
            raise CampaignInvariantViolation(
                "adapter instruction count does not "
                "match hard cap at cut: "
                f"adapter="
                f"{adapter_instruction_count}, "
                f"hard_cap={self._hard_cap}"
            )

        if kill_cycle != current_cycle:
            raise CampaignInvariantViolation(
                "kill cycle differs from exact-cut "
                "cycle: "
                f"current_cycle={current_cycle}, "
                f"kill_cycle={kill_cycle}"
            )

        self._cut_marked = True
        self._cut_cycle = current_cycle
        self._kill_cycle = kill_cycle

    def finalize(
        self,
        snapshot: CampaignLifecycleSnapshot,
    ) -> None:
        """
        Recheck the final stable state and prove exact-cut completion.
        """
        self.check_snapshot(snapshot)

        if not self._cut_marked:
            raise CampaignInvariantViolation(
                "campaign finalized without exact cut"
            )

        if snapshot.accepted != self._hard_cap:
            raise CampaignInvariantViolation(
                "final accepted count does not "
                "match hard cap"
            )

        if self._post_cut_clock_edges != 0:
            raise CampaignInvariantViolation(
                "post-cut clock edges are non-zero: "
                f"{self._post_cut_clock_edges}"
            )
