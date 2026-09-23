"""Bounded immutable first-failure capture for Week 12."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True, slots=True)
class FailureRecord:
    instruction_id: int
    cycle: int
    pc: int
    instruction: int
    checker: str
    check_name: str
    expected: Any
    observed: Any
    forward_a: Optional[int] = None
    forward_b: Optional[int] = None
    stall_cycles_before_accept: Optional[int] = None

    def __post_init__(self) -> None:
        if self.instruction_id <= 0:
            raise ValueError("instruction_id must be positive")

        if self.cycle < 0:
            raise ValueError("cycle must be non-negative")

        if not 0 <= self.pc <= 0x1FF:
            raise ValueError("pc must fit frozen 9-bit PC")

        if not 0 <= self.instruction <= 0xFFFFFFFF:
            raise ValueError("instruction must fit 32 bits")

        if not self.checker:
            raise ValueError("checker must not be empty")

        if not self.check_name:
            raise ValueError("check_name must not be empty")

        for name, value in (
            ("forward_a", self.forward_a),
            ("forward_b", self.forward_b),
        ):
            if value is not None and not 0 <= value <= 0b11:
                raise ValueError(
                    f"{name} must be None or a 2-bit value"
                )

        if (
            self.stall_cycles_before_accept is not None
            and self.stall_cycles_before_accept < 0
        ):
            raise ValueError(
                "stall_cycles_before_accept must be non-negative"
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FirstFailureRecorder:
    """
    Retain only immutable first-failure evidence.

    State is O(1) with respect to campaign length.
    """

    VALID_KINDS = frozenset({
        "control",
        "functional",
        "performance",
    })

    def __init__(self) -> None:
        self._first_failure: Optional[FailureRecord] = None
        self._by_kind: Dict[str, Optional[FailureRecord]] = {
            kind: None
            for kind in self.VALID_KINDS
        }

    @property
    def first_failure(self) -> Optional[FailureRecord]:
        return self._first_failure

    @property
    def first_control_failure(self) -> Optional[FailureRecord]:
        return self._by_kind["control"]

    @property
    def first_functional_failure(self) -> Optional[FailureRecord]:
        return self._by_kind["functional"]

    @property
    def first_performance_failure(self) -> Optional[FailureRecord]:
        return self._by_kind["performance"]

    @property
    def empty(self) -> bool:
        return self._first_failure is None

    def record(
        self,
        kind: str,
        failure: FailureRecord,
    ) -> bool:
        """
        Record failure if this is the first failure for the requested kind.

        Returns True only when the per-kind slot was written.
        Previously recorded evidence is never replaced.
        """
        if kind not in self.VALID_KINDS:
            raise ValueError(
                f"unknown failure kind {kind!r}"
            )

        if not isinstance(failure, FailureRecord):
            raise TypeError(
                "failure must be FailureRecord"
            )

        if self._first_failure is None:
            self._first_failure = failure

        if self._by_kind[kind] is not None:
            return False

        self._by_kind[kind] = failure
        return True

    def snapshot(self) -> Dict[str, Any]:
        def encode(
            record: Optional[FailureRecord],
        ) -> Optional[Dict[str, Any]]:
            if record is None:
                return None
            return record.to_dict()

        return {
            "first_failure": encode(
                self._first_failure
            ),
            "first_control_failure": encode(
                self._by_kind["control"]
            ),
            "first_functional_failure": encode(
                self._by_kind["functional"]
            ),
            "first_performance_failure": encode(
                self._by_kind["performance"]
            ),
        }
