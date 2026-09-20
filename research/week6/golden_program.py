from typing import Tuple

from research.week5.impl.rv32_encode import (
    add,
    addi,
    auipc,
    lui,
    lw,
    sw,
)


GOLDEN_PROGRAM_INSTRUCTION_COUNT = 58


def build_golden_program() -> Tuple[int, ...]:
    """
    Deterministic 58-instruction architectural workload for Gate T6.

    Final expected state:
        x1 = 100
        x2 = 11
        x3 = 67
        x4 = 67
        x5 = 68
        x6 = 0x12345000
        x7 = 28

        mem[100] = 3
        mem[104] = 67

    The program is intentionally straight-line. Control-flow semantics
    are tested separately so this workload remains an unambiguous
    >=50 executed-instruction Golden Model gate.
    """

    words = [
        # ----------------------------------------------------------
        # Initial architectural state.
        # ----------------------------------------------------------
        addi(1, 0, 100),       # x1 = memory base
        addi(2, 0, 1),         # x2 = 1
        addi(3, 0, 2),         # x3 = 2
        add(4, 2, 3),          # x4 = 3
        sw(4, 1, 0),           # mem[100] = 3
        lw(5, 1, 0),           # x5 = 3
        lui(6, 0x12345),       # x6 = 0x12345000
        auipc(7, 0),           # x7 = PC = 28
    ]

    # --------------------------------------------------------------
    # Ten iterations x five instructions = 50 instructions.
    #
    # Each iteration:
    #     x2 += 1
    #     x3 += x2
    #     mem[104] = x3
    #     x4 = mem[104]
    #     x5 = x4 + 1
    # --------------------------------------------------------------
    for _ in range(10):
        words.extend(
            [
                addi(2, 2, 1),
                add(3, 3, 2),
                sw(3, 1, 4),
                lw(4, 1, 4),
                addi(5, 4, 1),
            ]
        )

    if len(words) != GOLDEN_PROGRAM_INSTRUCTION_COUNT:
        raise AssertionError(
            "Gate T6 Golden program length changed unexpectedly: "
            f"{len(words)}"
        )

    return tuple(words)
