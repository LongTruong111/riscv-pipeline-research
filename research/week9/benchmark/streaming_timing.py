"""Bounded streaming timing oracle and performance monitor for Week 9.

The timing oracle reuses the frozen Week-7 semantic helpers and emits
one TimingExpectationV1 at a time instead of retaining an O(N)
TimingScheduleV1.

The performance monitor retains only expectations that have been
accepted but not yet retired.
"""

from typing import Dict, Mapping

from research.week5.impl.execution_event import ExecutionEvent
from research.week7.retire_monitor import RetireEvent
from research.week7.timing_oracle_v1 import (
    REDIRECT_BUBBLES,
    RETIRE_LATENCY,
    TimingExpectationV1,
    TimingProgramError,
    _Producer,
    _branch_taken,
    _decode_checked,
    _execution_event,
    _forward_for_age,
)
from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week8.performance_monitor import (
    PerformanceMonitorProtocolError,
    PerformanceResult,
)


class StreamingTimingOracleV1:
    """Streaming equivalent of frozen Timing Oracle v1.

    Retained state:
        - immutable finite program mapping;
        - 32-register architectural model;
        - latest writer for at most 31 GPRs;
        - scalar cycle/instruction counters.

    With a fixed-size benchmark program and bounded memory-address
    footprint, retained timing-oracle state is O(1) with respect to
    campaign length.
    """

    def __init__(
        self,
        program: Mapping[int, int],
    ) -> None:
        normalized: Dict[int, int] = {}

        for pc, instruction in program.items():
            if pc < 0:
                raise ValueError(
                    "program PC must be non-negative"
                )

            if pc & 0x3:
                raise ValueError(
                    "program PC must be 4-byte aligned, "
                    f"got {pc:#x}"
                )

            if not 0 <= instruction <= 0xFFFFFFFF:
                raise ValueError(
                    f"instruction at PC {pc:#x} "
                    "does not fit 32 bits"
                )

            normalized[int(pc)] = int(instruction)

        if not normalized:
            raise ValueError(
                "streaming timing program must not be empty"
            )

        if 0 not in normalized:
            raise TimingProgramError(
                "Timing Oracle v1 currently requires "
                "entry PC 0"
            )

        self._program = normalized
        self._model = RV32ArchitecturalModel()

        self._last_writer: Dict[int, _Producer] = {}

        self._next_instruction_id = 1
        self._next_accept_cycle = 1
        self._generated_count = 0

    @property
    def generated_count(self) -> int:
        return self._generated_count

    @property
    def writer_count(self) -> int:
        return len(self._last_writer)

    @property
    def expected_pc(self) -> int:
        return self._model.expected_pc

    def next_expectation(
        self,
    ) -> TimingExpectationV1:
        """Generate exactly one independent timing expectation."""

        pc = self._model.expected_pc

        try:
            instruction = self._program[pc]
        except KeyError as exc:
            raise TimingProgramError(
                "expected PC is outside streaming program: "
                f"pc={pc:#x}"
            ) from exc

        instruction_id = self._next_instruction_id

        decoded = _decode_checked(instruction)

        producer_a = None
        producer_b = None

        if decoded.uses_rs1 and decoded.rs1 != 0:
            producer_a = self._last_writer.get(
                decoded.rs1
            )

        if decoded.uses_rs2 and decoded.rs2 != 0:
            producer_b = self._last_writer.get(
                decoded.rs2
            )

        candidate_cycle = self._next_accept_cycle

        needs_load_stall = False

        for producer in (
            producer_a,
            producer_b,
        ):
            if producer is None:
                continue

            age_before_stall = (
                candidate_cycle
                - producer.accept_cycle
            )

            if (
                producer.decoded.producer_type
                == "MEM_DATA"
                and age_before_stall == 1
            ):
                needs_load_stall = True

        stall_cycles = (
            1 if needs_load_stall else 0
        )

        accept_cycle = (
            candidate_cycle
            + stall_cycles
        )

        source_a_age = (
            None
            if producer_a is None
            else (
                accept_cycle
                - producer_a.accept_cycle
            )
        )

        source_b_age = (
            None
            if producer_b is None
            else (
                accept_cycle
                - producer_b.accept_cycle
            )
        )

        forward_a = _forward_for_age(
            source_a_age
        )

        forward_b = _forward_for_age(
            source_b_age
        )

        for role, producer, age in (
            ("RS1", producer_a, source_a_age),
            ("RS2", producer_b, source_b_age),
        ):
            if (
                producer is not None
                and producer.decoded.producer_type
                == "MEM_DATA"
                and age == 1
            ):
                raise TimingProgramError(
                    f"{role}: unresolved load-use hazard"
                )

        if decoded.mnemonic in {
            "JAL",
            "JALR",
        }:
            redirect = True

        elif decoded.mnemonic in {
            "BEQ",
            "BNE",
            "BLT",
            "BGE",
            "BLTU",
            "BGEU",
        }:
            redirect = _branch_taken(
                decoded,
                self._model,
            )

        else:
            redirect = False

        redirect_bubbles = (
            REDIRECT_BUBBLES
            if redirect
            else 0
        )

        event = _execution_event(
            instruction_id=instruction_id,
            cycle=accept_cycle,
            pc=pc,
            instruction=instruction,
            decoded=decoded,
        )

        step = self._model.step(event)

        if not step.pc_match:
            raise TimingProgramError(
                "internal streaming timing oracle "
                "PC mismatch"
            )

        expectation = TimingExpectationV1(
            instruction_id=instruction_id,
            pc=pc,
            instruction=instruction,
            mnemonic=decoded.mnemonic,
            accept_cycle=accept_cycle,
            stall_cycles_before_accept=(
                stall_cycles
            ),
            retire_cycle=(
                accept_cycle
                + RETIRE_LATENCY
            ),
            forward_a=forward_a,
            forward_b=forward_b,
            source_a_producer_id=(
                None
                if producer_a is None
                else producer_a.instruction_id
            ),
            source_b_producer_id=(
                None
                if producer_b is None
                else producer_b.instruction_id
            ),
            source_a_cycle_age=source_a_age,
            source_b_cycle_age=source_b_age,
            redirect=redirect,
            redirect_bubbles=(
                redirect_bubbles
            ),
        )

        if (
            decoded.writes_rd
            and decoded.rd != 0
        ):
            self._last_writer[
                decoded.rd
            ] = _Producer(
                instruction_id=instruction_id,
                accept_cycle=accept_cycle,
                decoded=decoded,
            )

        self._next_accept_cycle = (
            accept_cycle
            + 1
            + redirect_bubbles
        )

        self._next_instruction_id += 1
        self._generated_count += 1

        return expectation

    def observe_accept(
        self,
        event: ExecutionEvent,
    ) -> TimingExpectationV1:
        """Generate and identity-check expectation for one DUT accept.

        Expected control flow and instruction fetch come from the
        independent program/model, not from DUT-observed PC.
        """

        if not isinstance(event, ExecutionEvent):
            raise TypeError(
                "event must be an ExecutionEvent"
            )

        expectation = self.next_expectation()

        if (
            event.instruction_index
            != expectation.instruction_id
        ):
            raise TimingProgramError(
                "accepted instruction ID mismatch: "
                f"expected "
                f"{expectation.instruction_id}, "
                f"got {event.instruction_index}"
            )

        if event.pc != expectation.pc:
            raise TimingProgramError(
                "accepted PC mismatch: "
                f"expected {expectation.pc:#x}, "
                f"got {event.pc:#x}"
            )

        if (
            event.instruction
            != expectation.instruction
        ):
            raise TimingProgramError(
                "accepted instruction mismatch: "
                f"expected "
                f"0x{expectation.instruction:08x}, "
                f"got 0x{event.instruction:08x}"
            )

        return expectation


class StreamingPerformanceMonitor:
    """Bounded equivalent of Week-8 PerformanceMonitor.

    Expectations are registered at instruction acceptance and removed
    immediately at logical retirement. Aggregate history is represented
    only by scalar counters.
    """

    def __init__(self) -> None:
        self._expected_by_id: Dict[
            int,
            TimingExpectationV1,
        ] = {}

        self._registered_count = 0
        self._checked_count = 0
        self._passed_count = 0
        self._failed_count = 0
        self._late_count = 0
        self._early_count = 0

        self._total_excess_cycles = 0
        self._max_excess_cycles = 0
        self._total_early_cycles = 0

        self._last_observed_id = 0

    @property
    def expected_count(self) -> int:
        return self._registered_count

    @property
    def checked_count(self) -> int:
        return self._checked_count

    @property
    def passed_count(self) -> int:
        return self._passed_count

    @property
    def failed_count(self) -> int:
        return self._failed_count

    @property
    def late_count(self) -> int:
        return self._late_count

    @property
    def early_count(self) -> int:
        return self._early_count

    @property
    def total_excess_cycles(self) -> int:
        return self._total_excess_cycles

    @property
    def max_excess_cycles(self) -> int:
        return self._max_excess_cycles

    @property
    def total_early_cycles(self) -> int:
        return self._total_early_cycles

    @property
    def pending_count(self) -> int:
        return len(self._expected_by_id)

    @property
    def complete(self) -> bool:
        return (
            self._checked_count
            == self._registered_count
            and not self._expected_by_id
        )

    @property
    def overall_pass(self) -> bool:
        return (
            self.complete
            and self._failed_count == 0
        )

    def register_expectation(
        self,
        expectation: TimingExpectationV1,
    ) -> None:
        if not isinstance(
            expectation,
            TimingExpectationV1,
        ):
            raise TypeError(
                "expectation must be "
                "TimingExpectationV1"
            )

        expected_id = (
            self._registered_count + 1
        )

        if (
            expectation.instruction_id
            != expected_id
        ):
            raise ValueError(
                "timing expectation stream must "
                "be contiguous: "
                f"expected instruction_id="
                f"{expected_id}, got "
                f"{expectation.instruction_id}"
            )

        if (
            expectation.instruction_id
            in self._expected_by_id
        ):
            raise ValueError(
                "duplicate timing expectation"
            )

        self._expected_by_id[
            expectation.instruction_id
        ] = expectation

        self._registered_count += 1

    def observe_retire(
        self,
        retire: RetireEvent,
    ) -> PerformanceResult:
        if not isinstance(retire, RetireEvent):
            raise TypeError(
                "retire must be a RetireEvent"
            )

        instruction_id = retire.instruction_id

        try:
            expected = self._expected_by_id[
                instruction_id
            ]
        except KeyError as exc:
            raise PerformanceMonitorProtocolError(
                "retirement has no matching "
                "timing expectation: "
                f"instruction_id={instruction_id}"
            ) from exc

        expected_next_id = (
            self._last_observed_id + 1
        )

        if (
            instruction_id
            != expected_next_id
        ):
            raise PerformanceMonitorProtocolError(
                "performance retire order violation: "
                f"expected instruction_id="
                f"{expected_next_id}, got "
                f"{instruction_id}"
            )

        delta = (
            retire.cycle
            - expected.retire_cycle
        )

        result = PerformanceResult(
            instruction_id=instruction_id,
            expected_retire_cycle=(
                expected.retire_cycle
            ),
            observed_retire_cycle=(
                retire.cycle
            ),
            delta_cycles=delta,
        )

        del self._expected_by_id[
            instruction_id
        ]

        self._last_observed_id = instruction_id
        self._checked_count += 1

        if result.passed:
            self._passed_count += 1
        else:
            self._failed_count += 1

        if result.late:
            self._late_count += 1
            self._total_excess_cycles += (
                result.delta_cycles
            )
            self._max_excess_cycles = max(
                self._max_excess_cycles,
                result.delta_cycles,
            )

        elif result.early:
            self._early_count += 1
            self._total_early_cycles += (
                -result.delta_cycles
            )

        return result
