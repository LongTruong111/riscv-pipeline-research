"""Deterministic 50-instruction integrated timing workload for Gate T11."""

from typing import Tuple

from research.week5.impl.rv32_encode import add, addi, lw, sw


WEEK11_INTEGRATED_INSTRUCTION_COUNT = 50


def build_week11_integrated_sequence() -> Tuple[int, ...]:
    """
    Straight-line workload for composition-level timing verification.

    Intentionally covers:
      - ALU d1 / d2
      - LOAD d1 on RS1 / RS2
      - LOAD d2
      - simultaneous d1+d2 forwarding
      - newest-producer priority
      - store-data forwarding
      - repeated/back-to-back load-use hazards

    Known frozen DUT-defect bins H11/H13/H18/H19/H20 and redirects are
    intentionally excluded from this PASS gate. They remain covered by
    their canonical directed regressions.
    """

    words = [
        # 01-05: ALU d2 then d1.
        addi(1, 0, 64),
        addi(5, 0, 7),
        addi(9, 0, 0),
        addi(6, 5, 1),
        addi(7, 6, 1),

        # 06-10: LOAD d1 on RS1 and RS2.
        lw(10, 1, 0),
        addi(11, 10, 1),
        addi(12, 0, 2),
        lw(13, 1, 4),
        add(14, 0, 13),

        # 11-15: LOAD d2 + simultaneous d1/d2.
        lw(15, 1, 8),
        addi(20, 0, 1),
        addi(16, 15, 1),
        addi(17, 0, 3),
        add(18, 17, 16),

        # 16-20: newest-producer priority.
        addi(21, 0, 1),
        addi(21, 0, 2),
        addi(22, 21, 0),
        addi(23, 0, 4),
        add(24, 22, 23),

        # 21-25: store-data + load-use + ALU chain.
        addi(25, 0, 42),
        sw(25, 1, 12),
        lw(26, 1, 12),
        addi(27, 26, 1),
        addi(28, 27, 1),

        # 26-30: consecutive load-use hazards.
        lw(5, 1, 16),
        addi(6, 5, 1),
        lw(7, 1, 20),
        addi(8, 7, 1),
        add(9, 8, 6),

        # 31-35: d1/d2 dual forwarding + store data.
        addi(10, 0, 5),
        addi(11, 10, 1),
        addi(12, 10, 2),
        add(13, 12, 11),
        sw(13, 1, 24),

        # 36-40: mixed LOAD d2 and LOAD d1.
        lw(14, 1, 24),
        addi(15, 0, 1),
        add(16, 14, 15),
        lw(17, 1, 28),
        add(18, 17, 16),

        # 41-45: overwrite / newest producer + store.
        addi(19, 0, 1),
        addi(20, 19, 1),
        addi(20, 0, 9),
        add(21, 20, 19),
        sw(21, 1, 32),

        # 46-50: load-use followed by dense ALU chain.
        lw(22, 1, 32),
        addi(23, 22, 1),
        addi(24, 23, 1),
        addi(25, 24, 1),
        add(26, 25, 24),
    ]

    if len(words) != WEEK11_INTEGRATED_INSTRUCTION_COUNT:
        raise AssertionError(
            "Week11 integrated sequence must contain exactly "
            f"{WEEK11_INTEGRATED_INSTRUCTION_COUNT} instructions, "
            f"got {len(words)}"
        )

    return tuple(words)
