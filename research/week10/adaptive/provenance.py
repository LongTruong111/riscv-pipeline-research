from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

from research.week5.impl.coverage_model import L2Hit

from research.week10.adaptive.template_library import (
    ArmID,
    Distance,
)
from research.week10.adaptive.template_realizer import (
    RealizedTemplate,
)


WitnessKey = Tuple[int, int, int, int]


def _distance_int(distance: Distance) -> int:
    if distance is Distance.D1:
        return 1

    if distance is Distance.D2:
        return 2

    raise ValueError(
        "attribution witness distance must be D1 or D2"
    )


@dataclass(frozen=True, slots=True)
class AttributionWitness:
    """
    Exact provenance for one intended positive L2 dependency.

    The producer/consumer identities are executed-program-order
    instruction indices, not PCs and not program-image word indices.
    """

    arm_id: ArmID
    template_instance_id: int

    distance: Distance
    register: int

    producer_instruction_index: int
    consumer_instruction_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.arm_id, ArmID):
            raise TypeError(
                "arm_id must be ArmID"
            )

        if (
            isinstance(self.template_instance_id, bool)
            or not isinstance(
                self.template_instance_id,
                int,
            )
            or self.template_instance_id <= 0
        ):
            raise ValueError(
                "template_instance_id must be a positive integer"
            )

        distance = _distance_int(
            self.distance
        )

        if (
            isinstance(self.register, bool)
            or not isinstance(self.register, int)
            or not 1 <= self.register <= 31
        ):
            raise ValueError(
                "register must be x1..x31"
            )

        for name, value in (
            (
                "producer_instruction_index",
                self.producer_instruction_index,
            ),
            (
                "consumer_instruction_index",
                self.consumer_instruction_index,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be a positive integer"
                )

        if (
            self.producer_instruction_index
            >= self.consumer_instruction_index
        ):
            raise ValueError(
                "producer must precede consumer"
            )

        actual_distance = (
            self.consumer_instruction_index
            - self.producer_instruction_index
        )

        if actual_distance != distance:
            raise ValueError(
                "witness executed distance mismatch: "
                f"declared=d{distance}, "
                f"actual=d{actual_distance}"
            )

    @property
    def key(self) -> WitnessKey:
        return (
            _distance_int(self.distance),
            self.register,
            self.producer_instruction_index,
            self.consumer_instruction_index,
        )

    def matches_hit(
        self,
        hit: L2Hit,
    ) -> bool:
        if not isinstance(hit, L2Hit):
            raise TypeError(
                "hit must be L2Hit"
            )

        return self.key == (
            hit.distance,
            hit.register,
            hit.producer_instruction_index,
            hit.consumer_instruction_index,
        )


def build_template_witnesses(
    realized: RealizedTemplate,
    *,
    template_instance_id: int,
    first_executed_instruction_index: int,
) -> Tuple[AttributionWitness, ...]:
    """
    Convert one realized template into exact intended L2 witnesses.

    first_executed_instruction_index is the instruction_index that will
    be assigned to the first architecturally executed word of this
    template.

    Flushed image words are absent from expected_executed_word_indices,
    so they consume no executed-program-order identity.
    """
    if not isinstance(
        realized,
        RealizedTemplate,
    ):
        raise TypeError(
            "realized must be RealizedTemplate"
        )

    if (
        isinstance(template_instance_id, bool)
        or not isinstance(template_instance_id, int)
        or template_instance_id <= 0
    ):
        raise ValueError(
            "template_instance_id must be a positive integer"
        )

    if (
        isinstance(
            first_executed_instruction_index,
            bool,
        )
        or not isinstance(
            first_executed_instruction_index,
            int,
        )
        or first_executed_instruction_index <= 0
    ):
        raise ValueError(
            "first_executed_instruction_index "
            "must be a positive integer"
        )

    executed_word_indices = (
        realized.expected_executed_word_indices
    )

    if not executed_word_indices:
        raise ValueError(
            "realized template has no executed words"
        )

    word_to_instruction_index = {
        word_index: (
            first_executed_instruction_index
            + offset
        )
        for offset, word_index in enumerate(
            executed_word_indices
        )
    }

    try:
        consumer_instruction_index = (
            word_to_instruction_index[
                realized.consumer_word_index
            ]
        )
    except KeyError as exc:
        raise ValueError(
            "template consumer is not in executed-program order"
        ) from exc

    witnesses = []

    if realized.d1_producer_word_index is not None:
        register = realized.target.d1

        if register is None:
            raise ValueError(
                "d1 producer exists but d1 target is missing"
            )

        try:
            producer_instruction_index = (
                word_to_instruction_index[
                    realized.d1_producer_word_index
                ]
            )
        except KeyError as exc:
            raise ValueError(
                "d1 producer is not architecturally executed"
            ) from exc

        witnesses.append(
            AttributionWitness(
                arm_id=realized.arm_id,
                template_instance_id=(
                    template_instance_id
                ),
                distance=Distance.D1,
                register=register,
                producer_instruction_index=(
                    producer_instruction_index
                ),
                consumer_instruction_index=(
                    consumer_instruction_index
                ),
            )
        )

    if realized.d2_producer_word_index is not None:
        register = realized.target.d2

        if register is None:
            raise ValueError(
                "d2 producer exists but d2 target is missing"
            )

        try:
            producer_instruction_index = (
                word_to_instruction_index[
                    realized.d2_producer_word_index
                ]
            )
        except KeyError as exc:
            raise ValueError(
                "d2 producer is not architecturally executed"
            ) from exc

        witnesses.append(
            AttributionWitness(
                arm_id=realized.arm_id,
                template_instance_id=(
                    template_instance_id
                ),
                distance=Distance.D2,
                register=register,
                producer_instruction_index=(
                    producer_instruction_index
                ),
                consumer_instruction_index=(
                    consumer_instruction_index
                ),
            )
        )

    expected_count = (
        2
        if realized.arm_id is ArmID.A4
        else 1
    )

    if len(witnesses) != expected_count:
        raise ValueError(
            "realized template produced unexpected witness count: "
            f"arm={realized.arm_id.value}, "
            f"expected={expected_count}, "
            f"actual={len(witnesses)}"
        )

    return tuple(witnesses)


class AttributionRegistry:
    """
    Bounded pending-witness registry.

    Matching is exact on:

        distance
        register
        producer instruction_index
        consumer instruction_index

    Global L2 coverage is deliberately outside this object.

    Campaign code may register future template witnesses ahead of
    execution. prune() removes witnesses whose consumer has already
    executed without producing the intended hit.

    If the instruction streaming window is bounded, retained registry
    state is bounded independently of total campaign length N.
    """

    def __init__(self) -> None:
        self._by_key: Dict[
            WitnessKey,
            AttributionWitness,
        ] = {}

        self._keys_by_consumer: Dict[
            int,
            set[WitnessKey],
        ] = {}

    @property
    def pending_count(self) -> int:
        return len(self._by_key)

    @property
    def pending_consumer_count(self) -> int:
        return len(
            self._keys_by_consumer
        )

    def register(
        self,
        witness: AttributionWitness,
    ) -> None:
        if not isinstance(
            witness,
            AttributionWitness,
        ):
            raise TypeError(
                "witness must be AttributionWitness"
            )

        key = witness.key

        if key in self._by_key:
            raise ValueError(
                "duplicate attribution witness"
            )

        self._by_key[key] = witness

        self._keys_by_consumer.setdefault(
            witness.consumer_instruction_index,
            set(),
        ).add(key)

    def register_many(
        self,
        witnesses: Iterable[
            AttributionWitness
        ],
    ) -> None:
        witnesses = tuple(witnesses)

        # Validate duplicate keys before mutating state so the batch is
        # atomic with respect to duplicate-registration errors.
        batch_keys = [
            witness.key
            for witness in witnesses
        ]

        if len(batch_keys) != len(set(batch_keys)):
            raise ValueError(
                "duplicate witness within registration batch"
            )

        for witness in witnesses:
            if not isinstance(
                witness,
                AttributionWitness,
            ):
                raise TypeError(
                    "all witnesses must be AttributionWitness"
                )

            if witness.key in self._by_key:
                raise ValueError(
                    "attribution witness already registered"
                )

        for witness in witnesses:
            self.register(witness)

    def consume_match(
        self,
        hit: L2Hit,
    ) -> Optional[AttributionWitness]:
        """
        Return and consume the exact matching planned witness.

        Incidental same-bin hits with different producer/consumer
        identities return None and remain globally valid L2 Intent hits.
        """
        if not isinstance(hit, L2Hit):
            raise TypeError(
                "hit must be L2Hit"
            )

        key = (
            hit.distance,
            hit.register,
            hit.producer_instruction_index,
            hit.consumer_instruction_index,
        )

        witness = self._by_key.pop(
            key,
            None,
        )

        if witness is None:
            return None

        consumer_keys = (
            self._keys_by_consumer[
                witness.consumer_instruction_index
            ]
        )

        consumer_keys.remove(key)

        if not consumer_keys:
            del self._keys_by_consumer[
                witness.consumer_instruction_index
            ]

        return witness

    def prune(
        self,
        *,
        latest_instruction_index: int,
    ) -> int:
        """
        Drop unmatched witnesses whose consumer is no longer future.

        Call only after all L2 hits for latest_instruction_index have
        been processed.

        Returns the number of discarded witnesses.
        """
        if (
            isinstance(
                latest_instruction_index,
                bool,
            )
            or not isinstance(
                latest_instruction_index,
                int,
            )
            or latest_instruction_index <= 0
        ):
            raise ValueError(
                "latest_instruction_index "
                "must be a positive integer"
            )

        stale_consumers = tuple(
            consumer
            for consumer
            in self._keys_by_consumer
            if consumer <= latest_instruction_index
        )

        removed = 0

        for consumer in stale_consumers:
            keys = self._keys_by_consumer.pop(
                consumer
            )

            for key in keys:
                if self._by_key.pop(
                    key,
                    None,
                ) is not None:
                    removed += 1

        return removed

    def discard_future_after(
        self,
        *,
        last_executed_instruction_index: int,
    ) -> int:
        """
        Discard all still-pending attribution witnesses at final campaign
        termination.

        Calling contract:
            prune(last_executed_instruction_index) must already have run
            after all L2 hits for the final executed instruction were
            processed.

        Therefore every witness still present here must belong strictly
        to the architecturally unexecuted future suffix.

        Returns the number of discarded witnesses.

        Complexity is O(P), where P is the bounded number of resident
        pending witnesses, hence O(1) with respect to campaign length N.
        """
        if (
            isinstance(
                last_executed_instruction_index,
                bool,
            )
            or not isinstance(
                last_executed_instruction_index,
                int,
            )
            or last_executed_instruction_index <= 0
        ):
            raise ValueError(
                "last_executed_instruction_index "
                "must be a positive integer"
            )

        nonfuture_consumers = tuple(
            sorted(
                consumer
                for consumer
                in self._keys_by_consumer
                if (
                    consumer
                    <= last_executed_instruction_index
                )
            )
        )

        if nonfuture_consumers:
            raise RuntimeError(
                "cannot discard campaign suffix while "
                "non-future attribution witnesses remain: "
                f"{nonfuture_consumers}"
            )

        removed = len(
            self._by_key
        )

        self._by_key.clear()
        self._keys_by_consumer.clear()

        return removed
