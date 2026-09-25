from __future__ import annotations

from enum import Enum
from random import Random


class InstructionFamily(str, Enum):
    ADD = "ADD"
    ADDI = "ADDI"
    LW = "LW"
    SW = "SW"
    BRANCH = "BRANCH"
    JAL = "JAL"
    JALR = "JALR"
    LUI = "LUI"
    AUIPC = "AUIPC"


# Frozen order from STOCHASTIC_GENERATOR_ADDENDUM.md.
#
# Every family draw selects one index uniformly from [0, 8].
FAMILY_ORDER = (
    InstructionFamily.ADD,
    InstructionFamily.ADDI,
    InstructionFamily.LW,
    InstructionFamily.SW,
    InstructionFamily.BRANCH,
    InstructionFamily.JAL,
    InstructionFamily.JALR,
    InstructionFamily.LUI,
    InstructionFamily.AUIPC,
)


def sample_family(
    family_rng: Random,
) -> InstructionFamily:
    """
    Draw exactly one M1-PR stochastic payload family.

    Frozen distribution:

        P(F_i) = 1 / 9

    RNG ownership:
        This function consumes only family_rng.

    It deliberately performs no operand, coverage, legality, DUT,
    or architectural-state inspection.

    Complexity:
        O(1) time, O(1) memory.
    """
    if not isinstance(family_rng, Random):
        raise TypeError(
            "family_rng must be random.Random"
        )

    index = family_rng.randrange(
        len(FAMILY_ORDER)
    )

    return FAMILY_ORDER[index]
