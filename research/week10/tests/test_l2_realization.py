from research.week5.impl.coverage_model import (
    L2CoverageCollector,
    L2Hit,
    l2_bin_index,
)
from research.week5.impl.execution_event import ExecutionEvent
from research.week6.expected_retire import ExpectedRetire
from research.week7.timing_oracle_v1 import TimingExpectationV1
from research.week10.l2_realization import (
    L2ValidatedCoverageChecker,
    check_l2_source_control,
    successor_pc_pass,
)


def event(
    instruction_id,
    *,
    pc=None,
    rs1=0,
    rs2=0,
    rd=0,
    uses_rs1=False,
    uses_rs2=False,
    writes_rd=False,
    producer_type="ALU_RESULT",
    consumer_type="ALU",
    stall=0,
    fwd_a=0,
    fwd_b=0,
):
    if pc is None:
        pc = ((instruction_id - 1) * 4) & 0x1FC

    return ExecutionEvent(
        instruction_index=instruction_id,
        cycle=instruction_id,
        pc=pc,
        instruction=0x00000013,
        rs1=rs1,
        rs2=rs2,
        rd=rd,
        uses_rs1=uses_rs1,
        uses_rs2=uses_rs2,
        writes_rd=writes_rd,
        producer_type=producer_type,
        consumer_type=consumer_type,
        stall_cycles_before_accept=stall,
        forward_a=fwd_a,
        forward_b=fwd_b,
    )


def expectation(
    consumer,
    *,
    source_a=None,
    source_b=None,
    stall=None,
    fwd_a=None,
    fwd_b=None,
    retire_cycle=None,
):
    if stall is None:
        stall = consumer.stall_cycles_before_accept
    if fwd_a is None:
        fwd_a = consumer.forward_a
    if fwd_b is None:
        fwd_b = consumer.forward_b
    if retire_cycle is None:
        retire_cycle = consumer.cycle + 3

    return TimingExpectationV1(
        instruction_id=consumer.instruction_index,
        pc=consumer.pc,
        instruction=consumer.instruction,
        mnemonic="ADD",
        accept_cycle=consumer.cycle,
        stall_cycles_before_accept=stall,
        retire_cycle=retire_cycle,
        forward_a=fwd_a,
        forward_b=fwd_b,
        source_a_producer_id=source_a,
        source_b_producer_id=source_b,
        source_a_cycle_age=None,
        source_b_cycle_age=None,
        redirect=False,
        redirect_bubbles=0,
    )


def make_hit(
    producer_id,
    consumer_id,
    distance,
    register,
):
    return L2Hit(
        bin_index=l2_bin_index(distance, register),
        distance=distance,
        register=register,
        producer_instruction_index=producer_id,
        consumer_instruction_index=consumer_id,
        producer_type="ALU_RESULT",
        consumer_type="ALU",
    )


def record(
    checker,
    instruction_id,
    *,
    pc=True,
    store=True,
    writeback=True,
    next_pc=True,
    x0=None,
):
    outcomes = []

    for kind, passed in (
        ("pc", pc),
        ("store", store),
        ("writeback", writeback),
        ("next_pc", next_pc),
    ):
        outcomes.extend(
            checker.record_architectural_result(
                instruction_id=instruction_id,
                kind=kind,
                passed=passed,
            )
        )

    if x0 is not None:
        outcomes.extend(
            checker.record_architectural_result(
                instruction_id=instruction_id,
                kind="x0",
                passed=x0,
            )
        )

    return tuple(outcomes)


def standard_pair(
    *,
    register=5,
    distance=1,
    role="RS1",
    stall=0,
    forward=None,
    producer_type="ALU_RESULT",
):
    producer_id = 1
    consumer_id = producer_id + distance

    if forward is None:
        forward = 0b10 if distance == 1 else 0b01

    producer = event(
        producer_id,
        rd=register,
        writes_rd=True,
        producer_type=producer_type,
    )

    kwargs = {"stall": stall}

    if role == "RS1":
        kwargs.update(
            rs1=register,
            uses_rs1=True,
            fwd_a=forward,
        )
        source_a = producer_id
        source_b = None
    else:
        kwargs.update(
            rs2=register,
            uses_rs2=True,
            fwd_b=forward,
        )
        source_a = None
        source_b = producer_id

    consumer = event(
        consumer_id,
        **kwargs,
    )

    hit = make_hit(
        producer_id,
        consumer_id,
        distance,
        register,
    )

    exp = expectation(
        consumer,
        source_a=source_a,
        source_b=source_b,
    )

    return producer, consumer, hit, exp


def registered_checker(producer, consumer, hit, exp):
    checker = L2ValidatedCoverageChecker()

    control = check_l2_source_control(
        hit,
        consumer,
        exp,
    )

    assert control.passed

    assert checker.register_hit(
        hit,
        control=control,
        producer=producer,
        consumer=consumer,
    ) == ()

    return checker


def test_01_d1_ex_mem_dependency_passes():
    _, consumer, hit, exp = standard_pair()

    assert check_l2_source_control(
        hit,
        consumer,
        exp,
    ).passed


def test_02_d2_mem_wb_dependency_passes():
    _, consumer, hit, exp = standard_pair(
        register=6,
        distance=2,
        role="RS2",
    )

    assert check_l2_source_control(
        hit,
        consumer,
        exp,
    ).passed


def test_03_load_use_d1_passes():
    _, consumer, hit, exp = standard_pair(
        register=7,
        stall=1,
        forward=0b01,
        producer_type="MEM_DATA",
    )

    assert check_l2_source_control(
        hit,
        consumer,
        exp,
    ).passed


def test_04_wrong_forwarding_fails():
    _, consumer, hit, exp = standard_pair()

    bad = event(
        consumer.instruction_index,
        pc=consumer.pc,
        rs1=hit.register,
        uses_rs1=True,
        fwd_a=0b01,
    )

    result = check_l2_source_control(
        hit,
        bad,
        exp,
    )

    assert not result.passed


def test_05_wrong_producer_identity_fails():
    _, consumer, hit, _ = standard_pair()

    bad_exp = expectation(
        consumer,
        source_a=99,
    )

    assert not check_l2_source_control(
        hit,
        consumer,
        bad_exp,
    ).passed


def test_06_wrong_stall_fails():
    _, consumer, hit, _ = standard_pair()

    bad_exp = expectation(
        consumer,
        source_a=1,
        stall=1,
        fwd_a=consumer.forward_a,
    )

    assert not check_l2_source_control(
        hit,
        consumer,
        bad_exp,
    ).passed


def test_07_producer_arch_failure_fails():
    producer, consumer, hit, exp = standard_pair()

    checker = registered_checker(
        producer,
        consumer,
        hit,
        exp,
    )

    record(
        checker,
        producer.instruction_index,
        writeback=False,
    )

    outcomes = record(
        checker,
        consumer.instruction_index,
    )

    assert len(outcomes) == 1
    assert not outcomes[0].validated


def test_08_consumer_writeback_failure_fails():
    producer, consumer, hit, exp = standard_pair()

    checker = registered_checker(
        producer,
        consumer,
        hit,
        exp,
    )

    record(checker, producer.instruction_index)

    outcomes = record(
        checker,
        consumer.instruction_index,
        writeback=False,
    )

    assert len(outcomes) == 1
    assert not outcomes[0].validated


def test_09_consumer_store_failure_fails():
    producer, consumer, hit, exp = standard_pair()

    checker = registered_checker(
        producer,
        consumer,
        hit,
        exp,
    )

    record(checker, producer.instruction_index)

    outcomes = record(
        checker,
        consumer.instruction_index,
        store=False,
    )

    assert len(outcomes) == 1
    assert not outcomes[0].validated


def test_10_producer_next_pc_failure_fails():
    producer, consumer, hit, exp = standard_pair()

    checker = registered_checker(
        producer,
        consumer,
        hit,
        exp,
    )

    record(
        checker,
        producer.instruction_index,
        next_pc=False,
    )

    outcomes = record(
        checker,
        consumer.instruction_index,
    )

    assert len(outcomes) == 1
    assert not outcomes[0].validated


def test_11_consumer_next_pc_failure_fails():
    producer, consumer, hit, exp = standard_pair()

    checker = registered_checker(
        producer,
        consumer,
        hit,
        exp,
    )

    record(checker, producer.instruction_index)

    outcomes = record(
        checker,
        consumer.instruction_index,
        next_pc=False,
    )

    assert len(outcomes) == 1
    assert not outcomes[0].validated


def test_12_consumer_local_x0_failure_fails():
    producer, consumer, hit, _ = standard_pair()

    consumer = event(
        consumer.instruction_index,
        pc=consumer.pc,
        rs1=hit.register,
        uses_rs1=True,
        rd=0,
        writes_rd=True,
        fwd_a=0b10,
    )

    exp = expectation(
        consumer,
        source_a=producer.instruction_index,
    )

    checker = registered_checker(
        producer,
        consumer,
        hit,
        exp,
    )

    record(checker, producer.instruction_index)

    outcomes = record(
        checker,
        consumer.instruction_index,
        x0=False,
    )

    assert len(outcomes) == 1
    assert not outcomes[0].validated


def test_13_unrelated_x0_failure_does_not_poison():
    producer, consumer, hit, exp = standard_pair()

    checker = registered_checker(
        producer,
        consumer,
        hit,
        exp,
    )

    checker.record_architectural_result(
        instruction_id=producer.instruction_index,
        kind="x0",
        passed=False,
    )

    checker.record_architectural_result(
        instruction_id=consumer.instruction_index,
        kind="x0",
        passed=False,
    )

    record(checker, producer.instruction_index)
    outcomes = record(
        checker,
        consumer.instruction_index,
    )

    assert len(outcomes) == 1
    assert outcomes[0].validated


def test_14_simultaneous_d1_d2_validate_independently():
    p_d2 = event(1, rd=5, writes_rd=True)
    p_d1 = event(2, rd=6, writes_rd=True)

    consumer = event(
        3,
        rs1=5,
        rs2=6,
        uses_rs1=True,
        uses_rs2=True,
        fwd_a=0b01,
        fwd_b=0b10,
    )

    h_d2 = make_hit(1, 3, 2, 5)
    h_d1 = make_hit(2, 3, 1, 6)

    exp = expectation(
        consumer,
        source_a=1,
        source_b=2,
        fwd_a=0b01,
        fwd_b=0b10,
    )

    checker = L2ValidatedCoverageChecker()

    for producer, hit in (
        (p_d2, h_d2),
        (p_d1, h_d1),
    ):
        control = check_l2_source_control(
            hit,
            consumer,
            exp,
        )

        assert control.passed

        checker.register_hit(
            hit,
            control=control,
            producer=producer,
            consumer=consumer,
        )

    record(checker, 1)
    record(checker, 2)
    outcomes = record(checker, 3)

    assert len(outcomes) == 2
    assert all(item.validated for item in outcomes)


def test_15_rs1_rs2_same_dependency_checks_both_roles():
    cov = L2CoverageCollector()

    producer = event(
        1,
        rd=5,
        writes_rd=True,
    )

    consumer = event(
        2,
        rs1=5,
        rs2=5,
        uses_rs1=True,
        uses_rs2=True,
        fwd_a=0b10,
        fwd_b=0b01,
    )

    assert cov.observe(producer) == ()
    hits = cov.observe(consumer)

    assert len(hits) == 1

    exp = expectation(
        consumer,
        source_a=1,
        source_b=1,
        fwd_a=0b10,
        fwd_b=0b10,
    )

    result = check_l2_source_control(
        hits[0],
        consumer,
        exp,
    )

    assert not result.passed

    names = {
        check.name
        for check in result.checks
    }

    assert "forward_rs1" in names
    assert "forward_rs2" in names


def test_16_failed_occurrence_then_later_pass_promotes():
    cov = L2CoverageCollector()

    p1 = event(1, rd=5, writes_rd=True)
    c1 = event(
        2,
        rs1=5,
        uses_rs1=True,
        fwd_a=0b01,
    )

    cov.observe(p1)
    first = cov.observe(c1)

    assert not check_l2_source_control(
        first[0],
        c1,
        expectation(
            c1,
            source_a=1,
            fwd_a=0b10,
        ),
    ).passed

    assert cov.validated_bins == 0

    p2 = event(3, rd=5, writes_rd=True)
    c2 = event(
        4,
        rs1=5,
        uses_rs1=True,
        fwd_a=0b10,
    )

    cov.observe(p2)
    second = cov.observe(c2)

    checker = L2ValidatedCoverageChecker()

    control = check_l2_source_control(
        second[0],
        c2,
        expectation(
            c2,
            source_a=3,
            fwd_a=0b10,
        ),
    )

    checker.register_hit(
        second[0],
        control=control,
        producer=p2,
        consumer=c2,
    )

    record(checker, 3)
    outcomes = record(checker, 4)

    assert outcomes[0].validated

    cov.promote_validated(
        (outcomes[0].hit,)
    )

    assert cov.validated_bins == 1


def test_17_missing_successor_keeps_hit_pending():
    producer, consumer, hit, exp = standard_pair()

    checker = registered_checker(
        producer,
        consumer,
        hit,
        exp,
    )

    record(checker, producer.instruction_index)

    for kind in (
        "pc",
        "store",
        "writeback",
    ):
        checker.record_architectural_result(
            instruction_id=consumer.instruction_index,
            kind=kind,
            passed=True,
        )

    assert checker.pending_hits == 1
    assert checker.validated_hit_count == 0


def test_18_retire_timing_mismatch_does_not_invalidate():
    producer, consumer, hit, _ = standard_pair()

    exp = expectation(
        consumer,
        source_a=1,
        retire_cycle=999,
    )

    checker = registered_checker(
        producer,
        consumer,
        hit,
        exp,
    )

    record(checker, producer.instruction_index)

    outcomes = record(
        checker,
        consumer.instruction_index,
    )

    assert len(outcomes) == 1
    assert outcomes[0].validated


def test_19_pending_state_bounded_over_long_stream():
    checker = L2ValidatedCoverageChecker()

    max_cache = 0
    max_pending = 0

    for n in range(1, 1001):
        producer_id = 2 * n - 1
        consumer_id = 2 * n
        register = ((n - 1) % 31) + 1

        producer = event(
            producer_id,
            rd=register,
            writes_rd=True,
        )

        consumer = event(
            consumer_id,
            rs1=register,
            uses_rs1=True,
            fwd_a=0b10,
        )

        hit = make_hit(
            producer_id,
            consumer_id,
            1,
            register,
        )

        exp = expectation(
            consumer,
            source_a=producer_id,
            fwd_a=0b10,
        )

        checker.register_hit(
            hit,
            control=check_l2_source_control(
                hit,
                consumer,
                exp,
            ),
            producer=producer,
            consumer=consumer,
        )

        record(checker, producer_id)
        outcomes = record(
            checker,
            consumer_id,
        )

        assert len(outcomes) == 1
        assert outcomes[0].validated

        checker.prune(
            latest_instruction_id=consumer_id
        )

        max_cache = max(
            max_cache,
            checker.architectural_cache_entries,
        )

        max_pending = max(
            max_pending,
            checker.pending_hits,
        )

    assert checker.pending_hits == 0
    assert max_pending <= 1
    assert max_cache <= 6


def test_20_successor_pc_does_not_truncate_golden_pc():
    expected = ExpectedRetire(
        instruction_id=1,
        pc=0x1FC,
        instruction=0x00000013,
        next_pc=0x200,
        regwrite=False,
        rd=None,
        wdata=None,
        store_address=None,
        store_data=None,
        store_width_bytes=None,
    )

    successor = event(
        2,
        pc=0x000,
    )

    assert not successor_pc_pass(
        expected,
        successor,
    )
