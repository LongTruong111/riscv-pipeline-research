from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Optional, Tuple

from research.week5.impl.isa_decode import (
    DecodedInstruction,
    decode_instruction,
)


FORWARD_RF = 0b00
FORWARD_MEM_WB = 0b01
FORWARD_EX_MEM = 0b10


class UnsupportedTimingInstruction(ValueError):
    pass


class UnsupportedTimingScenario(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TimingExpectation:
    """
    Timing Oracle v0 expectation for one executed instruction.

    Dependency distance is measured in executed-program order.
    No absolute cycle/retire timing is modeled in v0.
    """

    instruction_index: int
    mnemonic: str

    stall_cycles_before_accept: int

    forward_a: int
    forward_b: int

    source_a_distance: Optional[int]
    source_b_distance: Optional[int]

    source_a_producer_type: Optional[str]
    source_b_producer_type: Optional[str]

    reason: str


@dataclass(frozen=True, slots=True)
class _HistoryEntry:
    instruction_index: int
    decoded: DecodedInstruction


@dataclass(frozen=True, slots=True)
class _Dependency:
    role: str
    distance: int
    producer: _HistoryEntry


_EXACT_T6_MNEMONICS = {
    "ADD",
    "ADDI",
    "LW",
    "SW",
    "LUI",
    "AUIPC",
    "JAL",
    "JALR",
    "BEQ",
    "BNE",
    "BLT",
    "BGE",
    "BLTU",
    "BGEU",
}

_CONTROL_FLOW_MNEMONICS = {
    "JAL",
    "JALR",
    "BEQ",
    "BNE",
    "BLT",
    "BGE",
    "BLTU",
    "BGEU",
}

_V0_HAZARD_CONSUMERS = {
    "ADD",
    "ADDI",
}


class TimingOracleV0:
    """
    Bounded-state timing oracle for the frozen Week-6 v0 scope.

    State:
        previous two executed instructions only.

    Supported dependency classes:
        ALU_RESULT d1 -> EX/MEM
        ALU_RESULT d2 -> MEM/WB
        MEM_DATA   d1 -> one stall then MEM/WB
        MEM_DATA   d2 -> MEM/WB

    DUT-observed stall/forward signals are never used as oracle input.
    """

    def __init__(self) -> None:
        self._history: Deque[_HistoryEntry] = deque(maxlen=2)
        self._next_instruction_index = 1

    @property
    def instructions_observed(self) -> int:
        return self._next_instruction_index - 1

    def reset(self) -> None:
        self._history.clear()
        self._next_instruction_index = 1

    @staticmethod
    def _decode_checked(instruction: int) -> DecodedInstruction:
        decoded = decode_instruction(instruction)

        if decoded is None:
            raise UnsupportedTimingInstruction(
                f"unsupported instruction 0x{instruction:08x}"
            )

        if decoded.mnemonic not in _EXACT_T6_MNEMONICS:
            raise UnsupportedTimingInstruction(
                "instruction is structurally decoded but is outside "
                f"the exact T6 subset: {decoded.mnemonic}"
            )

        return decoded

    def _nearest_writer(
        self,
        register: int,
    ) -> Optional[Tuple[_HistoryEntry, int]]:
        if register == 0:
            return None

        for distance, previous in enumerate(
            reversed(self._history),
            start=1,
        ):
            producer = previous.decoded

            if (
                producer.writes_rd
                and producer.rd != 0
                and producer.rd == register
            ):
                return previous, distance

        return None

    def _dependency(
        self,
        *,
        role: str,
        register: int,
    ) -> Optional[_Dependency]:
        match = self._nearest_writer(register)

        if match is None:
            return None

        producer, distance = match

        return _Dependency(
            role=role,
            distance=distance,
            producer=producer,
        )

    def observe(
        self,
        instruction: int,
    ) -> TimingExpectation:
        decoded = self._decode_checked(instruction)

        if decoded.mnemonic in _CONTROL_FLOW_MNEMONICS:
            raise UnsupportedTimingScenario(
                f"{decoded.mnemonic} timing is deferred to Timing Oracle v1"
            )

        instruction_index = self._next_instruction_index

        dependencies = []

        if decoded.uses_rs1:
            dep = self._dependency(
                role="RS1",
                register=decoded.rs1,
            )
            if dep is not None:
                dependencies.append(dep)

        if decoded.uses_rs2:
            dep = self._dependency(
                role="RS2",
                register=decoded.rs2,
            )
            if dep is not None:
                dependencies.append(dep)

        # ----------------------------------------------------------
        # No RAW dependency in d1/d2.
        # ----------------------------------------------------------
        if not dependencies:
            expectation = TimingExpectation(
                instruction_index=instruction_index,
                mnemonic=decoded.mnemonic,
                stall_cycles_before_accept=0,
                forward_a=FORWARD_RF,
                forward_b=FORWARD_RF,
                source_a_distance=None,
                source_b_distance=None,
                source_a_producer_type=None,
                source_b_producer_type=None,
                reason="NO_HAZARD",
            )

            self._commit(decoded)
            return expectation

        # Timing v0 only models dependencies consumed by ADD/ADDI.
        if decoded.mnemonic not in _V0_HAZARD_CONSUMERS:
            raise UnsupportedTimingScenario(
                "Timing Oracle v0 models RAW timing only for "
                "ADD/ADDI consumers"
            )

        # Reject producer classes deliberately deferred from v0.
        for dep in dependencies:
            producer_type = dep.producer.decoded.producer_type

            if producer_type not in {
                "ALU_RESULT",
                "MEM_DATA",
            }:
                raise UnsupportedTimingScenario(
                    "producer type is outside Timing Oracle v0: "
                    f"{producer_type}"
                )

        # ----------------------------------------------------------
        # LOAD d1 requires exactly one stall.
        #
        # If another distinct producer simultaneously feeds the
        # consumer, its effective forwarding age changes because of
        # the stall. That composite case is explicitly deferred.
        # ----------------------------------------------------------
        load_d1 = [
            dep
            for dep in dependencies
            if (
                dep.distance == 1
                and dep.producer.decoded.producer_type == "MEM_DATA"
            )
        ]

        if load_d1:
            load_producer_index = (
                load_d1[0].producer.instruction_index
            )

            distinct_producers = {
                dep.producer.instruction_index
                for dep in dependencies
            }

            if distinct_producers != {load_producer_index}:
                raise UnsupportedTimingScenario(
                    "composite load-use plus another dependency "
                    "is deferred from Timing Oracle v0"
                )

            stall_cycles = 1
        else:
            stall_cycles = 0

        forward_a = FORWARD_RF
        forward_b = FORWARD_RF

        source_a_distance = None
        source_b_distance = None

        source_a_producer_type = None
        source_b_producer_type = None

        for dep in dependencies:
            producer_type = dep.producer.decoded.producer_type

            if producer_type == "ALU_RESULT":
                if dep.distance == 1:
                    forward = FORWARD_EX_MEM
                elif dep.distance == 2:
                    forward = FORWARD_MEM_WB
                else:
                    raise AssertionError(
                        "v0 history must only expose d1/d2"
                    )

            elif producer_type == "MEM_DATA":
                if dep.distance == 1:
                    # One load-use stall moves the load result into
                    # MEM/WB before the consumer executes.
                    forward = FORWARD_MEM_WB
                elif dep.distance == 2:
                    forward = FORWARD_MEM_WB
                else:
                    raise AssertionError(
                        "v0 history must only expose d1/d2"
                    )

            else:
                raise AssertionError(
                    f"unexpected producer type {producer_type}"
                )

            if dep.role == "RS1":
                forward_a = forward
                source_a_distance = dep.distance
                source_a_producer_type = producer_type

            elif dep.role == "RS2":
                forward_b = forward
                source_b_distance = dep.distance
                source_b_producer_type = producer_type

            else:
                raise AssertionError(
                    f"unexpected source role {dep.role}"
                )

        distinct_producers = {
            dep.producer.instruction_index
            for dep in dependencies
        }

        if load_d1:
            reason = "LOAD_D1"
        elif len(distinct_producers) > 1:
            reason = "MULTI_FORWARD"
        else:
            dep = dependencies[0]

            if dep.producer.decoded.producer_type == "MEM_DATA":
                reason = "LOAD_D2"
            else:
                reason = f"ALU_D{dep.distance}"

        expectation = TimingExpectation(
            instruction_index=instruction_index,
            mnemonic=decoded.mnemonic,
            stall_cycles_before_accept=stall_cycles,
            forward_a=forward_a,
            forward_b=forward_b,
            source_a_distance=source_a_distance,
            source_b_distance=source_b_distance,
            source_a_producer_type=source_a_producer_type,
            source_b_producer_type=source_b_producer_type,
            reason=reason,
        )

        self._commit(decoded)
        return expectation

    def _commit(
        self,
        decoded: DecodedInstruction,
    ) -> None:
        self._history.append(
            _HistoryEntry(
                instruction_index=self._next_instruction_index,
                decoded=decoded,
            )
        )

        self._next_instruction_index += 1


def build_timing_expectations(
    instructions: Iterable[int],
) -> Tuple[TimingExpectation, ...]:
    oracle = TimingOracleV0()
    result = []

    for instruction in instructions:
        result.append(
            oracle.observe(instruction)
        )

    return tuple(result)
