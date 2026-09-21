from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from random import Random
from typing import Iterable

from research.week5.impl.rv32_encode import (
    add,
    addi,
    auipc,
    jal,
    jalr,
    lui,
    lw,
    sw,
)

from research.week10.adaptive.filler_policy import (
    FillerConstructionError,
    FillerKind,
    build_filler_instruction,
)
from research.week10.adaptive.register_policy import (
    TargetSelection,
)
from research.week10.adaptive.reward_engine import (
    attribution_targets_for,
)
from research.week10.adaptive.template_library import (
    ArmID,
)


SPECIAL_IMM20 = 0x12345

ALU_PRODUCER_VALUE = 7
LOAD_OFFSET = 0
STORE_OFFSET = 0
STORE_DATA_VALUE = 42

JUMP_LOCAL_TARGET_OFFSET = 12


class TemplateConstructionError(RuntimeError):
    """
    Raised when a frozen adaptive template cannot be constructed
    legally for the supplied context.
    """


class TemplateVariant(str, Enum):
    RS1 = "rs1"
    RS2 = "rs2"

    DUAL = "dual"

    LUI = "lui"
    AUIPC = "auipc"

    JAL = "jal"
    JALR = "jalr"

    STORE_DATA = "store_data"
    PRIORITY = "priority"


@dataclass(frozen=True)
class RealizedTemplate:
    """
    One concrete Adaptive-CGS template.

    words:
        Program-image words, including control-flow fall-through words
        that may be flushed.

    expected_executed_word_indices:
        Word indices expected to appear in executed-program order.

    structural_word_indices:
        Structural instructions required to realize the template.
        These may be executed d2 fillers or flushed control-flow words.

    d1_producer_word_index / d2_producer_word_index:
        Active producer locations for the intended positive L2 bins.

    shadowed_writer_word_indices:
        Writers intentionally superseded by latest-writer semantics.
    """

    arm_id: ArmID
    variant: TemplateVariant
    target: TargetSelection
    start_pc: int

    words: tuple[int, ...]

    expected_executed_word_indices: tuple[int, ...]
    structural_word_indices: tuple[int, ...]

    consumer_word_index: int

    d1_producer_word_index: int | None = None
    d2_producer_word_index: int | None = None

    shadowed_writer_word_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.start_pc < 0:
            raise ValueError("start_pc must be non-negative")

        if self.start_pc % 4 != 0:
            raise ValueError(
                "start_pc must be 4-byte aligned"
            )

        if not self.words:
            raise ValueError(
                "realized template must contain instructions"
            )

        for word in self.words:
            if not 0 <= word <= 0xFFFFFFFF:
                raise ValueError(
                    f"instruction word does not fit 32 bits: {word}"
                )

        self._validate_indices(
            "expected_executed_word_indices",
            self.expected_executed_word_indices,
        )

        self._validate_indices(
            "structural_word_indices",
            self.structural_word_indices,
        )

        self._validate_indices(
            "shadowed_writer_word_indices",
            self.shadowed_writer_word_indices,
        )

        if not 0 <= self.consumer_word_index < len(self.words):
            raise ValueError(
                "consumer_word_index is outside template"
            )

        if (
            self.consumer_word_index
            not in self.expected_executed_word_indices
        ):
            raise ValueError(
                "consumer must be architecturally executed"
            )

        for producer_index in (
            self.d1_producer_word_index,
            self.d2_producer_word_index,
        ):
            if producer_index is None:
                continue

            if not 0 <= producer_index < len(self.words):
                raise ValueError(
                    "producer word index is outside template"
                )

            if (
                producer_index
                not in self.expected_executed_word_indices
            ):
                raise ValueError(
                    "active producer must be architecturally executed"
                )

    def _validate_indices(
        self,
        name: str,
        indices: tuple[int, ...],
    ) -> None:
        if len(indices) != len(set(indices)):
            raise ValueError(
                f"{name} contains duplicate indices"
            )

        for index in indices:
            if not 0 <= index < len(self.words):
                raise ValueError(
                    f"{name} contains out-of-range index {index}"
                )

    @property
    def image_word_count(self) -> int:
        return len(self.words)

    @property
    def expected_executed_instruction_count(self) -> int:
        return len(self.expected_executed_word_indices)

    def pc_for_word(self, word_index: int) -> int:
        if not 0 <= word_index < len(self.words):
            raise IndexError(
                f"word index outside template: {word_index}"
            )

        return self.start_pc + 4 * word_index


def _positive_auxiliary_register(
    protected_registers: Iterable[int],
) -> int:
    protected = frozenset(protected_registers)

    for register in range(1, 32):
        if register not in protected:
            return register

    raise TemplateConstructionError(
        "no legal positive auxiliary register remains"
    )


def _two_auxiliary_registers(
    protected_registers: Iterable[int],
) -> tuple[int, int]:
    protected = set(protected_registers)

    first = _positive_auxiliary_register(protected)
    protected.add(first)

    second = _positive_auxiliary_register(protected)

    return first, second


def _rs1_consumer(
    target_register: int,
    destination_register: int,
) -> int:
    return addi(
        destination_register,
        target_register,
        1,
    )


def _rs2_consumer(
    target_register: int,
    destination_register: int,
) -> int:
    return add(
        destination_register,
        0,
        target_register,
    )


def _signed_12_fits(value: int) -> bool:
    return -(1 << 11) <= value <= (1 << 11) - 1


class TemplateRealizer:
    """
    Deterministic concrete realization of frozen Adaptive-CGS arms.

    All stochastic within-arm choices use only the caller-owned RNG.
    No rejection sampling is used.
    """

    def __init__(self, rng: Random) -> None:
        if not isinstance(rng, Random):
            raise TypeError(
                "rng must be an instance of random.Random"
            )

        self._rng = rng

    def realize(
        self,
        arm_id: ArmID,
        target: TargetSelection,
        *,
        start_pc: int = 0,
    ) -> RealizedTemplate:
        """
        Realize one complete adaptive template.

        start_pc matters only for control-flow realization. It must be
        4-byte aligned.
        """
        if start_pc < 0:
            raise ValueError(
                "start_pc must be non-negative"
            )

        if start_pc % 4 != 0:
            raise ValueError(
                "start_pc must be 4-byte aligned"
            )

        # Reuse the frozen reward-attribution shape validation.
        attribution_targets_for(
            arm_id,
            target,
        )

        if arm_id is ArmID.A0:
            return self._realize_alu_d1(
                target,
                start_pc,
            )

        if arm_id is ArmID.A1:
            return self._realize_alu_d2(
                target,
                start_pc,
            )

        if arm_id is ArmID.A2:
            return self._realize_load_d1(
                target,
                start_pc,
            )

        if arm_id is ArmID.A3:
            return self._realize_load_d2(
                target,
                start_pc,
            )

        if arm_id is ArmID.A4:
            return self._realize_dual(
                target,
                start_pc,
            )

        if arm_id is ArmID.A5:
            return self._realize_special_d1(
                target,
                start_pc,
            )

        if arm_id is ArmID.A6:
            return self._realize_special_d2(
                target,
                start_pc,
            )

        if arm_id is ArmID.A7:
            return self._realize_link_d1(
                target,
                start_pc,
            )

        if arm_id is ArmID.A8:
            return self._realize_store_data_d1(
                target,
                start_pc,
            )

        if arm_id is ArmID.A9:
            return self._realize_priority_d1(
                target,
                start_pc,
            )

        raise TemplateConstructionError(
            f"unsupported adaptive arm: {arm_id!r}"
        )

    def _choose_operand_variant(
        self,
    ) -> TemplateVariant:
        return self._rng.choice(
            (
                TemplateVariant.RS1,
                TemplateVariant.RS2,
            )
        )

    def _consumer_for_variant(
        self,
        *,
        variant: TemplateVariant,
        target_register: int,
        destination_register: int,
    ) -> int:
        if variant is TemplateVariant.RS1:
            return _rs1_consumer(
                target_register,
                destination_register,
            )

        if variant is TemplateVariant.RS2:
            return _rs2_consumer(
                target_register,
                destination_register,
            )

        raise TemplateConstructionError(
            f"invalid operand variant: {variant}"
        )

    def _structural_filler(
        self,
        *,
        protected_registers: Iterable[int],
    ) -> int:
        try:
            filler = build_filler_instruction(
                kind=FillerKind.STRUCTURAL_D2,
                protected_registers=protected_registers,
            )
        except FillerConstructionError as exc:
            raise TemplateConstructionError(
                "unable to construct structural d2 filler"
            ) from exc

        return filler.word

    def _realize_alu_d1(
        self,
        target: TargetSelection,
        start_pc: int,
    ) -> RealizedTemplate:
        register = target.d1
        assert register is not None

        destination = _positive_auxiliary_register(
            {register}
        )

        variant = self._choose_operand_variant()

        words = (
            addi(
                register,
                0,
                ALU_PRODUCER_VALUE,
            ),
            self._consumer_for_variant(
                variant=variant,
                target_register=register,
                destination_register=destination,
            ),
        )

        return RealizedTemplate(
            arm_id=ArmID.A0,
            variant=variant,
            target=target,
            start_pc=start_pc,
            words=words,
            expected_executed_word_indices=(0, 1),
            structural_word_indices=(),
            consumer_word_index=1,
            d1_producer_word_index=0,
        )

    def _realize_alu_d2(
        self,
        target: TargetSelection,
        start_pc: int,
    ) -> RealizedTemplate:
        register = target.d2
        assert register is not None

        destination = _positive_auxiliary_register(
            {register}
        )

        variant = self._choose_operand_variant()

        filler_word = self._structural_filler(
            protected_registers={
                register,
                destination,
            }
        )

        words = (
            addi(
                register,
                0,
                ALU_PRODUCER_VALUE,
            ),
            filler_word,
            self._consumer_for_variant(
                variant=variant,
                target_register=register,
                destination_register=destination,
            ),
        )

        return RealizedTemplate(
            arm_id=ArmID.A1,
            variant=variant,
            target=target,
            start_pc=start_pc,
            words=words,
            expected_executed_word_indices=(0, 1, 2),
            structural_word_indices=(1,),
            consumer_word_index=2,
            d2_producer_word_index=0,
        )

    def _realize_load_d1(
        self,
        target: TargetSelection,
        start_pc: int,
    ) -> RealizedTemplate:
        register = target.d1
        assert register is not None

        destination = _positive_auxiliary_register(
            {register}
        )

        variant = self._choose_operand_variant()

        words = (
            lw(
                register,
                0,
                LOAD_OFFSET,
            ),
            self._consumer_for_variant(
                variant=variant,
                target_register=register,
                destination_register=destination,
            ),
        )

        return RealizedTemplate(
            arm_id=ArmID.A2,
            variant=variant,
            target=target,
            start_pc=start_pc,
            words=words,
            expected_executed_word_indices=(0, 1),
            structural_word_indices=(),
            consumer_word_index=1,
            d1_producer_word_index=0,
        )

    def _realize_load_d2(
        self,
        target: TargetSelection,
        start_pc: int,
    ) -> RealizedTemplate:
        register = target.d2
        assert register is not None

        destination = _positive_auxiliary_register(
            {register}
        )

        variant = self._choose_operand_variant()

        filler_word = self._structural_filler(
            protected_registers={
                register,
                destination,
            }
        )

        words = (
            lw(
                register,
                0,
                LOAD_OFFSET,
            ),
            filler_word,
            self._consumer_for_variant(
                variant=variant,
                target_register=register,
                destination_register=destination,
            ),
        )

        return RealizedTemplate(
            arm_id=ArmID.A3,
            variant=variant,
            target=target,
            start_pc=start_pc,
            words=words,
            expected_executed_word_indices=(0, 1, 2),
            structural_word_indices=(1,),
            consumer_word_index=2,
            d2_producer_word_index=0,
        )

    def _realize_dual(
        self,
        target: TargetSelection,
        start_pc: int,
    ) -> RealizedTemplate:
        d1_register = target.d1
        d2_register = target.d2

        assert d1_register is not None
        assert d2_register is not None

        destination = _positive_auxiliary_register(
            {
                d1_register,
                d2_register,
            }
        )

        # Older d2 producer first, then newer d1 producer.
        # The second producer is intentionally source-independent so it
        # does not create an incidental dependency on the d2 register.
        words = (
            addi(
                d2_register,
                0,
                10,
            ),
            addi(
                d1_register,
                0,
                20,
            ),
            add(
                destination,
                d1_register,
                d2_register,
            ),
        )

        return RealizedTemplate(
            arm_id=ArmID.A4,
            variant=TemplateVariant.DUAL,
            target=target,
            start_pc=start_pc,
            words=words,
            expected_executed_word_indices=(0, 1, 2),
            structural_word_indices=(),
            consumer_word_index=2,
            d1_producer_word_index=1,
            d2_producer_word_index=0,
        )

    def _choose_special_variant(
        self,
    ) -> TemplateVariant:
        return self._rng.choice(
            (
                TemplateVariant.LUI,
                TemplateVariant.AUIPC,
            )
        )

    @staticmethod
    def _special_producer(
        variant: TemplateVariant,
        register: int,
    ) -> int:
        if variant is TemplateVariant.LUI:
            return lui(
                register,
                SPECIAL_IMM20,
            )

        if variant is TemplateVariant.AUIPC:
            return auipc(
                register,
                SPECIAL_IMM20,
            )

        raise TemplateConstructionError(
            f"invalid special producer variant: {variant}"
        )

    def _realize_special_d1(
        self,
        target: TargetSelection,
        start_pc: int,
    ) -> RealizedTemplate:
        register = target.d1
        assert register is not None

        destination = _positive_auxiliary_register(
            {register}
        )

        variant = self._choose_special_variant()

        words = (
            self._special_producer(
                variant,
                register,
            ),
            addi(
                destination,
                register,
                1,
            ),
        )

        return RealizedTemplate(
            arm_id=ArmID.A5,
            variant=variant,
            target=target,
            start_pc=start_pc,
            words=words,
            expected_executed_word_indices=(0, 1),
            structural_word_indices=(),
            consumer_word_index=1,
            d1_producer_word_index=0,
        )

    def _realize_special_d2(
        self,
        target: TargetSelection,
        start_pc: int,
    ) -> RealizedTemplate:
        register = target.d2
        assert register is not None

        destination = _positive_auxiliary_register(
            {register}
        )

        variant = self._choose_special_variant()

        filler_word = self._structural_filler(
            protected_registers={
                register,
                destination,
            }
        )

        words = (
            self._special_producer(
                variant,
                register,
            ),
            filler_word,
            addi(
                destination,
                register,
                1,
            ),
        )

        return RealizedTemplate(
            arm_id=ArmID.A6,
            variant=variant,
            target=target,
            start_pc=start_pc,
            words=words,
            expected_executed_word_indices=(0, 1, 2),
            structural_word_indices=(1,),
            consumer_word_index=2,
            d2_producer_word_index=0,
        )

    def _realize_link_d1(
        self,
        target: TargetSelection,
        start_pc: int,
    ) -> RealizedTemplate:
        register = target.d1
        assert register is not None

        destination = _positive_auxiliary_register(
            {register}
        )

        fallthrough_1, fallthrough_2 = (
            _two_auxiliary_registers(
                {
                    register,
                    destination,
                }
            )
        )

        target_pc = (
            start_pc
            + JUMP_LOCAL_TARGET_OFFSET
        )

        legal_variants = [
            TemplateVariant.JAL
        ]

        # JALR xR, x0, target_pc is self-contained when the absolute
        # target fits the signed I-immediate. x0 introduces no positive
        # L2 dependency.
        if _signed_12_fits(target_pc):
            legal_variants.append(
                TemplateVariant.JALR
            )

        if len(legal_variants) == 1:
            variant = legal_variants[0]
        else:
            variant = self._rng.choice(
                tuple(legal_variants)
            )

        if variant is TemplateVariant.JAL:
            producer = jal(
                register,
                JUMP_LOCAL_TARGET_OFFSET,
            )

        elif variant is TemplateVariant.JALR:
            producer = jalr(
                register,
                0,
                target_pc,
            )

        else:
            raise TemplateConstructionError(
                f"invalid link variant: {variant}"
            )

        words = (
            producer,

            # Sequential fall-through words. Correct redirect semantics
            # require both to be flushed and absent from executed order.
            addi(
                fallthrough_1,
                0,
                9,
            ),
            addi(
                fallthrough_2,
                0,
                10,
            ),

            # First executed instruction at redirect target.
            addi(
                destination,
                register,
                1,
            ),
        )

        return RealizedTemplate(
            arm_id=ArmID.A7,
            variant=variant,
            target=target,
            start_pc=start_pc,
            words=words,
            expected_executed_word_indices=(0, 3),
            structural_word_indices=(1, 2),
            consumer_word_index=3,
            d1_producer_word_index=0,
        )

    def _realize_store_data_d1(
        self,
        target: TargetSelection,
        start_pc: int,
    ) -> RealizedTemplate:
        register = target.d1
        assert register is not None

        words = (
            addi(
                register,
                0,
                STORE_DATA_VALUE,
            ),

            # rs2 = target register.
            # rs1 = x0, immediate = 0 -> address zero.
            # Therefore store-data forwarding is distinct from address
            # generation and creates no positive base-register RAW.
            sw(
                register,
                0,
                STORE_OFFSET,
            ),
        )

        return RealizedTemplate(
            arm_id=ArmID.A8,
            variant=TemplateVariant.STORE_DATA,
            target=target,
            start_pc=start_pc,
            words=words,
            expected_executed_word_indices=(0, 1),
            structural_word_indices=(),
            consumer_word_index=1,
            d1_producer_word_index=0,
        )

    def _realize_priority_d1(
        self,
        target: TargetSelection,
        start_pc: int,
    ) -> RealizedTemplate:
        register = target.d1
        assert register is not None

        destination = _positive_auxiliary_register(
            {register}
        )

        words = (
            # Older writer: shadowed by the following writer.
            addi(
                register,
                0,
                1,
            ),

            # Newest active d1 writer.
            addi(
                register,
                0,
                2,
            ),

            # Consumer must resolve to the newest writer.
            addi(
                destination,
                register,
                0,
            ),
        )

        return RealizedTemplate(
            arm_id=ArmID.A9,
            variant=TemplateVariant.PRIORITY,
            target=target,
            start_pc=start_pc,
            words=words,
            expected_executed_word_indices=(0, 1, 2),
            structural_word_indices=(),
            consumer_word_index=2,
            d1_producer_word_index=1,
            shadowed_writer_word_indices=(0,),
        )
