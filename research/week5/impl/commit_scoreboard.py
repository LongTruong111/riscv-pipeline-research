from dataclasses import dataclass
from typing import Optional, Tuple

from .architectural_model import ArchitecturalStep


MASK32 = 0xFFFFFFFF


@dataclass(frozen=True, slots=True)
class ArchitecturalCheck:
    name: str
    expected: int
    observed: int

    @property
    def passed(self) -> bool:
        return self.expected == self.observed


@dataclass(frozen=True, slots=True)
class ArchitecturalCheckResult:
    kind: str
    instruction_index: int
    checks: Tuple[ArchitecturalCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> Tuple[ArchitecturalCheck, ...]:
        return tuple(
            check
            for check in self.checks
            if not check.passed
        )


@dataclass(frozen=True, slots=True)
class WritebackObservation:
    instruction_index: int
    write_enable: bool
    rd: int
    data: int

    # Optional stage identity cross-check.
    instruction: Optional[int] = None

    def __post_init__(self) -> None:
        if self.instruction_index <= 0:
            raise ValueError(
                "instruction_index must be positive"
            )

        if not 0 <= self.rd <= 31:
            raise ValueError(
                f"rd must be in [0, 31], got {self.rd}"
            )

        if not 0 <= self.data <= MASK32:
            raise ValueError(
                "writeback data must fit 32 bits"
            )

        if (
            self.instruction is not None
            and not 0 <= self.instruction <= MASK32
        ):
            raise ValueError(
                "instruction must fit 32 bits"
            )


@dataclass(frozen=True, slots=True)
class StoreObservation:
    instruction_index: int
    write_enable: bool
    address: int
    data: int

    instruction: Optional[int] = None

    def __post_init__(self) -> None:
        if self.instruction_index <= 0:
            raise ValueError(
                "instruction_index must be positive"
            )

        if not 0 <= self.address <= 0x1FF:
            raise ValueError(
                "observed DUT memory address must fit 9 bits"
            )

        if not 0 <= self.data <= MASK32:
            raise ValueError(
                "store data must fit 32 bits"
            )

        if (
            self.instruction is not None
            and not 0 <= self.instruction <= MASK32
        ):
            raise ValueError(
                "instruction must fit 32 bits"
            )


class CommitScoreboard:
    """
    Compare independent architectural expectations against live DUT
    observations.

    This checker does NOT use DUT datapath values as its oracle.

    Important x0 rule:
      A physical write-enable targeting rd=x0 is not treated here as an
      architectural register commit. Architectural x0 state is checked
      independently through check_x0().

    This avoids assuming a particular compliant microarchitecture while
    still allowing the frozen DUT's x0 state defect to be detected.
    """

    @staticmethod
    def _check_instruction_index(
        step: ArchitecturalStep,
        instruction_index: int,
    ) -> None:
        if step.instruction_index != instruction_index:
            raise ValueError(
                "Observation instruction index does not match "
                f"ArchitecturalStep: expected "
                f"{step.instruction_index}, "
                f"got {instruction_index}"
            )

    def check_pc(
        self,
        step: ArchitecturalStep,
    ) -> ArchitecturalCheckResult:
        return ArchitecturalCheckResult(
            kind="pc",
            instruction_index=step.instruction_index,
            checks=(
                ArchitecturalCheck(
                    name="executed_pc",
                    expected=step.expected_pc & MASK32,
                    observed=step.pc & MASK32,
                ),
            ),
        )

    def check_writeback(
        self,
        step: ArchitecturalStep,
        observation: WritebackObservation,
    ) -> ArchitecturalCheckResult:
        self._check_instruction_index(
            step,
            observation.instruction_index,
        )

        checks = []

        if observation.instruction is not None:
            checks.append(
                ArchitecturalCheck(
                    name="wb_instruction",
                    expected=step.instruction & MASK32,
                    observed=observation.instruction & MASK32,
                )
            )

        expected_write = step.register_write

        if expected_write is None:
            # A physical write to x0 has no architectural register-write
            # effect. x0 state is validated independently.
            unexpected_architectural_write = (
                observation.write_enable
                and observation.rd != 0
            )

            checks.append(
                ArchitecturalCheck(
                    name="unexpected_architectural_write",
                    expected=0,
                    observed=int(
                        unexpected_architectural_write
                    ),
                )
            )

            return ArchitecturalCheckResult(
                kind="writeback",
                instruction_index=step.instruction_index,
                checks=tuple(checks),
            )

        checks.append(
            ArchitecturalCheck(
                name="write_enable",
                expected=1,
                observed=int(observation.write_enable),
            )
        )

        if observation.write_enable:
            checks.append(
                ArchitecturalCheck(
                    name="write_rd",
                    expected=expected_write.rd,
                    observed=observation.rd,
                )
            )

            checks.append(
                ArchitecturalCheck(
                    name="write_data",
                    expected=expected_write.value & MASK32,
                    observed=observation.data & MASK32,
                )
            )

        return ArchitecturalCheckResult(
            kind="writeback",
            instruction_index=step.instruction_index,
            checks=tuple(checks),
        )

    def check_store(
        self,
        step: ArchitecturalStep,
        observation: StoreObservation,
    ) -> ArchitecturalCheckResult:
        self._check_instruction_index(
            step,
            observation.instruction_index,
        )

        checks = []

        if observation.instruction is not None:
            checks.append(
                ArchitecturalCheck(
                    name="store_instruction",
                    expected=step.instruction & MASK32,
                    observed=observation.instruction & MASK32,
                )
            )

        expected_store = step.store

        if expected_store is None:
            checks.append(
                ArchitecturalCheck(
                    name="unexpected_store",
                    expected=0,
                    observed=int(observation.write_enable),
                )
            )

            return ArchitecturalCheckResult(
                kind="store",
                instruction_index=step.instruction_index,
                checks=tuple(checks),
            )

        checks.append(
            ArchitecturalCheck(
                name="store_enable",
                expected=1,
                observed=int(observation.write_enable),
            )
        )

        if observation.write_enable:
            if expected_store.address > 0x1FF:
                # Frozen DUT exposes only a 9-bit data-memory address.
                # Do not silently truncate an architectural address.
                checks.append(
                    ArchitecturalCheck(
                        name="store_address_in_dut_range",
                        expected=1,
                        observed=0,
                    )
                )
            else:
                checks.append(
                    ArchitecturalCheck(
                        name="store_address",
                        expected=expected_store.address,
                        observed=observation.address,
                    )
                )

            checks.append(
                ArchitecturalCheck(
                    name="store_data",
                    expected=expected_store.data & MASK32,
                    observed=observation.data & MASK32,
                )
            )

        return ArchitecturalCheckResult(
            kind="store",
            instruction_index=step.instruction_index,
            checks=tuple(checks),
        )

    def check_x0(
        self,
        *,
        instruction_index: int,
        observed_value: int,
    ) -> ArchitecturalCheckResult:
        if instruction_index <= 0:
            raise ValueError(
                "instruction_index must be positive"
            )

        if not 0 <= observed_value <= MASK32:
            raise ValueError(
                "observed x0 value must fit 32 bits"
            )

        return ArchitecturalCheckResult(
            kind="x0",
            instruction_index=instruction_index,
            checks=(
                ArchitecturalCheck(
                    name="architectural_x0",
                    expected=0,
                    observed=observed_value,
                ),
            ),
        )
