from research.week5.impl.directed_cases import (
    DIRECTED_CASES,
    validate_directed_cases,
)
from research.week5.impl.rv32_encode import (
    OP_IMM,
    OP_LOAD,
)


def test_exactly_20_directed_cases():
    assert len(DIRECTED_CASES) == 20


def test_exact_t01_t20_set():
    assert set(DIRECTED_CASES) == {
        f"T{i:02d}" for i in range(1, 21)
    }


def test_exact_h01_h20_mapping():
    for index in range(1, 21):
        test_id = f"T{index:02d}"
        assert DIRECTED_CASES[test_id].target_bin == f"H{index:02d}"


def test_global_validation():
    validate_directed_cases()


def test_t06_is_canonical_load_d1_rs1_only():
    case = DIRECTED_CASES["T06"]

    load = case.words[0]
    consumer = case.words[1]

    assert (load & 0x7F) == OP_LOAD
    assert ((load >> 7) & 0x1F) == 5

    assert (consumer & 0x7F) == OP_IMM
    assert ((consumer >> 15) & 0x1F) == 5

    assert case.oracle_stall_cycles == 1


def test_t19_load_destination_is_x0():
    case = DIRECTED_CASES["T19"]
    load = case.words[0]

    assert (load & 0x7F) == OP_LOAD
    assert ((load >> 7) & 0x1F) == 0

    # Architectural oracle: no RAW stall is required.
    assert case.oracle_stall_cycles == 0


def test_t20_raw_rs2_matches_load_rd_but_consumer_uses_rs1_x2():
    case = DIRECTED_CASES["T20"]

    load = case.words[0]
    consumer = case.words[1]

    load_rd = (load >> 7) & 0x1F
    consumer_rs1 = (consumer >> 15) & 0x1F
    consumer_raw_rs2 = (consumer >> 20) & 0x1F

    assert load_rd == 5
    assert consumer_rs1 == 2
    assert consumer_raw_rs2 == 5

    assert (consumer & 0x7F) == OP_IMM
    assert case.oracle_stall_cycles == 0


def test_t15_target_layout():
    case = DIRECTED_CASES["T15"]

    assert len(case.words) == 4
    assert case.expected_accepted == 2
    assert case.oracle_redirect is True
