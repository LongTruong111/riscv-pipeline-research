"""Authoritative per-hit L2 realization checking.

Implements the Week-10 L2 realization contract without modifying
frozen Week-5 through Week-8 semantics.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from research.week5.impl.coverage_model import D1, D2, L2Hit
from research.week5.impl.execution_event import ExecutionEvent
from research.week6.expected_retire import ExpectedRetire
from research.week7.timing_oracle_v1 import TimingExpectationV1


_ARCHITECTURAL_KINDS = frozenset(
    {
        "pc",
        "store",
        "writeback",
        "x0",
        "next_pc",
    }
)


@dataclass(frozen=True, slots=True)
class L2ControlCheck:
    name: str
    expected: object
    observed: object

    @property
    def passed(self) -> bool:
        return self.expected == self.observed


@dataclass(frozen=True, slots=True)
class L2ControlResult:
    hit: L2Hit
    checks: Tuple[L2ControlCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> Tuple[L2ControlCheck, ...]:
        return tuple(
            check
            for check in self.checks
            if not check.passed
        )


@dataclass(frozen=True, slots=True)
class L2ValidationOutcome:
    hit: L2Hit
    control_passed: bool
    architectural_passed: Optional[bool]
    validated: bool

    failed_architectural_checks: Tuple[
        Tuple[int, str], ...
    ] = ()


@dataclass(frozen=True, slots=True)
class _PendingHit:
    hit: L2Hit
    required_checks: Tuple[
        Tuple[int, str], ...
    ]


def _expected_producer(
    expectation: TimingExpectationV1,
    role: str,
):
    if role == "RS1":
        return expectation.source_a_producer_id

    if role == "RS2":
        return expectation.source_b_producer_id

    raise ValueError(f"unsupported source role: {role}")


def _expected_forward(
    expectation: TimingExpectationV1,
    role: str,
) -> int:
    if role == "RS1":
        return expectation.forward_a

    if role == "RS2":
        return expectation.forward_b

    raise ValueError(f"unsupported source role: {role}")


def _observed_forward(
    consumer: ExecutionEvent,
    role: str,
) -> int:
    if role == "RS1":
        return consumer.forward_a

    if role == "RS2":
        return consumer.forward_b

    raise ValueError(f"unsupported source role: {role}")


def check_l2_source_control(
    hit: L2Hit,
    consumer: ExecutionEvent,
    expectation: TimingExpectationV1,
) -> L2ControlResult:
    """Check source-specific control realization for one L2 hit."""

    if hit.distance not in (D1, D2):
        raise ValueError(
            f"L2 distance must be d1/d2, got {hit.distance}"
        )

    if not 1 <= hit.register <= 31:
        raise ValueError(
            "positive L2 register must be x1..x31"
        )

    if (
        hit.consumer_instruction_index
        != consumer.instruction_index
    ):
        raise ValueError(
            "L2Hit consumer does not match ExecutionEvent"
        )

    if (
        expectation.instruction_id
        != consumer.instruction_index
    ):
        raise ValueError(
            "TimingExpectation consumer identity mismatch"
        )

    if (
        consumer.instruction_index
        - hit.producer_instruction_index
        != hit.distance
    ):
        raise ValueError(
            "L2 producer/consumer distance is inconsistent"
        )

    if expectation.pc != consumer.pc:
        raise ValueError(
            "TimingExpectation PC does not match consumer"
        )

    if expectation.instruction != consumer.instruction:
        raise ValueError(
            "TimingExpectation instruction does not match consumer"
        )

    roles: List[str] = []

    if consumer.uses_rs1 and consumer.rs1 == hit.register:
        roles.append("RS1")

    if consumer.uses_rs2 and consumer.rs2 == hit.register:
        roles.append("RS2")

    if not roles:
        raise ValueError(
            "L2 register is not an architectural consumer source"
        )

    checks: List[L2ControlCheck] = [
        L2ControlCheck(
            name="stall_cycles_before_accept",
            expected=expectation.stall_cycles_before_accept,
            observed=consumer.stall_cycles_before_accept,
        )
    ]

    for role in roles:
        checks.append(
            L2ControlCheck(
                name=f"{role.lower()}_producer_identity",
                expected=hit.producer_instruction_index,
                observed=_expected_producer(
                    expectation,
                    role,
                ),
            )
        )

        checks.append(
            L2ControlCheck(
                name=f"forward_{role.lower()}",
                expected=_expected_forward(
                    expectation,
                    role,
                ),
                observed=_observed_forward(
                    consumer,
                    role,
                ),
            )
        )

    return L2ControlResult(
        hit=hit,
        checks=tuple(checks),
    )


def successor_pc_pass(
    expected: ExpectedRetire,
    successor: ExecutionEvent,
) -> bool:
    """Validate predecessor next-PC without truncating Golden PC."""

    if (
        successor.instruction_index
        != expected.instruction_id + 1
    ):
        raise ValueError(
            "successor instruction ID must be contiguous"
        )

    return successor.pc == expected.next_pc


class L2ValidatedCoverageChecker:
    """Bounded authoritative per-hit L2 validation layer."""

    def __init__(self) -> None:
        self._architectural_results: Dict[
            int,
            Dict[str, bool],
        ] = {}

        self._pending_by_consumer: Dict[
            int,
            List[_PendingHit],
        ] = {}

        self._attempt_count = 0
        self._validated_hit_count = 0
        self._rejected_hit_count = 0

    @property
    def attempt_count(self) -> int:
        return self._attempt_count

    @property
    def validated_hit_count(self) -> int:
        return self._validated_hit_count

    @property
    def rejected_hit_count(self) -> int:
        return self._rejected_hit_count

    @property
    def pending_hits(self) -> int:
        return sum(
            len(items)
            for items in self._pending_by_consumer.values()
        )

    @property
    def architectural_cache_entries(self) -> int:
        return len(self._architectural_results)

    @staticmethod
    def _participant_requirements(
        event: ExecutionEvent,
    ) -> Tuple[Tuple[int, str], ...]:
        kinds = [
            "pc",
            "store",
            "writeback",
            "next_pc",
        ]

        if event.writes_rd and event.rd == 0:
            kinds.append("x0")

        return tuple(
            (event.instruction_index, kind)
            for kind in kinds
        )

    @classmethod
    def _required_checks(
        cls,
        hit: L2Hit,
        producer: ExecutionEvent,
        consumer: ExecutionEvent,
    ) -> Tuple[Tuple[int, str], ...]:
        if (
            producer.instruction_index
            != hit.producer_instruction_index
        ):
            raise ValueError(
                "producer event does not match L2Hit"
            )

        if (
            consumer.instruction_index
            != hit.consumer_instruction_index
        ):
            raise ValueError(
                "consumer event does not match L2Hit"
            )

        if not producer.writes_rd:
            raise ValueError(
                "positive L2 producer must write rd"
            )

        if producer.rd != hit.register:
            raise ValueError(
                "producer rd does not match L2 register"
            )

        if producer.rd == 0:
            raise ValueError(
                "x0 cannot be a positive L2 producer"
            )

        result = []

        for participant in (producer, consumer):
            for check in cls._participant_requirements(
                participant
            ):
                if check not in result:
                    result.append(check)

        return tuple(result)

    def _evaluate(
        self,
        pending: _PendingHit,
    ) -> Optional[L2ValidationOutcome]:
        for instruction_id, kind in pending.required_checks:
            per_instruction = (
                self._architectural_results.get(
                    instruction_id
                )
            )

            if (
                per_instruction is None
                or kind not in per_instruction
            ):
                return None

        failed = tuple(
            (instruction_id, kind)
            for instruction_id, kind
            in pending.required_checks
            if not self._architectural_results[
                instruction_id
            ][kind]
        )

        passed = not failed

        if passed:
            self._validated_hit_count += 1
        else:
            self._rejected_hit_count += 1

        return L2ValidationOutcome(
            hit=pending.hit,
            control_passed=True,
            architectural_passed=passed,
            validated=passed,
            failed_architectural_checks=failed,
        )

    def _try_finalize_consumer(
        self,
        consumer_id: int,
    ) -> Tuple[L2ValidationOutcome, ...]:
        pending = self._pending_by_consumer.get(
            consumer_id
        )

        if not pending:
            return ()

        outcomes = []
        remaining = []

        for item in pending:
            outcome = self._evaluate(item)

            if outcome is None:
                remaining.append(item)
            else:
                outcomes.append(outcome)

        if remaining:
            self._pending_by_consumer[
                consumer_id
            ] = remaining
        else:
            del self._pending_by_consumer[
                consumer_id
            ]

        return tuple(outcomes)

    def _try_finalize_all(
        self,
    ) -> Tuple[L2ValidationOutcome, ...]:
        outcomes = []

        for consumer_id in tuple(
            self._pending_by_consumer
        ):
            outcomes.extend(
                self._try_finalize_consumer(
                    consumer_id
                )
            )

        return tuple(outcomes)

    def register_hit(
        self,
        hit: L2Hit,
        *,
        control: L2ControlResult,
        producer: ExecutionEvent,
        consumer: ExecutionEvent,
    ) -> Tuple[L2ValidationOutcome, ...]:
        if control.hit != hit:
            raise ValueError(
                "control result does not belong to L2Hit"
            )

        self._attempt_count += 1

        if not control.passed:
            self._rejected_hit_count += 1

            return (
                L2ValidationOutcome(
                    hit=hit,
                    control_passed=False,
                    architectural_passed=None,
                    validated=False,
                ),
            )

        required = self._required_checks(
            hit,
            producer,
            consumer,
        )

        existing = self._pending_by_consumer.get(
            hit.consumer_instruction_index,
            (),
        )

        if any(item.hit == hit for item in existing):
            raise ValueError(
                "duplicate unresolved L2Hit registration"
            )

        self._pending_by_consumer.setdefault(
            hit.consumer_instruction_index,
            [],
        ).append(
            _PendingHit(
                hit=hit,
                required_checks=required,
            )
        )

        return self._try_finalize_consumer(
            hit.consumer_instruction_index
        )

    def record_architectural_result(
        self,
        *,
        instruction_id: int,
        kind: str,
        passed: bool,
    ) -> Tuple[L2ValidationOutcome, ...]:
        if instruction_id <= 0:
            raise ValueError(
                "instruction_id must be positive"
            )

        if kind not in _ARCHITECTURAL_KINDS:
            raise ValueError(
                f"unsupported architectural result kind: {kind}"
            )

        per_instruction = (
            self._architectural_results.setdefault(
                instruction_id,
                {},
            )
        )

        value = bool(passed)

        if kind in per_instruction:
            if per_instruction[kind] != value:
                raise ValueError(
                    "conflicting architectural result: "
                    f"instruction_id={instruction_id}, "
                    f"kind={kind}"
                )

            return ()

        per_instruction[kind] = value

        return self._try_finalize_all()

    def prune(
        self,
        *,
        latest_instruction_id: int,
    ) -> None:
        if latest_instruction_id <= 0:
            raise ValueError(
                "latest_instruction_id must be positive"
            )

        retained_by_pending = set()

        for items in self._pending_by_consumer.values():
            for item in items:
                retained_by_pending.update(
                    instruction_id
                    for instruction_id, _
                    in item.required_checks
                )

        keep_from = max(
            1,
            latest_instruction_id - 5,
        )

        for instruction_id in tuple(
            self._architectural_results
        ):
            if (
                instruction_id < keep_from
                and instruction_id
                not in retained_by_pending
            ):
                del self._architectural_results[
                    instruction_id
                ]
