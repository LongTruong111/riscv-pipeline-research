from dataclasses import dataclass
from typing import Any, Tuple

from research.week5.impl.execution_event import ExecutionEvent
from research.week5.impl.l1_coverage import (
    L1_BIN_IDS,
    L1Hit,
)
from research.week7.retire_monitor import RetireEvent
from research.week7.timing_oracle_v1 import TimingExpectationV1


@dataclass(frozen=True, slots=True)
class TimingObservation:
    """
    Observed timing/control state for one accepted instruction.

    This is deliberately separated from TimingExpectationV1 so expected
    values never come from DUT observations.
    """

    instruction_id: int
    pc: int
    instruction: int

    accept_cycle: int
    stall_cycles_before_accept: int

    forward_a: int
    forward_b: int

    @classmethod
    def from_execution_event(
        cls,
        event: ExecutionEvent,
    ) -> "TimingObservation":
        return cls(
            instruction_id=event.instruction_index,
            pc=event.pc,
            instruction=event.instruction,
            accept_cycle=event.cycle,
            stall_cycles_before_accept=(
                event.stall_cycles_before_accept
            ),
            forward_a=event.forward_a,
            forward_b=event.forward_b,
        )


@dataclass(frozen=True, slots=True)
class AttributionCheck:
    name: str
    expected: Any
    observed: Any

    @property
    def passed(self) -> bool:
        return self.expected == self.observed


@dataclass(frozen=True, slots=True)
class HazardAttribution:
    """
    Trace one frozen L1 Intent hit through timing and retirement.
    """

    bin_id: str

    consumer_instruction_id: int
    producer_instruction_ids: Tuple[int, ...]
    matched_sources: Tuple[str, ...]

    checks: Tuple[AttributionCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> Tuple[AttributionCheck, ...]:
        return tuple(
            check
            for check in self.checks
            if not check.passed
        )


def _source_producer_id(
    expectation: TimingExpectationV1,
    role: str,
):
    if role == "RS1":
        return expectation.source_a_producer_id

    if role == "RS2":
        return expectation.source_b_producer_id

    if role == "RAW_RS2_UNUSED":
        # H20 intentionally represents a raw encoding coincidence,
        # not an architectural source dependency.
        return None

    raise ValueError(
        f"unsupported matched source role: {role}"
    )


def correlate_hazard(
    hit: L1Hit,
    expectation: TimingExpectationV1,
    observation: TimingObservation,
    retire: RetireEvent,
) -> HazardAttribution:
    """
    Correlate one Intent hit with expected timing, observed timing,
    and final retirement.

    Structural identity mismatches raise ValueError because they indicate
    malformed correlation input rather than a DUT timing failure.

    Behavioral mismatches are returned as failed AttributionCheck objects.
    """

    if hit.bin_id not in L1_BIN_IDS:
        raise ValueError(
            f"unknown L1 bin: {hit.bin_id}"
        )

    consumer_id = hit.consumer_instruction_index

    identities = {
        "expectation": expectation.instruction_id,
        "observation": observation.instruction_id,
        "retire": retire.instruction_id,
    }

    for source, instruction_id in identities.items():
        if instruction_id != consumer_id:
            raise ValueError(
                f"{source} instruction_id does not match "
                f"L1Hit consumer: expected {consumer_id}, "
                f"got {instruction_id}"
            )

    for producer_id in hit.producer_instruction_indices:
        if producer_id <= 0:
            raise ValueError(
                "producer instruction IDs must be positive"
            )

        if producer_id >= consumer_id:
            raise ValueError(
                "producer must precede consumer in executed "
                "program order"
            )

    checks = [
        AttributionCheck(
            name="pc",
            expected=expectation.pc,
            observed=observation.pc,
        ),
        AttributionCheck(
            name="instruction",
            expected=expectation.instruction,
            observed=observation.instruction,
        ),
        AttributionCheck(
            name="accept_cycle",
            expected=expectation.accept_cycle,
            observed=observation.accept_cycle,
        ),
        AttributionCheck(
            name="stall_cycles_before_accept",
            expected=expectation.stall_cycles_before_accept,
            observed=observation.stall_cycles_before_accept,
        ),
        AttributionCheck(
            name="forward_a",
            expected=expectation.forward_a,
            observed=observation.forward_a,
        ),
        AttributionCheck(
            name="forward_b",
            expected=expectation.forward_b,
            observed=observation.forward_b,
        ),
        AttributionCheck(
            name="retire_cycle",
            expected=expectation.retire_cycle,
            observed=retire.cycle,
        ),
    ]

    # --------------------------------------------------------------
    # Intent-producer attribution.
    #
    # Positive RAW bins must agree with Timing Oracle producer
    # identities. Negative semantic bins H18-H20 deliberately do not.
    # --------------------------------------------------------------
    if hit.bin_id in {"H18", "H19"}:
        # x0 has no architectural producer.
        for role in hit.matched_sources:
            checks.append(
                AttributionCheck(
                    name=f"{role.lower()}_producer_excluded",
                    expected=None,
                    observed=_source_producer_id(
                        expectation,
                        role,
                    ),
                )
            )

    elif hit.bin_id == "H20":
        checks.append(
            AttributionCheck(
                name="unused_raw_rs2_excluded",
                expected=None,
                observed=expectation.source_b_producer_id,
            )
        )

    elif hit.bin_id == "H10":
        # H10 has two distinct producers. Source orientation may vary,
        # so compare the producer set rather than tuple ordering.
        timing_producers = {
            producer_id
            for producer_id in (
                expectation.source_a_producer_id,
                expectation.source_b_producer_id,
            )
            if producer_id is not None
        }

        checks.append(
            AttributionCheck(
                name="dual_producer_identity",
                expected=frozenset(
                    hit.producer_instruction_indices
                ),
                observed=frozenset(timing_producers),
            )
        )

    elif hit.bin_id == "H17":
        # H17 records older + newer writers. Only the newest writer is
        # the actual source selected for the consumer.
        newest_producer = max(
            hit.producer_instruction_indices
        )

        for role in hit.matched_sources:
            checks.append(
                AttributionCheck(
                    name=f"{role.lower()}_newest_producer",
                    expected=newest_producer,
                    observed=_source_producer_id(
                        expectation,
                        role,
                    ),
                )
            )

    else:
        # H01-H16 excluding H10:
        # every semantic matched source must resolve to one of the
        # producer IDs carried by the frozen L1 hit.
        allowed_producers = set(
            hit.producer_instruction_indices
        )

        for role in hit.matched_sources:
            actual_producer = _source_producer_id(
                expectation,
                role,
            )

            checks.append(
                AttributionCheck(
                    name=f"{role.lower()}_producer_identity",
                    expected=True,
                    observed=(
                        actual_producer in allowed_producers
                    ),
                )
            )

    return HazardAttribution(
        bin_id=hit.bin_id,
        consumer_instruction_id=consumer_id,
        producer_instruction_ids=(
            hit.producer_instruction_indices
        ),
        matched_sources=hit.matched_sources,
        checks=tuple(checks),
    )
