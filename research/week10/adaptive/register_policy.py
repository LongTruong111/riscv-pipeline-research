from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import FrozenSet

from research.week10.adaptive.template_library import (
    ArmID,
    Distance,
    get_template,
)


POSITIVE_REGISTERS: tuple[int, ...] = tuple(range(1, 32))
_POSITIVE_REGISTER_SET = frozenset(POSITIVE_REGISTERS)


@dataclass(frozen=True)
class L2IntentCoverageState:
    """
    Minimal immutable view of current L2 Intent coverage.

    Registers are architectural positive target registers:
        x1 ... x31

    x0 is never a positive L2 target.
    """

    d1_covered: FrozenSet[int] = frozenset()
    d2_covered: FrozenSet[int] = frozenset()

    def __post_init__(self) -> None:
        self._validate_register_set("d1_covered", self.d1_covered)
        self._validate_register_set("d2_covered", self.d2_covered)

    @staticmethod
    def _validate_register_set(
        name: str,
        registers: FrozenSet[int],
    ) -> None:
        invalid = set(registers) - _POSITIVE_REGISTER_SET

        if invalid:
            raise ValueError(
                f"{name} contains invalid positive L2 registers: "
                f"{sorted(invalid)}"
            )

    def covered(self, distance: Distance) -> FrozenSet[int]:
        if distance is Distance.D1:
            return self.d1_covered

        if distance is Distance.D2:
            return self.d2_covered

        raise ValueError(
            f"coverage state requires a scalar distance, got {distance!r}"
        )

    def uncovered(self, distance: Distance) -> tuple[int, ...]:
        """
        Return uncovered positive registers in canonical numeric order.
        """
        covered = self.covered(distance)

        return tuple(
            register
            for register in POSITIVE_REGISTERS
            if register not in covered
        )

    def is_covered(
        self,
        distance: Distance,
        register: int,
    ) -> bool:
        if register not in _POSITIVE_REGISTER_SET:
            raise ValueError(
                f"register x{register} is not a positive L2 target"
            )

        return register in self.covered(distance)


@dataclass(frozen=True)
class TargetSelection:
    """
    Register targets selected for one adaptive template instance.

    Single-distance arms populate exactly one of d1/d2.
    A4 populates both.
    """

    d1: int | None = None
    d2: int | None = None

    def __post_init__(self) -> None:
        for field_name, register in (
            ("d1", self.d1),
            ("d2", self.d2),
        ):
            if register is None:
                continue

            if register not in _POSITIVE_REGISTER_SET:
                raise ValueError(
                    f"{field_name} target x{register} is invalid"
                )

        if (
            self.d1 is not None
            and self.d2 is not None
            and self.d1 == self.d2
        ):
            raise ValueError(
                "dual d1/d2 target registers must be distinct"
            )

    @property
    def is_dual(self) -> bool:
        return self.d1 is not None and self.d2 is not None


class RegisterTargetPolicy:
    """
    Seed-deterministic uncovered-first L2 Intent register targeting.

    Randomness is supplied by the caller-owned Random instance.
    No module-global RNG state is used.
    """

    def __init__(self, rng: Random) -> None:
        if not isinstance(rng, Random):
            raise TypeError("rng must be an instance of random.Random")

        self._rng = rng

    def select(
        self,
        arm_id: ArmID,
        coverage: L2IntentCoverageState,
    ) -> TargetSelection:
        """
        Select positive L2 target register(s) for one arm.

        Single-distance arms:
            uncovered-first;
            saturated distance -> uniform x1..x31.

        A4:
            distinct ordered d1/d2 pair maximizing uncovered
            opportunity score, then seeded-uniform tie-break.
        """
        spec = get_template(arm_id)

        if spec.distance is Distance.D1:
            return TargetSelection(
                d1=self._select_single(
                    Distance.D1,
                    coverage,
                )
            )

        if spec.distance is Distance.D2:
            return TargetSelection(
                d2=self._select_single(
                    Distance.D2,
                    coverage,
                )
            )

        if spec.distance is Distance.D1_D2:
            return self._select_dual(coverage)

        raise RuntimeError(
            f"unsupported adaptive distance: {spec.distance!r}"
        )

    def _select_single(
        self,
        distance: Distance,
        coverage: L2IntentCoverageState,
    ) -> int:
        uncovered = coverage.uncovered(distance)

        if uncovered:
            candidates = uncovered
        else:
            candidates = POSITIVE_REGISTERS

        # candidates is already in canonical order.
        return self._rng.choice(candidates)

    def _select_dual(
        self,
        coverage: L2IntentCoverageState,
    ) -> TargetSelection:
        """
        Select an ordered (d1, d2) pair for A4.

        The pair must be distinct.

        Among all valid pairs, maximize:

            1[d1 target currently uncovered]
          + 1[d2 target currently uncovered]

        Then choose seeded-uniformly among tied maximum-score pairs.
        """
        uncovered_d1 = frozenset(
            coverage.uncovered(Distance.D1)
        )
        uncovered_d2 = frozenset(
            coverage.uncovered(Distance.D2)
        )

        best_score = -1
        best_pairs: list[tuple[int, int]] = []

        # Iteration order is explicitly canonical.
        for d1_register in POSITIVE_REGISTERS:
            for d2_register in POSITIVE_REGISTERS:
                if d1_register == d2_register:
                    continue

                score = (
                    int(d1_register in uncovered_d1)
                    + int(d2_register in uncovered_d2)
                )

                if score > best_score:
                    best_score = score
                    best_pairs = [
                        (d1_register, d2_register)
                    ]
                elif score == best_score:
                    best_pairs.append(
                        (d1_register, d2_register)
                    )

        if not best_pairs:
            # Architecturally unreachable with x1..x31,
            # but retained as a fail-fast invariant.
            raise RuntimeError(
                "no legal distinct A4 target-register pair"
            )

        d1_register, d2_register = self._rng.choice(best_pairs)

        return TargetSelection(
            d1=d1_register,
            d2=d2_register,
        )
