"""Bounded streaming equivalent of Week-8 FunctionalScoreboard."""

from typing import Dict

from research.week5.impl.commit_scoreboard import (
    StoreObservation,
)
from research.week6.expected_retire import (
    ExpectedRetire,
)
from research.week7.retire_monitor import (
    RetireEvent,
)
from research.week8.functional_scoreboard import (
    FunctionalCheck,
    FunctionalResult,
    FunctionalScoreboardProtocolError,
)


MASK32 = 0xFFFFFFFF


class StreamingFunctionalScoreboard:
    """Check WHAT without retaining campaign-length history.

    Expected retirement state is registered when an instruction is
    accepted and discarded immediately after that instruction retires.

    Store observations are retained only from C until D.

    Retained memory therefore scales with pipeline in-flight state,
    not total campaign length.
    """

    def __init__(self) -> None:
        self._expected_by_id: Dict[
            int,
            ExpectedRetire,
        ] = {}

        self._store_by_id: Dict[
            int,
            StoreObservation,
        ] = {}

        self._registered_count = 0
        self._checked_count = 0
        self._passed_count = 0
        self._failed_count = 0

        self._last_retired_id = 0

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
    def pending_expected_count(self) -> int:
        return len(self._expected_by_id)

    @property
    def pending_store_count(self) -> int:
        return len(self._store_by_id)

    @property
    def complete(self) -> bool:
        return (
            self._checked_count
            == self._registered_count
            and not self._expected_by_id
            and not self._store_by_id
        )

    @property
    def overall_pass(self) -> bool:
        return (
            self.complete
            and self._failed_count == 0
        )

    def register_expected(
        self,
        expected: ExpectedRetire,
    ) -> None:
        if not isinstance(
            expected,
            ExpectedRetire,
        ):
            raise TypeError(
                "expected must be ExpectedRetire"
            )

        expected_id = (
            self._registered_count + 1
        )

        if (
            expected.instruction_id
            != expected_id
        ):
            raise ValueError(
                "expected retire stream must be "
                "contiguous: "
                f"expected instruction_id="
                f"{expected_id}, got "
                f"{expected.instruction_id}"
            )

        if (
            expected.instruction_id
            in self._expected_by_id
        ):
            raise ValueError(
                "duplicate ExpectedRetire"
            )

        self._expected_by_id[
            expected.instruction_id
        ] = expected

        self._registered_count += 1

    def _require_expected(
        self,
        instruction_id: int,
    ) -> ExpectedRetire:
        try:
            return self._expected_by_id[
                instruction_id
            ]
        except KeyError as exc:
            raise FunctionalScoreboardProtocolError(
                "observation has no matching "
                "ExpectedRetire: "
                f"instruction_id={instruction_id}"
            ) from exc

    def observe_store_stage(
        self,
        observation: StoreObservation,
    ) -> None:
        if not isinstance(
            observation,
            StoreObservation,
        ):
            raise TypeError(
                "observation must be StoreObservation"
            )

        self._require_expected(
            observation.instruction_index
        )

        if (
            observation.instruction_index
            in self._store_by_id
        ):
            raise FunctionalScoreboardProtocolError(
                "duplicate store-stage observation "
                "for instruction_id="
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
        if not isinstance(retire, RetireEvent):
            raise TypeError(
                "retire must be RetireEvent"
            )

        if not 0 <= observed_x0 <= MASK32:
            raise ValueError(
                "observed_x0 must fit 32 bits"
            )

        instruction_id = retire.instruction_id

        expected_next_id = (
            self._last_retired_id + 1
        )

        if instruction_id != expected_next_id:
            raise FunctionalScoreboardProtocolError(
                "functional retire order violation: "
                f"expected instruction_id="
                f"{expected_next_id}, got "
                f"{instruction_id}"
            )

        expected = self._require_expected(
            instruction_id
        )

        try:
            store_observation = (
                self._store_by_id[
                    instruction_id
                ]
            )
        except KeyError as exc:
            raise FunctionalScoreboardProtocolError(
                "missing C-stage store observation "
                "before retirement of "
                f"instruction_id={instruction_id}"
            ) from exc

        checks = []

        # ------------------------------------------------------
        # Register writeback
        # ------------------------------------------------------
        if expected.regwrite:
            if (
                expected.rd is None
                or expected.wdata is None
            ):
                raise FunctionalScoreboardProtocolError(
                    "ExpectedRetire is internally "
                    "inconsistent: regwrite=True "
                    "requires rd and wdata"
                )

            checks.append(
                FunctionalCheck(
                    name="write_enable",
                    expected=1,
                    observed=int(
                        retire.regwrite
                    ),
                )
            )

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
                            expected.wdata
                            & MASK32
                        ),
                        observed=(
                            retire.wdata
                            & MASK32
                        ),
                    )
                )

        else:
            unexpected_architectural_write = (
                retire.regwrite
                and retire.rd != 0
            )

            checks.append(
                FunctionalCheck(
                    name=(
                        "unexpected_architectural_write"
                    ),
                    expected=0,
                    observed=int(
                        unexpected_architectural_write
                    ),
                )
            )

        # ------------------------------------------------------
        # Store side effect
        # ------------------------------------------------------
        expected_is_store = (
            expected.store_address is not None
        )

        if not expected_is_store:
            checks.append(
                FunctionalCheck(
                    name="unexpected_store",
                    expected=0,
                    observed=int(
                        store_observation
                        .write_enable
                    ),
                )
            )

        else:
            if (
                expected.store_data is None
                or expected.store_width_bytes
                is None
            ):
                raise FunctionalScoreboardProtocolError(
                    "ExpectedRetire is internally "
                    "inconsistent: store address "
                    "requires data and width"
                )

            checks.append(
                FunctionalCheck(
                    name="store_enable",
                    expected=1,
                    observed=int(
                        store_observation
                        .write_enable
                    ),
                )
            )

            if store_observation.write_enable:
                if (
                    expected.store_address
                    > 0x1FF
                ):
                    checks.append(
                        FunctionalCheck(
                            name=(
                                "store_address_"
                                "in_dut_range"
                            ),
                            expected=1,
                            observed=0,
                        )
                    )
                else:
                    checks.append(
                        FunctionalCheck(
                            name="store_address",
                            expected=(
                                expected
                                .store_address
                            ),
                            observed=(
                                store_observation
                                .address
                            ),
                        )
                    )

                checks.append(
                    FunctionalCheck(
                        name="store_data",
                        expected=(
                            expected.store_data
                            & MASK32
                        ),
                        observed=(
                            store_observation.data
                            & MASK32
                        ),
                    )
                )

        # ------------------------------------------------------
        # Architectural x0
        # ------------------------------------------------------
        checks.append(
            FunctionalCheck(
                name="architectural_x0",
                expected=0,
                observed=(
                    observed_x0
                    & MASK32
                ),
            )
        )

        result = FunctionalResult(
            instruction_id=instruction_id,
            checks=tuple(checks),
        )

        del self._store_by_id[
            instruction_id
        ]

        del self._expected_by_id[
            instruction_id
        ]

        self._last_retired_id = (
            instruction_id
        )

        self._checked_count += 1

        if result.passed:
            self._passed_count += 1
        else:
            self._failed_count += 1

        return result
