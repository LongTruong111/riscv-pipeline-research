from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

from research.week5.impl.commit_scoreboard import StoreObservation
from research.week6.expected_retire import ExpectedRetire
from research.week7.retire_monitor import RetireEvent


MASK32 = 0xFFFFFFFF


class FunctionalScoreboardProtocolError(RuntimeError):
    """
    Verification-protocol failure.

    This is deliberately distinct from a DUT functional failure.
    """


@dataclass(frozen=True, slots=True)
class FunctionalCheck:
    name: str
    expected: int
    observed: int

    @property
    def passed(self) -> bool:
        return self.expected == self.observed


@dataclass(frozen=True, slots=True)
class FunctionalResult:
    instruction_id: int
    checks: Tuple[FunctionalCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> Tuple[FunctionalCheck, ...]:
        return tuple(
            check
            for check in self.checks
            if not check.passed
        )


class FunctionalScoreboard:
    """
    Week-8 architectural functional scoreboard.

    WHAT is checked here:
        - architectural register write enable
        - destination register
        - writeback data
        - store enable/address/data
        - x0 architectural invariant

    WHEN is intentionally not checked here.

    Store observations are buffered because the frozen DUT performs
    the store side effect in C before the same instruction logically
    retires from D.
    """

    def __init__(
        self,
        expected_retires: Iterable[ExpectedRetire],
    ) -> None:
        expected = tuple(expected_retires)

        self._expected_by_id: Dict[int, ExpectedRetire] = {}

        for expected_id, item in enumerate(
            expected,
            start=1,
        ):
            if item.instruction_id != expected_id:
                raise ValueError(
                    "expected retire stream must be contiguous: "
                    f"expected instruction_id={expected_id}, "
                    f"got {item.instruction_id}"
                )

            self._expected_by_id[item.instruction_id] = item

        self._store_by_id: Dict[int, StoreObservation] = {}
        self._results_by_id: Dict[int, FunctionalResult] = {}

    @property
    def expected_count(self) -> int:
        return len(self._expected_by_id)

    @property
    def checked_count(self) -> int:
        return len(self._results_by_id)

    @property
    def passed_count(self) -> int:
        return sum(
            result.passed
            for result in self._results_by_id.values()
        )

    @property
    def failed_count(self) -> int:
        return self.checked_count - self.passed_count

    @property
    def failed_instruction_ids(self) -> Tuple[int, ...]:
        return tuple(
            instruction_id
            for instruction_id, result
            in sorted(self._results_by_id.items())
            if not result.passed
        )

    @property
    def complete(self) -> bool:
        return self.checked_count == self.expected_count

    def _require_expected(
        self,
        instruction_id: int,
    ) -> ExpectedRetire:
        try:
            return self._expected_by_id[instruction_id]
        except KeyError as exc:
            raise FunctionalScoreboardProtocolError(
                "observation has no matching ExpectedRetire: "
                f"instruction_id={instruction_id}"
            ) from exc

    def observe_store_stage(
        self,
        observation: StoreObservation,
    ) -> None:
        """
        Record one valid C-stage memory-side-effect observation.

        Call this once for every verification-valid C-stage tag,
        including non-store instructions with write_enable=False.
        """

        self._require_expected(
            observation.instruction_index
        )

        if (
            observation.instruction_index
            in self._store_by_id
        ):
            raise FunctionalScoreboardProtocolError(
                "duplicate store-stage observation for "
                f"instruction_id="
                f"{observation.instruction_index}"
            )

        self._store_by_id[
            observation.instruction_index
        ] = observation

    def observe_retire(
        self,
        retire: RetireEvent,
        *,
        observed_x0: int,
    ) -> FunctionalResult:
        """
        Finalize the functional verdict for one logical retirement.

        Timing/cycle is deliberately ignored here.
        """

        if not 0 <= observed_x0 <= MASK32:
            raise ValueError(
                "observed_x0 must fit 32 bits"
            )

        instruction_id = retire.instruction_id

        expected = self._require_expected(
            instruction_id
        )

        if instruction_id in self._results_by_id:
            raise FunctionalScoreboardProtocolError(
                "duplicate functional retirement for "
                f"instruction_id={instruction_id}"
            )

        try:
            store_observation = self._store_by_id.pop(
                instruction_id
            )
        except KeyError as exc:
            raise FunctionalScoreboardProtocolError(
                "missing C-stage store observation before "
                f"retirement of instruction_id="
                f"{instruction_id}"
            ) from exc

        checks = []

        # ----------------------------------------------------------
        # Register writeback
        # ----------------------------------------------------------
        if expected.regwrite:
            if expected.rd is None or expected.wdata is None:
                raise FunctionalScoreboardProtocolError(
                    "ExpectedRetire is internally inconsistent: "
                    "regwrite=True requires rd and wdata"
                )

            checks.append(
                FunctionalCheck(
                    name="write_enable",
                    expected=1,
                    observed=int(retire.regwrite),
                )
            )

            # rd/wdata are meaningful only when the DUT actually
            # asserts its physical write enable.
            if retire.regwrite:
                checks.append(
                    FunctionalCheck(
                        name="write_rd",
                        expected=expected.rd,
                        observed=retire.rd,
                    )
                )

                checks.append(
                    FunctionalCheck(
                        name="write_data",
                        expected=(
                            expected.wdata & MASK32
                        ),
                        observed=(
                            retire.wdata & MASK32
                        ),
                    )
                )

        else:
            # Preserve the frozen Week-5 x0 rule:
            # a physical write-enable to rd=x0 is not itself an
            # architectural GPR write. x0 state is checked below.
            unexpected_architectural_write = (
                retire.regwrite
                and retire.rd != 0
            )

            checks.append(
                FunctionalCheck(
                    name="unexpected_architectural_write",
                    expected=0,
                    observed=int(
                        unexpected_architectural_write
                    ),
                )
            )

        # ----------------------------------------------------------
        # Store side effect
        # ----------------------------------------------------------
        expected_is_store = (
            expected.store_address is not None
        )

        if not expected_is_store:
            checks.append(
                FunctionalCheck(
                    name="unexpected_store",
                    expected=0,
                    observed=int(
                        store_observation.write_enable
                    ),
                )
            )

        else:
            if (
                expected.store_data is None
                or expected.store_width_bytes is None
            ):
                raise FunctionalScoreboardProtocolError(
                    "ExpectedRetire is internally inconsistent: "
                    "store address requires data and width"
                )

            checks.append(
                FunctionalCheck(
                    name="store_enable",
                    expected=1,
                    observed=int(
                        store_observation.write_enable
                    ),
                )
            )

            if store_observation.write_enable:
                # Frozen DUT exposes only a 9-bit data-memory address.
                # Never silently truncate a 32-bit Golden address.
                if expected.store_address > 0x1FF:
                    checks.append(
                        FunctionalCheck(
                            name="store_address_in_dut_range",
                            expected=1,
                            observed=0,
                        )
                    )
                else:
                    checks.append(
                        FunctionalCheck(
                            name="store_address",
                            expected=expected.store_address,
                            observed=store_observation.address,
                        )
                    )

                checks.append(
                    FunctionalCheck(
                        name="store_data",
                        expected=(
                            expected.store_data & MASK32
                        ),
                        observed=(
                            store_observation.data & MASK32
                        ),
                    )
                )

        # ----------------------------------------------------------
        # Architectural x0 state
        # ----------------------------------------------------------
        checks.append(
            FunctionalCheck(
                name="architectural_x0",
                expected=0,
                observed=observed_x0 & MASK32,
            )
        )

        result = FunctionalResult(
            instruction_id=instruction_id,
            checks=tuple(checks),
        )

        self._results_by_id[
            instruction_id
        ] = result

        return result
