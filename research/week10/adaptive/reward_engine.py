from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterable

from research.week10.adaptive.register_policy import TargetSelection
from research.week10.adaptive.template_library import (
    ArmID,
    Distance,
    get_template,
)


POSITIVE_REGISTERS: tuple[int, ...] = tuple(range(1, 32))


@dataclass(frozen=True, order=True)
class L2IntentBin:
    """
    One frozen L2 Intent bin:

        (dependency_distance, architectural_register)

    Only scalar d1/d2 distances participate in the 62-bin L2 model.
    """

    distance: Distance
    register: int

    def __post_init__(self) -> None:
        if self.distance not in (
            Distance.D1,
            Distance.D2,
        ):
            raise ValueError(
                "L2 Intent bin distance must be d1 or d2"
            )

        if self.register not in POSITIVE_REGISTERS:
            raise ValueError(
                "L2 Intent register must be x1..x31, "
                f"got x{self.register}"
            )


def attribution_targets_for(
    arm_id: ArmID,
    target: TargetSelection,
) -> FrozenSet[L2IntentBin]:
    """
    Convert the selected register target(s) of one arm into the exact
    L2 Intent bins that are eligible for reward attribution.

    This function deliberately derives attribution from the arm/template
    contract rather than accepting an arbitrary caller-provided
    'attributable=True' flag.
    """
    spec = get_template(arm_id)

    if spec.distance is Distance.D1:
        if target.d1 is None or target.d2 is not None:
            raise ValueError(
                f"{arm_id.value} requires exactly one d1 target"
            )

        return frozenset(
            {
                L2IntentBin(
                    distance=Distance.D1,
                    register=target.d1,
                )
            }
        )

    if spec.distance is Distance.D2:
        if target.d1 is not None or target.d2 is None:
            raise ValueError(
                f"{arm_id.value} requires exactly one d2 target"
            )

        return frozenset(
            {
                L2IntentBin(
                    distance=Distance.D2,
                    register=target.d2,
                )
            }
        )

    if spec.distance is Distance.D1_D2:
        if (
            target.d1 is None
            or target.d2 is None
        ):
            raise ValueError(
                f"{arm_id.value} requires both d1 and d2 targets"
            )

        if target.d1 == target.d2:
            raise ValueError(
                "A4 d1/d2 target registers must be distinct"
            )

        return frozenset(
            {
                L2IntentBin(
                    distance=Distance.D1,
                    register=target.d1,
                ),
                L2IntentBin(
                    distance=Distance.D2,
                    register=target.d2,
                ),
            }
        )

    raise RuntimeError(
        f"unsupported adaptive template distance: {spec.distance!r}"
    )

@dataclass(frozen=True)
class EpochRewardResult:
    """
    Immutable reward result for one completed adaptive epoch.
    """

    arm_id: ArmID
    actual_executed_instructions: int

    attributable_targets: FrozenSet[L2IntentBin]

    # All globally observed L2 Intent bins during this epoch.
    observed_intent_bins: FrozenSet[L2IntentBin]

    # Subset whose exact template provenance was independently proven.
    attributable_observed_intent_bins: FrozenSet[L2IntentBin]

    global_new_intent_bins: FrozenSet[L2IntentBin]
    attributable_new_intent_bins: FrozenSet[L2IntentBin]

    reward: float

    @property
    def global_new_count(self) -> int:
        return len(self.global_new_intent_bins)

    @property
    def attributable_new_count(self) -> int:
        return len(self.attributable_new_intent_bins)


class EpochRewardTracker:
    """
    Bounded per-epoch L2 Intent reward tracker.

    Two observation domains are deliberately separate:

        global_observed
            every live L2 Intent hit observed during the epoch

        attributable_observed
            only hits whose exact generated-template provenance has
            independently matched

    Novelty remains frozen against coverage state at epoch start:

        global_new =
            global_observed - covered_at_epoch_start

        attributable_new =
            (
                attributable_observed
                - covered_at_epoch_start
            )
            intersect selected_arm_targets

        reward =
            1000
            * len(attributable_new)
            / actual_executed_instructions

    Validated coverage is intentionally absent from this interface.
    """

    def __init__(
        self,
        *,
        arm_id: ArmID,
        target: TargetSelection,
        covered_at_epoch_start: Iterable[L2IntentBin],
    ) -> None:
        self._arm_id = arm_id

        self._attributable_targets = attribution_targets_for(
            arm_id,
            target,
        )

        self._covered_at_epoch_start = frozenset(
            covered_at_epoch_start
        )

        self._validate_bin_collection(
            self._covered_at_epoch_start
        )

        self._observed_intent_bins: set[L2IntentBin] = set()

        self._attributable_observed_intent_bins: set[
            L2IntentBin
        ] = set()

        self._finalized = False

    @staticmethod
    def _validate_bin_collection(
        bins: Iterable[L2IntentBin],
    ) -> None:
        for bin_value in bins:
            if not isinstance(
                bin_value,
                L2IntentBin,
            ):
                raise TypeError(
                    "L2 Intent coverage must contain "
                    "L2IntentBin objects"
                )

    def _require_open_bin(
        self,
        bin_value: L2IntentBin,
    ) -> None:
        if self._finalized:
            raise RuntimeError(
                "cannot record L2 Intent hit "
                "after reward finalization"
            )

        if not isinstance(
            bin_value,
            L2IntentBin,
        ):
            raise TypeError(
                "bin_value must be an L2IntentBin"
            )

    @property
    def arm_id(self) -> ArmID:
        return self._arm_id

    @property
    def attributable_targets(
        self,
    ) -> FrozenSet[L2IntentBin]:
        return self._attributable_targets

    @property
    def covered_at_epoch_start(
        self,
    ) -> FrozenSet[L2IntentBin]:
        return self._covered_at_epoch_start

    @property
    def observed_intent_bins(
        self,
    ) -> FrozenSet[L2IntentBin]:
        return frozenset(
            self._observed_intent_bins
        )

    @property
    def attributable_observed_intent_bins(
        self,
    ) -> FrozenSet[L2IntentBin]:
        return frozenset(
            self._attributable_observed_intent_bins
        )

    def record_intent_hit(
        self,
        bin_value: L2IntentBin,
    ) -> None:
        """
        Record one global live L2 Intent observation.

        This method grants NO adaptive attribution by itself.

        In particular, observing the selected target bin is not enough
        to earn reward without exact template provenance.
        """
        self._require_open_bin(
            bin_value
        )

        self._observed_intent_bins.add(
            bin_value
        )

    def record_attributable_intent_hit(
        self,
        bin_value: L2IntentBin,
    ) -> None:
        """
        Record an Intent observation whose exact template provenance has
        already been independently established by the caller.

        An attributable hit necessarily also exists in global Intent.
        """
        self._require_open_bin(
            bin_value
        )

        if (
            bin_value
            not in self._attributable_targets
        ):
            raise ValueError(
                "provenance-qualified hit is outside "
                "the selected arm attribution targets"
            )

        self._observed_intent_bins.add(
            bin_value
        )

        self._attributable_observed_intent_bins.add(
            bin_value
        )

    def finalize(
        self,
        *,
        actual_executed_instructions: int,
    ) -> EpochRewardResult:
        """
        Finalize one epoch using the actual executed-instruction count.
        """
        if self._finalized:
            raise RuntimeError(
                "epoch reward has already been finalized"
            )

        if (
            isinstance(
                actual_executed_instructions,
                bool,
            )
            or not isinstance(
                actual_executed_instructions,
                int,
            )
            or actual_executed_instructions <= 0
        ):
            raise ValueError(
                "actual_executed_instructions "
                "must be a positive integer"
            )

        observed = frozenset(
            self._observed_intent_bins
        )

        attributable_observed = frozenset(
            self._attributable_observed_intent_bins
        )

        global_new = frozenset(
            observed
            - self._covered_at_epoch_start
        )

        attributable_new = frozenset(
            (
                attributable_observed
                - self._covered_at_epoch_start
            )
            & self._attributable_targets
        )

        reward = (
            1000.0
            * len(attributable_new)
            / actual_executed_instructions
        )

        self._finalized = True

        return EpochRewardResult(
            arm_id=self._arm_id,
            actual_executed_instructions=(
                actual_executed_instructions
            ),
            attributable_targets=(
                self._attributable_targets
            ),
            observed_intent_bins=observed,
            attributable_observed_intent_bins=(
                attributable_observed
            ),
            global_new_intent_bins=global_new,
            attributable_new_intent_bins=(
                attributable_new
            ),
            reward=reward,
        )
