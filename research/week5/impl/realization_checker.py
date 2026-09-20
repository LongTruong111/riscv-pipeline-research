from dataclasses import dataclass
from typing import List, Mapping, Tuple

from .execution_event import ExecutionEvent
from .l1_coverage import L1_BIN_IDS, L1Hit


@dataclass(frozen=True, slots=True)
class ControlCheck:
    """
    One control/timing realization predicate.

    This is deliberately narrower than architectural correctness.
    """

    name: str
    expected: int
    observed: int

    @property
    def passed(self) -> bool:
        return self.expected == self.observed


@dataclass(frozen=True, slots=True)
class ControlRealizationResult:
    """
    Control/timing realization result for one L1 Intent hit.

    A PASS here is not yet a ValidatedHit because architectural value/state
    checking is handled separately.
    """

    bin_id: str
    consumer_instruction_index: int
    checks: Tuple[ControlCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> Tuple[ControlCheck, ...]:
        return tuple(
            check for check in self.checks
            if not check.passed
        )


class L1ControlRealizationChecker:
    """
    Frozen H01-H20 control/timing realization checker.

    Checked here:
      - load-use / no-stall behavior;
      - EX/MEM vs MEM/WB vs RF forwarding selection;
      - newest-producer priority;
      - x0 forwarding exclusion.

    NOT checked here:
      - actual forwarded value;
      - final architectural register value;
      - memory side effect;
      - redirect target correctness;
      - x0 architectural state retention.

    Therefore this checker must not by itself promote a bin to
    Validated Coverage.
    """

    _STALL_EXPECTED = {
        bin_id: 0
        for bin_id in L1_BIN_IDS
    }

    _STALL_EXPECTED["H06"] = 1
    _STALL_EXPECTED["H07"] = 1

    # Fixed forwarding requirements:
    #
    # 00 = Register File
    # 01 = MEM/WB
    # 10 = EX/MEM
    #
    # H05/H10/H15/H17/H18 require role-dependent handling below.
    _FIXED_FORWARD = {
        "H01": (("RS1", 0b10),),
        "H02": (("RS2", 0b10),),
        "H03": (("RS1", 0b01),),
        "H04": (("RS2", 0b01),),

        "H06": (("RS1", 0b01),),
        "H07": (("RS2", 0b01),),
        "H08": (("RS1", 0b01),),
        "H09": (("RS2", 0b01),),

        # d1 special producers still select EX/MEM.
        # Their DATA value may nevertheless be wrong; that is checked later.
        "H11": (("RS1", 0b10),),
        "H12": (("RS1", 0b01),),
        "H13": (("RS1", 0b10),),
        "H14": (("RS1", 0b01),),

        "H16": (("RS2", 0b10),),
    }

    @staticmethod
    def _forward_value(
        event: ExecutionEvent,
        role: str,
    ) -> int:
        if role == "RS1":
            return event.forward_a

        if role == "RS2":
            return event.forward_b

        raise ValueError(
            f"Unsupported forwarding source role: {role}"
        )

    @staticmethod
    def _add_forward_check(
        checks: List[ControlCheck],
        event: ExecutionEvent,
        role: str,
        expected: int,
    ) -> None:
        observed = (
            event.forward_a
            if role == "RS1"
            else event.forward_b
            if role == "RS2"
            else None
        )

        if observed is None:
            raise ValueError(
                f"Unsupported forwarding role: {role}"
            )

        checks.append(
            ControlCheck(
                name=f"forward_{role.lower()}",
                expected=expected,
                observed=observed,
            )
        )

    @staticmethod
    def _lookup_producer(
        events_by_index: Mapping[int, ExecutionEvent],
        instruction_index: int,
    ) -> ExecutionEvent:
        try:
            return events_by_index[instruction_index]
        except KeyError as exc:
            raise ValueError(
                "Missing producer ExecutionEvent for "
                f"instruction_index={instruction_index}"
            ) from exc

    def check(
        self,
        hit: L1Hit,
        consumer: ExecutionEvent,
        events_by_index: Mapping[int, ExecutionEvent],
    ) -> ControlRealizationResult:
        if hit.bin_id not in L1_BIN_IDS:
            raise ValueError(
                f"Unknown L1 bin: {hit.bin_id}"
            )

        if (
            hit.consumer_instruction_index
            != consumer.instruction_index
        ):
            raise ValueError(
                "L1Hit consumer index does not match "
                "ExecutionEvent index"
            )

        checks: List[ControlCheck] = []

        # ----------------------------------------------------------
        # Stall/interlock realization.
        #
        # Every frozen H01-H20 row specifies stall=0 except:
        #   H06 = exactly one stall
        #   H07 = exactly one stall
        # ----------------------------------------------------------
        expected_stall = self._STALL_EXPECTED[hit.bin_id]

        checks.append(
            ControlCheck(
                name="stall_cycles_before_accept",
                expected=expected_stall,
                observed=consumer.stall_cycles_before_accept,
            )
        )

        # ----------------------------------------------------------
        # Fixed forwarding rows.
        # ----------------------------------------------------------
        for role, expected in self._FIXED_FORWARD.get(
            hit.bin_id,
            (),
        ):
            self._add_forward_check(
                checks,
                consumer,
                role,
                expected,
            )

        # ----------------------------------------------------------
        # H05 — d3 RF boundary.
        # All dependency source roles must use the Register File.
        # ----------------------------------------------------------
        if hit.bin_id == "H05":
            for role in hit.matched_sources:
                self._add_forward_check(
                    checks,
                    consumer,
                    role,
                    0b00,
                )

        # ----------------------------------------------------------
        # H10 — simultaneous d1+d2 forwarding.
        #
        # Classifier allows either operand orientation:
        #
        # newer d1 source -> EX/MEM = 10
        # older d2 source -> MEM/WB = 01
        # ----------------------------------------------------------
        elif hit.bin_id == "H10":
            if len(hit.producer_instruction_indices) != 2:
                raise ValueError(
                    "H10 requires exactly two producers"
                )

            older_index, newer_index = (
                hit.producer_instruction_indices
            )

            older = self._lookup_producer(
                events_by_index,
                older_index,
            )

            newer = self._lookup_producer(
                events_by_index,
                newer_index,
            )

            matched_roles = 0

            if (
                consumer.uses_rs1
                and consumer.rs1 == newer.rd
            ):
                self._add_forward_check(
                    checks,
                    consumer,
                    "RS1",
                    0b10,
                )
                matched_roles += 1

            elif (
                consumer.uses_rs1
                and consumer.rs1 == older.rd
            ):
                self._add_forward_check(
                    checks,
                    consumer,
                    "RS1",
                    0b01,
                )
                matched_roles += 1

            if (
                consumer.uses_rs2
                and consumer.rs2 == newer.rd
            ):
                self._add_forward_check(
                    checks,
                    consumer,
                    "RS2",
                    0b10,
                )
                matched_roles += 1

            elif (
                consumer.uses_rs2
                and consumer.rs2 == older.rd
            ):
                self._add_forward_check(
                    checks,
                    consumer,
                    "RS2",
                    0b01,
                )
                matched_roles += 1

            if matched_roles != 2:
                raise ValueError(
                    "H10 consumer does not expose both "
                    "d1 and d2 producer operands"
                )

        # ----------------------------------------------------------
        # H15 — link producer across redirect.
        #
        # Redirect bubbles create enough separation for ordinary
        # Register-File visibility in the frozen truth table.
        #
        # Redirect occurrence itself is NOT checked here yet because it
        # is not currently carried by ExecutionEvent.
        # ----------------------------------------------------------
        elif hit.bin_id == "H15":
            for role in hit.matched_sources:
                self._add_forward_check(
                    checks,
                    consumer,
                    role,
                    0b00,
                )

        # ----------------------------------------------------------
        # H17 — newest producer must win.
        #
        # The newer writer is d1, therefore the used source must select
        # EX/MEM rather than the older MEM/WB writer.
        # ----------------------------------------------------------
        elif hit.bin_id == "H17":
            for role in hit.matched_sources:
                self._add_forward_check(
                    checks,
                    consumer,
                    role,
                    0b10,
                )

        # ----------------------------------------------------------
        # H18 — rd=x0 must not become a forwarding dependency.
        # ----------------------------------------------------------
        elif hit.bin_id == "H18":
            for role in hit.matched_sources:
                self._add_forward_check(
                    checks,
                    consumer,
                    role,
                    0b00,
                )

        # H19/H20 intentionally add no forwarding predicate here.
        #
        # Their primary control requirement is absence of a false load-use
        # stall. H19 may also incidentally hit H18, which independently
        # checks x0 forwarding exclusion.

        return ControlRealizationResult(
            bin_id=hit.bin_id,
            consumer_instruction_index=(
                consumer.instruction_index
            ),
            checks=tuple(checks),
        )
