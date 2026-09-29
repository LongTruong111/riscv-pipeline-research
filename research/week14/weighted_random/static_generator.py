from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from random import Random

from research.week10.adaptive.register_policy import (
    TargetSelection,
)
from research.week10.adaptive.template_library import (
    ArmID,
    Distance,
    get_template,
)
from research.week10.adaptive.template_realizer import (
    RealizedTemplate,
    TemplateRealizer,
)
from research.week13.pure_random.runtime_stream import (
    physical_pc_for_logical_word,
)


# Exact Week-5 frozen integer ticket representation.
#
# Sampling one uniform index in [0, 15] therefore realizes:
#
# A0 2/16
# A1 2/16
# A2 2/16
# A3 2/16
# A4 1/16
# A5 2/16
# A6 2/16
# A7 1/16
# A8 1/16
# A9 1/16
ARM_TICKETS: tuple[ArmID, ...] = (
    ArmID.A0,
    ArmID.A0,
    ArmID.A1,
    ArmID.A1,
    ArmID.A2,
    ArmID.A2,
    ArmID.A3,
    ArmID.A3,
    ArmID.A4,
    ArmID.A5,
    ArmID.A5,
    ArmID.A6,
    ArmID.A6,
    ArmID.A7,
    ArmID.A8,
    ArmID.A9,
)

POSITIVE_REGISTERS: tuple[int, ...] = tuple(
    range(1, 32)
)

_RNG_SCHEMA = "week14.m2.static-rng.v1"


def _validate_root_seed(root_seed: int) -> None:
    if (
        isinstance(root_seed, bool)
        or not isinstance(root_seed, int)
        or root_seed < 0
    ):
        raise ValueError(
            "root_seed must be a non-negative integer"
        )


def _validate_budget(
    accepted_instruction_budget: int,
) -> None:
    if (
        isinstance(
            accepted_instruction_budget,
            bool,
        )
        or not isinstance(
            accepted_instruction_budget,
            int,
        )
        or accepted_instruction_budget <= 0
    ):
        raise ValueError(
            "accepted_instruction_budget "
            "must be positive"
        )


def derive_rng_seed(
    root_seed: int,
    domain: str,
) -> int:
    """
    Deterministically derive an independent RNG domain.

    Domain separation prevents variable target/realization
    draw counts from perturbing the weighted arm sequence.
    """
    _validate_root_seed(root_seed)

    if domain not in {
        "arm",
        "target",
        "realization",
    }:
        raise ValueError(
            f"unsupported RNG domain: {domain!r}"
        )

    payload = (
        f"{_RNG_SCHEMA}|"
        f"{root_seed}|"
        f"{domain}"
    ).encode("ascii")

    digest = hashlib.sha256(payload).digest()

    return int.from_bytes(
        digest[:16],
        byteorder="big",
        signed=False,
    )


class StaticWeightedArmSampler:
    """
    Fixed M2 A0-A9 policy.

    No campaign state, coverage, checker result,
    reward, or adaptive utility is accepted by this API.
    """

    def __init__(self, rng: Random) -> None:
        if not isinstance(rng, Random):
            raise TypeError(
                "rng must be random.Random"
            )

        self._rng = rng

    def sample(self) -> ArmID:
        ticket = self._rng.randrange(
            len(ARM_TICKETS)
        )

        return ARM_TICKETS[ticket]


class StaticUniformTargetSampler:
    """
    Frozen Weighted-Random register targeting.

    Single-distance arms:
        Uniform x1..x31.

    A4:
        ordered d1/d2 pair sampled uniformly
        without replacement.

    No coverage state exists in this interface.
    """

    def __init__(self, rng: Random) -> None:
        if not isinstance(rng, Random):
            raise TypeError(
                "rng must be random.Random"
            )

        self._rng = rng

    def sample(
        self,
        arm_id: ArmID,
    ) -> TargetSelection:
        spec = get_template(arm_id)

        if spec.distance is Distance.D1:
            return TargetSelection(
                d1=self._rng.choice(
                    POSITIVE_REGISTERS
                ),
            )

        if spec.distance is Distance.D2:
            return TargetSelection(
                d2=self._rng.choice(
                    POSITIVE_REGISTERS
                ),
            )

        if spec.distance is Distance.D1_D2:
            d1 = self._rng.choice(
                POSITIVE_REGISTERS
            )

            remaining = tuple(
                register
                for register
                in POSITIVE_REGISTERS
                if register != d1
            )

            d2 = self._rng.choice(
                remaining
            )

            return TargetSelection(
                d1=d1,
                d2=d2,
            )

        raise RuntimeError(
            "unsupported frozen template distance: "
            f"{spec.distance!r}"
        )


@dataclass(frozen=True)
class PlannedWeightedRandomBlock:
    block_index: int
    logical_word_start: int
    first_accepted_instruction_index: int

    arm_id: ArmID
    target: TargetSelection
    realized: RealizedTemplate

    # Exact accepted prefix of the template's
    # architecturally executed word sequence.
    accepted_word_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.block_index, bool)
            or not isinstance(
                self.block_index,
                int,
            )
            or self.block_index < 0
        ):
            raise ValueError(
                "block_index must be non-negative"
            )

        if (
            isinstance(
                self.logical_word_start,
                bool,
            )
            or not isinstance(
                self.logical_word_start,
                int,
            )
            or self.logical_word_start < 0
        ):
            raise ValueError(
                "logical_word_start "
                "must be non-negative"
            )

        if (
            isinstance(
                self.first_accepted_instruction_index,
                bool,
            )
            or not isinstance(
                self.first_accepted_instruction_index,
                int,
            )
            or (
                self.first_accepted_instruction_index
                <= 0
            )
        ):
            raise ValueError(
                "first accepted instruction index "
                "must be positive"
            )

        if self.realized.arm_id is not self.arm_id:
            raise ValueError(
                "realized arm identity mismatch"
            )

        if self.realized.target != self.target:
            raise ValueError(
                "realized target identity mismatch"
            )

        expected_start_pc = (
            physical_pc_for_logical_word(
                self.logical_word_start
            )
        )

        if (
            self.realized.start_pc
            != expected_start_pc
        ):
            raise ValueError(
                "realized physical start PC "
                "does not match logical placement"
            )

        expected = (
            self.realized
            .expected_executed_word_indices
        )

        if not self.accepted_word_indices:
            raise ValueError(
                "block must contribute at least "
                "one accepted instruction"
            )

        if (
            self.accepted_word_indices
            != expected[
                :len(
                    self.accepted_word_indices
                )
            ]
        ):
            raise ValueError(
                "accepted indices must be an exact "
                "prefix of executed template order"
            )

    @property
    def image_word_count(self) -> int:
        return self.realized.image_word_count

    @property
    def accepted_instruction_count(
        self,
    ) -> int:
        return len(
            self.accepted_word_indices
        )

    @property
    def full_expected_instruction_count(
        self,
    ) -> int:
        return (
            self.realized
            .expected_executed_instruction_count
        )

    @property
    def is_partial(self) -> bool:
        return (
            self.accepted_instruction_count
            < self.full_expected_instruction_count
        )

    def hash_payload(self) -> dict:
        return {
            "block_index":
                self.block_index,
            "logical_word_start":
                self.logical_word_start,
            "first_accepted_instruction_index":
                self.first_accepted_instruction_index,
            "arm_id":
                self.arm_id.value,
            "target": {
                "d1": self.target.d1,
                "d2": self.target.d2,
            },
            "variant":
                self.realized.variant.value,
            "start_pc":
                self.realized.start_pc,
            "words":
                list(self.realized.words),
            "expected_executed_word_indices":
                list(
                    self.realized
                    .expected_executed_word_indices
                ),
            "accepted_word_indices":
                list(
                    self.accepted_word_indices
                ),
        }


@dataclass(frozen=True)
class WeightedRandomPlan:
    root_seed: int
    accepted_instruction_budget: int
    blocks: tuple[
        PlannedWeightedRandomBlock,
        ...,
    ]

    def __post_init__(self) -> None:
        _validate_root_seed(
            self.root_seed
        )

        _validate_budget(
            self.accepted_instruction_budget
        )

        if not self.blocks:
            raise ValueError(
                "weighted plan must not be empty"
            )

        accepted = 0
        logical_word = 0

        for expected_block_index, block in enumerate(
            self.blocks
        ):
            if (
                block.block_index
                != expected_block_index
            ):
                raise ValueError(
                    "block indices are not contiguous"
                )

            if (
                block.logical_word_start
                != logical_word
            ):
                raise ValueError(
                    "logical program layout "
                    "is not contiguous"
                )

            if (
                block
                .first_accepted_instruction_index
                != accepted + 1
            ):
                raise ValueError(
                    "accepted instruction indices "
                    "are not contiguous"
                )

            accepted += (
                block.accepted_instruction_count
            )

            logical_word += (
                block.image_word_count
            )

        if (
            accepted
            != self.accepted_instruction_budget
        ):
            raise ValueError(
                "plan does not terminate at "
                "exact accepted budget"
            )

        if any(
            block.is_partial
            for block in self.blocks[:-1]
        ):
            raise ValueError(
                "only final block may be partial"
            )

    @property
    def accepted_instruction_count(
        self,
    ) -> int:
        return sum(
            block.accepted_instruction_count
            for block in self.blocks
        )

    @property
    def image_word_count(self) -> int:
        return sum(
            block.image_word_count
            for block in self.blocks
        )

    @property
    def arm_histogram(self) -> dict[str, int]:
        counts = Counter(
            block.arm_id.value
            for block in self.blocks
        )

        return {
            arm.value: counts[arm.value]
            for arm in ArmID
        }

    def hash_payload(self) -> dict:
        return {
            "schema":
                "week14.m2-static-plan.v1",
            "rng_schema":
                _RNG_SCHEMA,
            "root_seed":
                self.root_seed,
            "accepted_instruction_budget":
                self.accepted_instruction_budget,
            "blocks": [
                block.hash_payload()
                for block in self.blocks
            ],
        }

    @property
    def plan_hash(self) -> str:
        canonical = json.dumps(
            self.hash_payload(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return hashlib.sha256(
            canonical
        ).hexdigest()


def generate_weighted_random_plan(
    root_seed: int,
    accepted_instruction_budget: int,
) -> WeightedRandomPlan:
    """
    Generate the complete deterministic M2 static plan.

    Complexity:
        O(N) time and O(N) offline plan storage,
        since every frozen template contains O(1)
        executed/image words.

    No DUT state, coverage state, reward, checker result,
    or adaptive policy object is accepted or observed.
    """
    _validate_root_seed(root_seed)

    _validate_budget(
        accepted_instruction_budget
    )

    arm_rng = Random(
        derive_rng_seed(
            root_seed,
            "arm",
        )
    )

    target_rng = Random(
        derive_rng_seed(
            root_seed,
            "target",
        )
    )

    realization_rng = Random(
        derive_rng_seed(
            root_seed,
            "realization",
        )
    )

    arm_sampler = StaticWeightedArmSampler(
        arm_rng
    )

    target_sampler = (
        StaticUniformTargetSampler(
            target_rng
        )
    )

    realizer = TemplateRealizer(
        realization_rng
    )

    blocks: list[
        PlannedWeightedRandomBlock
    ] = []

    accepted = 0
    logical_word_start = 0

    while (
        accepted
        < accepted_instruction_budget
    ):
        arm_id = arm_sampler.sample()

        target = target_sampler.sample(
            arm_id
        )

        start_pc = (
            physical_pc_for_logical_word(
                logical_word_start
            )
        )

        realized = realizer.realize(
            arm_id,
            target,
            start_pc=start_pc,
        )

        remaining = (
            accepted_instruction_budget
            - accepted
        )

        full_execution = (
            realized
            .expected_executed_word_indices
        )

        accepted_word_indices = (
            full_execution[:remaining]
        )

        block = PlannedWeightedRandomBlock(
            block_index=len(blocks),
            logical_word_start=(
                logical_word_start
            ),
            first_accepted_instruction_index=(
                accepted + 1
            ),
            arm_id=arm_id,
            target=target,
            realized=realized,
            accepted_word_indices=(
                accepted_word_indices
            ),
        )

        blocks.append(block)

        accepted += (
            block.accepted_instruction_count
        )

        logical_word_start += (
            block.image_word_count
        )

    return WeightedRandomPlan(
        root_seed=root_seed,
        accepted_instruction_budget=(
            accepted_instruction_budget
        ),
        blocks=tuple(blocks),
    )
