from dataclasses import dataclass
from typing import Dict, Tuple

from .rv32_encode import (
    add,
    addi,
    auipc,
    jal,
    lui,
    lw,
    sw,
)


@dataclass(frozen=True, slots=True)
class DirectedCase:
    test_id: str
    target_bin: str
    words: Tuple[int, ...]
    expected_accepted: int

    # Architectural/microarchitectural oracle metadata.
    # These fields are NOT Intent-hit predicates.
    oracle_stall_cycles: int
    oracle_redirect: bool

    description: str


def _case(
    test_id: str,
    target_bin: str,
    words,
    expected_accepted: int,
    oracle_stall_cycles: int = 0,
    oracle_redirect: bool = False,
    description: str = "",
) -> DirectedCase:
    return DirectedCase(
        test_id=test_id,
        target_bin=target_bin,
        words=tuple(words),
        expected_accepted=expected_accepted,
        oracle_stall_cycles=oracle_stall_cycles,
        oracle_redirect=oracle_redirect,
        description=description,
    )


DIRECTED_CASES: Dict[str, DirectedCase] = {
    # --------------------------------------------------------------
    # A — canonical ALU forwarding
    # --------------------------------------------------------------
    "T01": _case(
        "T01",
        "H01",
        [
            addi(5, 0, 7),
            addi(6, 5, 1),
        ],
        expected_accepted=2,
        description="ALU d1 -> RS1_ONLY/RS1",
    ),

    "T02": _case(
        "T02",
        "H02",
        [
            addi(5, 0, 7),
            add(6, 0, 5),
        ],
        expected_accepted=2,
        description="ALU d1 -> RS2",
    ),

    "T03": _case(
        "T03",
        "H03",
        [
            addi(5, 0, 7),
            addi(9, 0, 0),
            addi(6, 5, 1),
        ],
        expected_accepted=3,
        description="ALU d2 -> RS1_ONLY/RS1",
    ),

    "T04": _case(
        "T04",
        "H04",
        [
            addi(5, 0, 7),
            addi(9, 0, 0),
            add(6, 0, 5),
        ],
        expected_accepted=3,
        description="ALU d2 -> RS2",
    ),

    # --------------------------------------------------------------
    # B — d3 Register-File boundary
    # --------------------------------------------------------------
    "T05": _case(
        "T05",
        "H05",
        [
            lw(5, 0, 0),
            addi(9, 0, 1),
            addi(10, 0, 2),
            addi(6, 5, 1),
        ],
        expected_accepted=4,
        description="LOAD producer visible through RF at executed d3",
    ),

    # --------------------------------------------------------------
    # C — LOAD/interlock
    # --------------------------------------------------------------
    "T06": _case(
        "T06",
        "H06",
        [
            lw(5, 0, 0),
            addi(6, 5, 1),
        ],
        expected_accepted=2,
        oracle_stall_cycles=1,
        description="LOAD d1 -> RS1_ONLY/RS1",
    ),

    "T07": _case(
        "T07",
        "H07",
        [
            lw(5, 0, 0),
            add(6, 0, 5),
        ],
        expected_accepted=2,
        oracle_stall_cycles=1,
        description="LOAD d1 -> RS2",
    ),

    "T08": _case(
        "T08",
        "H08",
        [
            lw(5, 0, 0),
            addi(9, 0, 0),
            addi(6, 5, 1),
        ],
        expected_accepted=3,
        description="LOAD d2 -> RS1_ONLY/RS1",
    ),

    "T09": _case(
        "T09",
        "H09",
        [
            lw(5, 0, 0),
            addi(9, 0, 0),
            add(6, 0, 5),
        ],
        expected_accepted=3,
        description="LOAD d2 -> RS2",
    ),

    # --------------------------------------------------------------
    # D — simultaneous dual forwarding
    # --------------------------------------------------------------
    "T10": _case(
        "T10",
        "H10",
        [
            addi(1, 0, 10),
            addi(2, 1, 5),
            add(3, 2, 1),
        ],
        expected_accepted=3,
        description="Dual ALU producers: d1 on RS1 and d2 on RS2",
    ),

    # --------------------------------------------------------------
    # E — non-ALU writeback producers
    # --------------------------------------------------------------
    "T11": _case(
        "T11",
        "H11",
        [
            lui(5, 0x12345),
            addi(6, 5, 1),
        ],
        expected_accepted=2,
        description="LUI/IMM d1 -> RS1",
    ),

    "T12": _case(
        "T12",
        "H12",
        [
            lui(5, 0x12345),
            addi(9, 0, 0),
            addi(6, 5, 1),
        ],
        expected_accepted=3,
        description="LUI/IMM d2 -> RS1",
    ),

    "T13": _case(
        "T13",
        "H13",
        [
            auipc(5, 0x12345),
            addi(6, 5, 1),
        ],
        expected_accepted=2,
        description="AUIPC/PC_PLUS_IMM d1 -> RS1",
    ),

    "T14": _case(
        "T14",
        "H14",
        [
            auipc(5, 0x12345),
            addi(9, 0, 0),
            addi(6, 5, 1),
        ],
        expected_accepted=3,
        description="AUIPC/PC_PLUS_IMM d2 -> RS1",
    ),

    # --------------------------------------------------------------
    # F — PC+4 link producer across redirect
    #
    # PC 0x00: jal x5, +12 -> target PC 0x0c
    # PC 0x04: fall-through instruction, must be flushed
    # PC 0x08: fall-through instruction, must be flushed
    # PC 0x0c: next executed consumer of x5
    # --------------------------------------------------------------
    "T15": _case(
        "T15",
        "H15",
        [
            jal(5, 12),
            addi(9, 0, 9),
            addi(10, 0, 10),
            addi(6, 5, 1),
        ],
        expected_accepted=2,
        oracle_redirect=True,
        description="JAL link -> next executed target consumer",
    ),

    # --------------------------------------------------------------
    # G — store-data forwarding
    # --------------------------------------------------------------
    "T16": _case(
        "T16",
        "H16",
        [
            addi(5, 0, 42),
            sw(5, 1, 0),
        ],
        expected_accepted=2,
        description="ALU d1 -> STORE data/RS2",
    ),

    # --------------------------------------------------------------
    # H — newest-producer priority
    # --------------------------------------------------------------
    "T17": _case(
        "T17",
        "H17",
        [
            addi(5, 0, 1),
            addi(5, 0, 2),
            addi(6, 5, 0),
        ],
        expected_accepted=3,
        description="newest d1 writer must dominate older d2 writer",
    ),

    # --------------------------------------------------------------
    # I — semantic negative cases
    # --------------------------------------------------------------
    "T18": _case(
        "T18",
        "H18",
        [
            addi(0, 1, 7),
            addi(6, 0, 1),
        ],
        expected_accepted=2,
        description="x0 destination followed by architectural x0 source",
    ),

    "T19": _case(
        "T19",
        "H19",
        [
            lw(0, 1, 0),
            addi(6, 0, 1),
        ],
        expected_accepted=2,
        oracle_stall_cycles=0,
        description="LOAD-to-x0 must not create architectural RAW stall",
    ),

    "T20": _case(
        "T20",
        "H20",
        [
            lw(5, 1, 0),
            # ADDI uses rs1=x2 only.
            # imm=5 makes raw instruction bits [24:20] equal x5.
            addi(6, 2, 5),
        ],
        expected_accepted=2,
        oracle_stall_cycles=0,
        description="unused OP-IMM raw rs2 field matches LOAD rd",
    ),
}


def validate_directed_cases() -> None:
    expected_tests = {f"T{i:02d}" for i in range(1, 21)}
    expected_bins = {f"H{i:02d}" for i in range(1, 21)}

    if set(DIRECTED_CASES) != expected_tests:
        raise ValueError("Directed test set must be exactly T01..T20")

    actual_bins = {
        case.target_bin
        for case in DIRECTED_CASES.values()
    }

    if actual_bins != expected_bins:
        raise ValueError("Directed targets must cover exactly H01..H20")

    for test_id, case in DIRECTED_CASES.items():
        expected_bin = f"H{int(test_id[1:]):02d}"

        if case.target_bin != expected_bin:
            raise ValueError(
                f"{test_id} must map to {expected_bin}, "
                f"got {case.target_bin}"
            )

        if not case.words:
            raise ValueError(f"{test_id} has an empty program")

        if case.expected_accepted <= 0:
            raise ValueError(
                f"{test_id}: expected_accepted must be positive"
            )


validate_directed_cases()
