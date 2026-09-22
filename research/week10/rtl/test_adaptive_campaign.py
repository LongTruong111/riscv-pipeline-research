from __future__ import annotations

import math
import time
from random import Random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import (
    FallingEdge,
    ReadOnly,
    RisingEdge,
    Timer,
)

from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week5.impl.coverage_model import (
    L2CoverageCollector,
)
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week9.benchmark.streaming_timing import (
    StreamingTimingOracleV1,
)
from research.week10.adaptive.mutable_timing_oracle import (
    BoundedMutableTimingOracleV1,
)
from research.week10.adaptive.reward_engine import (
    attribution_targets_for,
)
from research.week9.coverage_collector import (
    CoverageCollector,
)
from research.week10.adaptive.campaign_runner import (
    AcceptedStreamTracker,
    AdaptiveEpochStreamPlanner,
    BoundedProgramRing,
    IMEM_WORD_CAPACITY,
    RuntimeStreamWindow,
)
from research.week10.adaptive.decision_engine import (
    BanditConfig,
    BanditDecisionEngine,
)
from research.week10.adaptive.epoch_coordinator import (
    AdaptiveEpochCoordinator,
)
from research.week10.adaptive.filler_policy import (
    CampaignFillerScheduler,
)
from research.week10.adaptive.register_policy import (
    RegisterTargetPolicy,
)
from research.week10.adaptive.template_realizer import (
    TemplateRealizer,
)
from research.week10.l2_live_coordinator import (
    L2LiveCoordinator,
)


CLOCK_NS = 10

# Integration-gate size only.
#
# This is deliberately much smaller than the frozen engineering gate
# of 5000 executed instructions.
E1_NOMINAL_EXECUTED = 24

# Test-local deterministic RNG partition.
#
# These constants do NOT define the final campaign seed protocol.
E1_DECISION_SEED = 10101
E1_TARGET_SEED = 20202
E1_REALIZATION_SEED = 30303

E1_EPSILON = 0.10
E1_ALPHA = 0.30
E1_Q_FLOOR = 0.05
# Multi-epoch integration gate.
#
# Two 24-instruction nominal epochs remain comfortably below the
# 128-word physical IMEM boundary even for the largest A7 stream shape.
E2_EPOCH_COUNT = 2

INSTRUCTION_BYTES = 4
MAX_PATCH_ADDRESS = 508


def signal_int(signal) -> int:
    return int(signal.value)


async def patch_word(
    dut,
    *,
    address: int,
    word: int,
) -> None:
    """
    Write one RV32 word through the Week-10 verification-only
    instruction-memory backdoor.
    """
    if (
        isinstance(address, bool)
        or not isinstance(address, int)
        or address < 0
    ):
        raise ValueError(
            "address must be a non-negative integer"
        )

    if address % INSTRUCTION_BYTES != 0:
        raise ValueError(
            "address must be 4-byte aligned"
        )

    if address > MAX_PATCH_ADDRESS:
        raise ValueError(
            "word exceeds 9-bit executable PC window"
        )

    if (
        isinstance(word, bool)
        or not isinstance(word, int)
        or not 0 <= word <= 0xFFFFFFFF
    ):
        raise ValueError(
            "word must fit 32 bits"
        )

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = address
    dut.imem_patch_data.value = word

    await Timer(
        1,
        units="ns",
    )

    dut.imem_patch_strobe.value = 1

    await Timer(
        1,
        units="ns",
    )

    dut.imem_patch_strobe.value = 0

    await Timer(
        1,
        units="ns",
    )


async def reset_active_high(
    dut,
    *,
    cycles: int = 3,
) -> None:
    """
    Frozen reset protocol:
      - reset HIGH for >= 3 cycles;
      - deassert at FallingEdge;
      - settle through RisingEdge + ReadOnly.
    """
    if cycles < 3:
        raise ValueError(
            "reset must remain high for at least 3 cycles"
        )

    dut.reset.value = 1

    for _ in range(cycles):
        await RisingEdge(
            dut.clk
        )

    await FallingEdge(
        dut.clk
    )

    dut.reset.value = 0

    await RisingEdge(
        dut.clk
    )

    await ReadOnly()


def build_adaptive_stack():
    """
    Construct the complete pure-Python adaptive stack used by e-1.

    RNG streams are deliberately independent so one subsystem's draw
    count cannot silently perturb another subsystem in this integration
    gate.
    """
    l2_coverage = L2CoverageCollector()

    coverage = CoverageCollector(
        checkpoint_interval=1000,
        retain_checkpoints=False,
    )

    live = L2LiveCoordinator(
        l2_coverage=l2_coverage,
        coverage=coverage,
    )

    decision_engine = BanditDecisionEngine(
        config=BanditConfig(
            epsilon=E1_EPSILON,
            alpha=E1_ALPHA,
            q_floor=E1_Q_FLOOR,
        ),
        rng=Random(
            E1_DECISION_SEED
        ),
    )

    coordinator = AdaptiveEpochCoordinator(
        decision_engine=decision_engine,
        register_policy=RegisterTargetPolicy(
            Random(
                E1_TARGET_SEED
            )
        ),
        live_coordinator=live,
    )

    planner = AdaptiveEpochStreamPlanner(
        coordinator=coordinator,
        template_realizer=TemplateRealizer(
            Random(
                E1_REALIZATION_SEED
            )
        ),
        filler_scheduler=CampaignFillerScheduler(),
        nominal_epoch_instructions=(
            E1_NOMINAL_EXECUTED
        ),
        initial_logical_word_index=0,
        first_executed_instruction_index=1,
    )

    ring = BoundedProgramRing()

    accepted_tracker = (
        AcceptedStreamTracker(
            first_expected_instruction_index=1
        )
    )

    window = RuntimeStreamWindow(
        coordinator=coordinator,
        ring=ring,
        accepted_tracker=accepted_tracker,
    )

    return (
        l2_coverage,
        coverage,
        decision_engine,
        coordinator,
        planner,
        window,
    )


def build_static_epoch_program(
    blocks,
) -> dict[int, int]:
    """
    Convert one pre-planned e-1 epoch into the immutable program mapping
    required by StreamingTimingOracleV1.

    e-1 intentionally forbids physical wrap. Runtime wrap/refill has
    already been proven independently by T10.9d-3b.
    """
    program: dict[int, int] = {}

    image_word_count = 0

    for block in blocks:
        image_word_count += (
            block.image_word_count
        )

        for address, word in zip(
            block.physical_word_addresses,
            block.image_words,
        ):
            if address in program:
                raise AssertionError(
                    "e-1 static epoch unexpectedly wrapped "
                    "or reused a physical IMEM address"
                )

            program[address] = word

    assert image_word_count <= (
        IMEM_WORD_CAPACITY
    )

    assert len(program) == image_word_count

    assert 0 in program

    return program

def build_epoch_program_fragment(
    blocks,
) -> dict[int, int]:
    """
    Build one non-wrapping physical program fragment.

    Unlike build_static_epoch_program(), this helper does not require
    PC 0 because later adaptive epochs begin at the next physical PC.
    """
    program: dict[int, int] = {}

    for block in blocks:
        for address, word in zip(
            block.physical_word_addresses,
            block.image_words,
        ):
            if address in program:
                raise AssertionError(
                    "e-2c epoch fragment unexpectedly reused "
                    f"physical PC 0x{address:03x}"
                )

            program[address] = word

    if not program:
        raise AssertionError(
            "adaptive epoch produced an empty program fragment"
        )

    return program

async def prepare_adaptive_epoch(
    dut,
    *,
    planner,
    window,
    preseed_next_boundary: bool,
):
    """
    Plan and patch exactly one adaptive epoch while preserving the
    one-instruction EBD lookahead required by the RTL fetch pipeline.

    First epoch:
        EBD_t is created by begin_epoch(), then patched here.

    Later epochs:
        EBD_t was already preseeded and committed during preparation of
        the preceding epoch. begin_epoch() only claims its ownership.

    If preseed_next_boundary is True, EBD_(t+1) is planned, patched, and
    committed before payload_t starts executing.
    """
    if not isinstance(
        preseed_next_boundary,
        bool,
    ):
        raise TypeError(
            "preseed_next_boundary must be bool"
        )

    pending_before_begin = (
        planner.pending_boundary_delimiter
    )

    if pending_before_begin is None:
        # Initial epoch: no resident stream entry exists yet.
        assert window.pending_block_count == 0
        assert window.used_words == 0
    else:
        # Later epoch: exactly one preseeded EBD must remain resident
        # from the preceding epoch.
        assert window.pending_block_count == 1

        assert (
            window.used_words
            == pending_before_begin.image_word_count
        )

    epoch_start = planner.begin_epoch()

    active_boundary = (
        planner.active_boundary_delimiter
    )

    assert active_boundary is not None

    if pending_before_begin is not None:
        assert (
            active_boundary.stream_entry_key
            == pending_before_begin.stream_entry_key
        )

    blocks = []

    while not planner.epoch_plan_complete:
        blocks.append(
            planner.build_next_block()
        )

    assert blocks

    payload_executed = sum(
        block.expected_executed_instruction_count
        for block in blocks
    )

    planned_executed = (
        active_boundary.expected_executed_instruction_count
        + payload_executed
    )

    assert (
        planned_executed
        == planner.planned_epoch_executed_instructions
    )

    next_boundary = None

    if preseed_next_boundary:
        next_boundary = (
            planner.plan_next_boundary_delimiter()
        )

        assert (
            next_boundary.epoch_index
            == active_boundary.epoch_index + 1
        )

        assert next_boundary.witnesses == ()

    # The e-2c/d gate remains deliberately non-wrapping.
    if (
        planner.next_logical_word_index
        > IMEM_WORD_CAPACITY
    ):
        raise AssertionError(
            "T10.9e-2d exceeded the non-wrapping "
            "128-word IMEM proof boundary"
        )

    newly_patched_entries = []

    # Initial EBD has not yet been committed. For later epochs the active
    # EBD is already resident from the previous epoch and must NOT be
    # patched or committed a second time.
    if pending_before_begin is None:
        newly_patched_entries.append(
            active_boundary
        )

    newly_patched_entries.extend(
        blocks
    )

    if next_boundary is not None:
        newly_patched_entries.append(
            next_boundary
        )

    fragment = build_epoch_program_fragment(
        newly_patched_entries
    )

    patched_image_words = sum(
        entry.image_word_count
        for entry in newly_patched_entries
    )

    assert (
        len(fragment)
        == patched_image_words
    )

    for entry in newly_patched_entries:
        for address, word in zip(
            entry.physical_word_addresses,
            entry.image_words,
        ):
            await patch_word(
                dut,
                address=address,
                word=word,
            )

        window.commit_patched_block(
            entry
        )

    expected_pending_entries = (
        1
        + len(blocks)
        + (
            1
            if next_boundary is not None
            else 0
        )
    )

    assert (
        window.pending_block_count
        == expected_pending_entries
    )

    expected_resident_words = (
        active_boundary.image_word_count
        + sum(
            block.image_word_count
            for block in blocks
        )
        + (
            next_boundary.image_word_count
            if next_boundary is not None
            else 0
        )
    )

    assert (
        window.used_words
        == expected_resident_words
    )

    planner.close_planning_epoch()

    assert not planner.active

    return (
        epoch_start,
        active_boundary,
        tuple(blocks),
        planned_executed,
        patched_image_words,
        fragment,
        next_boundary,
    )

async def resume_clock_from_high_to_falling(
    dut,
    clock,
):
    """
    Restart a killed Cocotb Clock while preserving the frozen
    FallingEdge -> ReadOnly pre-edge sampling point.

    A waiter is armed before clock.start(start_high=False), avoiding
    loss of the immediate HIGH->LOW transition.
    """
    assert signal_int(
        dut.clk
    ) == 1

    async def wait_for_falling():
        await FallingEdge(
            dut.clk
        )

    falling_waiter = cocotb.start_soon(
        wait_for_falling()
    )

    # Give the waiter a simulation-time opportunity to arm while the
    # killed clock remains stable HIGH.
    await Timer(
        1,
        units="ns",
    )

    clock_task = cocotb.start_soon(
        clock.start(
            start_high=False
        )
    )

    await falling_waiter
    await ReadOnly()

    assert signal_int(
        dut.clk
    ) == 0

    return clock_task

@cocotb.test()
async def test_one_epoch_adaptive_rtl_end_to_end(
    dut,
):
    """
    T10.9e-1 proof obligation:

        bandit decision
          -> uncovered-first target
          -> EBD + concrete adaptive templates
          -> deterministic 80:20 payload filler
          -> runtime IMEM patch
          -> exact provenance registration
          -> real RTL execution
          -> accepted ExecutionEvent stream
          -> independent timing/architectural evidence
          -> L2 Intent observation
          -> exact provenance attribution
          -> epoch reward
          -> selected-arm Q update

    Exactly one adaptive epoch is executed.

    Frozen EBD accounting:

        N_epoch = 1 EBD + architecturally accepted payload

    No lookahead EBD is required because this is the final and only
    epoch of the integration gate.
    """

    # ----------------------------------------------------------
    # Verification interface initialization.
    # ----------------------------------------------------------
    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    await Timer(
        1,
        units="ns",
    )

    (
        l2_coverage,
        coverage,
        decision_engine,
        coordinator,
        planner,
        window,
    ) = build_adaptive_stack()

    # ----------------------------------------------------------
    # ADAPTATION / GENERATION / PATCH.
    #
    # Reuse the same EBD-aware preparation path as the multi-epoch
    # gate. With preseed_next_boundary=False the resulting physical
    # stream is:
    #
    #     EBD_0 + payload_0
    #
    # and nothing from a hypothetical epoch 1 is generated.
    # ----------------------------------------------------------
    (
        epoch_start,
        active_boundary,
        blocks,
        planned_executed,
        planned_image_words,
        program,
        next_boundary,
    ) = await prepare_adaptive_epoch(
        dut,
        planner=planner,
        window=window,
        preseed_next_boundary=False,
    )

    assert coordinator.active
    assert not planner.active

    assert active_boundary.epoch_index == 0

    assert (
        active_boundary.expected_executed_instruction_count
        == 1
    )

    assert next_boundary is None

    assert blocks

    payload_executed = sum(
        block.expected_executed_instruction_count
        for block in blocks
    )

    assert (
        planned_executed
        == (
            active_boundary.expected_executed_instruction_count
            + payload_executed
        )
    )

    assert (
        planned_executed
        == planner.planned_epoch_executed_instructions
        or not planner.active
    )

    assert (
        planned_executed
        >= E1_NOMINAL_EXECUTED
    )

    # Complete-template overshoot is allowed by the frozen protocol.
    assert (
        planned_executed
        >= E1_NOMINAL_EXECUTED
    )

    assert min(program) == 0

    assert (
        len(program)
        == planned_image_words
    )

    assert (
        planned_image_words
        <= IMEM_WORD_CAPACITY
    )

    assert (
        planner.next_executed_instruction_index
        == planned_executed + 1
    )

    # The complete epoch is resident before execution starts.
    assert (
        window.pending_block_count
        == 1 + len(blocks)
    )

    assert (
        window.used_words
        == planned_image_words
    )

    assert (
        coordinator
        .pending_attribution_witness_count
        > 0
    )

    # ----------------------------------------------------------
    # Independent streaming reference models.
    #
    # EBD participates in both timing and architectural streams.
    # It has no selected-arm attribution witness and therefore cannot
    # contribute to the reward numerator.
    # ----------------------------------------------------------
    timing_oracle = (
        StreamingTimingOracleV1(
            program
        )
    )

    architectural_model = (
        RV32ArchitecturalModel()
    )

    adapter = ExecutionEventAdapter()

    events_by_index = {}

    pending_next_pc = None

    released_entry_count = 0

    measurement_start_ns = (
        time.perf_counter_ns()
    )

    # ----------------------------------------------------------
    # Exactly one clock owner.
    # ----------------------------------------------------------
    clock = Clock(
        dut.clk,
        CLOCK_NS,
        units="ns",
    )

    clock_task = cocotb.start_soon(
        clock.start()
    )

    await reset_active_high(
        dut,
        cycles=3,
    )

    assert signal_int(
        dut.reset
    ) == 0

    max_cycles = (
        planned_executed * 8
        + 32
    )

    # ----------------------------------------------------------
    # RTL EXECUTION.
    # ----------------------------------------------------------
    for cycle in range(
        1,
        max_cycles + 1,
    ):
        # ------------------------------------------------------
        # FALLING EDGE + ReadOnly.
        # ------------------------------------------------------
        await FallingEdge(
            dut.clk
        )

        await ReadOnly()

        snapshot = PreEdgeSnapshot(
            cycle=cycle,
            reset=bool(
                signal_int(
                    dut.reset
                )
            ),
            stall=bool(
                signal_int(
                    dut.probe_stall
                )
            ),
            flush_redirect=bool(
                signal_int(
                    dut.probe_flush
                )
            ),
            pc=signal_int(
                dut.probe_a_pc
            ),
            instruction=signal_int(
                dut.probe_a_instr
            ),
        )

        pending = (
            adapter.observe_pre_edge(
                snapshot
            )
        )

        # ------------------------------------------------------
        # RISING EDGE + ReadOnly.
        # ------------------------------------------------------
        await RisingEdge(
            dut.clk
        )

        await ReadOnly()

        if pending is None:
            continue

        b_pc = signal_int(
            dut.probe_b_pc
        )

        b_instruction = signal_int(
            dut.probe_b_instr
        )

        assert b_pc == pending.pc, (
            "ID/EX PC does not match admitted IF/ID PC: "
            f"pending=0x{pending.pc:03x}, "
            f"observed=0x{b_pc:03x}"
        )

        assert (
            b_instruction
            == pending.instruction
        ), (
            "ID/EX instruction does not match admitted IF/ID word: "
            f"pc=0x{pending.pc:03x}, "
            f"pending=0x{pending.instruction:08x}, "
            f"observed=0x{b_instruction:08x}"
        )

        event = (
            adapter.finalize_post_edge(
                pending,
                forward_a=signal_int(
                    dut.probe_fwd_a
                ),
                forward_b=signal_int(
                    dut.probe_fwd_b
                ),
            )
        )

        # ------------------------------------------------------
        # Independent timing evidence.
        # ------------------------------------------------------
        expectation = (
            timing_oracle.observe_accept(
                event
            )
        )

        wall_ns = (
            time.perf_counter_ns()
            - measurement_start_ns
        )

        # ------------------------------------------------------
        # Resolve predecessor next-PC evidence.
        # ------------------------------------------------------
        if pending_next_pc is not None:
            (
                predecessor_id,
                predecessor_next_pc,
            ) = pending_next_pc

            coordinator.record_successor_pc(
                predecessor_instruction_id=(
                    predecessor_id
                ),
                expected_next_pc=(
                    predecessor_next_pc
                ),
                successor=event,
                cycle=cycle,
                wall_ns=wall_ns,
            )

        # ------------------------------------------------------
        # Independent architectural model.
        # ------------------------------------------------------
        architectural_step = (
            architectural_model.step(
                event
            )
        )

        coordinator.record_architectural_result(
            instruction_id=(
                event.instruction_index
            ),
            kind="pc",
            passed=(
                architectural_step.pc_match
            ),
            cycle=cycle,
            wall_ns=wall_ns,
        )

        assert architectural_step.pc_match, (
            "architectural PC mismatch: "
            f"instruction_index="
            f"{event.instruction_index}, "
            f"event_pc=0x{event.pc:03x}, "
            f"expected_pc="
            f"0x{architectural_step.expected_pc:x}"
        )

        pending_next_pc = (
            event.instruction_index,
            architectural_step.next_pc,
        )

        # ------------------------------------------------------
        # Authoritative executed-instruction accounting.
        # ------------------------------------------------------
        assert (
            event.instruction_index
            == coverage.executed_instructions + 1
        )

        coverage.record_instruction(
            instruction_id=(
                event.instruction_index
            ),
            cycle=cycle,
        )

        # ------------------------------------------------------
        # Global L2 Intent classification.
        # ------------------------------------------------------
        events_by_index[
            event.instruction_index
        ] = event

        hits = l2_coverage.observe(
            event
        )

        for hit in hits:
            producer_event = (
                events_by_index[
                    hit.producer_instruction_index
                ]
            )

            coordinator.register_l2_hit(
                hit,
                producer=producer_event,
                consumer=event,
                expectation=expectation,
                cycle=cycle,
                wall_ns=wall_ns,
            )

        # Only d1/d2 producer history is required.
        stale_event_id = (
            event.instruction_index
            - 2
        )

        if stale_event_id > 0:
            events_by_index.pop(
                stale_event_id,
                None,
            )

        # ------------------------------------------------------
        # Exact owner of witness pruning + StreamEntry release.
        # ------------------------------------------------------
        released = (
            window.finalize_accepted_event(
                event
            )
        )

        if released is not None:
            released_entry_count += 1

        assert (
            window.accepted_count
            == coverage.executed_instructions
        )

        if (
            window.accepted_count
            == planned_executed
        ):
            break

    # ----------------------------------------------------------
    # End-of-epoch execution invariants.
    # ----------------------------------------------------------
    assert (
        window.accepted_count
        == planned_executed
    ), (
        "RTL did not consume the complete EBD-aware epoch: "
        f"planned={planned_executed}, "
        f"accepted={window.accepted_count}"
    )

    assert (
        coverage.executed_instructions
        == planned_executed
    )

    # One EBD StreamEntry plus every adaptive payload block.
    assert (
        released_entry_count
        == 1 + len(blocks)
    )

    assert (
        window.pending_block_count
        == 0
    )

    assert (
        window.used_words
        == 0
    )

    assert (
        coordinator
        .pending_attribution_witness_count
        == 0
    )

    # ----------------------------------------------------------
    # Reward + bandit update.
    #
    # EBD is included in the reward denominator.
    # ----------------------------------------------------------
    completion = (
        coordinator.finish_epoch(
            actual_executed_instructions=(
                planned_executed
            )
        )
    )

    assert not coordinator.active

    assert (
        completion.start
        == epoch_start
    )

    assert (
        completion.bandit_update.arm_id
        is epoch_start.decision.arm_id
    )

    assert (
        completion.bandit_update.pull_count
        == 1
    )

    assert (
        decision_engine.epoch_index
        == 1
    )

    # Epoch starts from completely uncovered L2 Intent.
    #
    # Single-distance adaptive arms contribute one attributable target;
    # A4 contributes two. EBD contributes zero attributable targets.
    expected_new_bins = (
        2
        if epoch_start.target.is_dual
        else 1
    )

    expected_reward = (
        1000.0
        * expected_new_bins
        / planned_executed
    )

    assert math.isclose(
        completion.reward_result.reward,
        expected_reward,
        rel_tol=0.0,
        abs_tol=1e-12,
    ), (
        "attributable reward mismatch: "
        f"expected={expected_reward}, "
        f"observed="
        f"{completion.reward_result.reward}"
    )

    # Q_old = 0 at epoch zero:
    #
    # Q_new = alpha * reward
    expected_q = (
        E1_ALPHA
        * expected_reward
    )

    assert math.isclose(
        completion.bandit_update.old_q,
        0.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    )

    assert math.isclose(
        completion.bandit_update.new_q,
        expected_q,
        rel_tol=0.0,
        abs_tol=1e-12,
    ), (
        "selected-arm Q update mismatch: "
        f"expected={expected_q}, "
        f"observed="
        f"{completion.bandit_update.new_q}"
    )

    selected_state = (
        decision_engine.arm_state(
            epoch_start.decision.arm_id
        )
    )

    assert math.isclose(
        selected_state.q_value,
        expected_q,
        rel_tol=0.0,
        abs_tol=1e-12,
    )

    assert (
        selected_state.pull_count
        == 1
    )

    # At least the selected attributable target(s) must exist globally.
    assert (
        l2_coverage.intent_bins
        >= expected_new_bins
    )

    assert (
        window.accepted_count
        == coverage.executed_instructions
    )

    assert (
        planner.next_executed_instruction_index
        == coverage.executed_instructions + 1
    )

    # No reset occurred between execution start and epoch completion.
    assert signal_int(
        dut.reset
    ) == 0

    clock_task.kill()

    assert clock_task.done()

@cocotb.test()
async def test_multi_epoch_adaptive_rtl_continuity(
    dut,
):
    """
    T10.9e-2c proof obligation:

        epoch 1 RTL execution
          -> attributable reward
          -> Q update
          -> pause sole clock owner
          -> begin epoch 2 from retained coverage/Q state
          -> runtime patch without reset
          -> mutable timing-oracle append
          -> resume same clock phase
          -> continuous ExecutionEvent numbering
          -> continuous architectural/L2 state
          -> second reward/Q update

    This gate deliberately remains below the 128-word physical IMEM
    wrap boundary. Wrap-aware adaptive campaigns are a later gate.
    """

    # ----------------------------------------------------------
    # Static verification-interface initialization.
    # ----------------------------------------------------------
    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    await Timer(
        1,
        units="ns",
    )

    (
        l2_coverage,
        coverage,
        decision_engine,
        coordinator,
        planner,
        window,
    ) = build_adaptive_stack()

    # ----------------------------------------------------------
    # Prepare epoch 1 before the clock starts.
    # ----------------------------------------------------------
    (
        current_start,
        current_boundary,
        current_blocks,
        current_planned_executed,
        current_image_words,
        first_fragment,
        current_next_boundary,
    ) = await prepare_adaptive_epoch(
        dut,
        planner=planner,
        window=window,
        preseed_next_boundary=(
            E2_EPOCH_COUNT > 1
        ),
    )
    assert current_boundary.epoch_index == 0

    assert current_next_boundary is not None

    assert (
        current_next_boundary.epoch_index
        == 1
    )
    assert (
        min(first_fragment)
        == 0
    )

    timing_oracle = (
        BoundedMutableTimingOracleV1(
            first_fragment
        )
    )

    assert (
        timing_oracle.program_word_count
        == current_image_words
    )

    architectural_model = (
        RV32ArchitecturalModel()
    )

    adapter = ExecutionEventAdapter()

    # Must remain live across epoch boundaries.
    events_by_index = {}
    pending_next_pc = None

    cycle = 0

    total_image_words = (
        current_image_words
    )

    previous_epoch_snapshot = None

    expected_pull_counts = {}

    measurement_start_ns = (
        time.perf_counter_ns()
    )

    # ----------------------------------------------------------
    # Exactly one live clock owner.
    # ----------------------------------------------------------
    clock = Clock(
        dut.clk,
        CLOCK_NS,
        units="ns",
    )

    clock_task = cocotb.start_soon(
        clock.start()
    )

    await reset_active_high(
        dut,
        cycles=3,
    )

    assert signal_int(
        dut.reset
    ) == 0

    # Normally an epoch begins by awaiting FallingEdge.
    #
    # After a pause/resume transition the helper already returns at
    # FallingEdge + ReadOnly, so the first iteration must consume that
    # already-reached pre-edge point instead of waiting for another.
    pre_edge_ready = False

    for epoch_number in range(
        1,
        E2_EPOCH_COUNT + 1,
    ):
        accepted_before_epoch = (
            window.accepted_count
        )

        released_this_epoch = 0

        q_values_before = (
            decision_engine.q_values()
        )

        if previous_epoch_snapshot is not None:
            assert (
                previous_epoch_snapshot
                <= current_start.covered_at_epoch_start
            )

        previous_epoch_snapshot = (
            current_start.covered_at_epoch_start
        )

        # Independent expected reward target:
        # only bins attributable to this selected arm/target and not
        # already globally covered at epoch start may contribute.
        attributable_targets = (
            attribution_targets_for(
                current_start.decision.arm_id,
                current_start.target,
            )
        )

        expected_new_target_bins = (
            attributable_targets
            - current_start.covered_at_epoch_start
        )

        assert expected_new_target_bins

        epoch_cycle_budget = (
            current_planned_executed
            * 8
            + 32
        )

        epoch_cycles = 0

        while (
            window.accepted_count
            - accepted_before_epoch
            < current_planned_executed
        ):
            if epoch_cycles >= epoch_cycle_budget:
                raise AssertionError(
                    "multi-epoch RTL execution exceeded "
                    "the bounded cycle budget"
                )

            # --------------------------------------------------
            # FALLING EDGE + ReadOnly.
            # --------------------------------------------------
            if pre_edge_ready:
                pre_edge_ready = False
            else:
                await FallingEdge(
                    dut.clk
                )

                await ReadOnly()

            cycle += 1
            epoch_cycles += 1

            snapshot = PreEdgeSnapshot(
                cycle=cycle,
                reset=bool(
                    signal_int(
                        dut.reset
                    )
                ),
                stall=bool(
                    signal_int(
                        dut.probe_stall
                    )
                ),
                flush_redirect=bool(
                    signal_int(
                        dut.probe_flush
                    )
                ),
                pc=signal_int(
                    dut.probe_a_pc
                ),
                instruction=signal_int(
                    dut.probe_a_instr
                ),
            )

            pending = (
                adapter.observe_pre_edge(
                    snapshot
                )
            )

            # --------------------------------------------------
            # RISING EDGE + ReadOnly.
            # --------------------------------------------------
            await RisingEdge(
                dut.clk
            )

            await ReadOnly()

            if pending is None:
                continue

            assert (
                signal_int(
                    dut.probe_b_pc
                )
                == pending.pc
            )

            assert (
                signal_int(
                    dut.probe_b_instr
                )
                == pending.instruction
            )

            event = (
                adapter.finalize_post_edge(
                    pending,
                    forward_a=signal_int(
                        dut.probe_fwd_a
                    ),
                    forward_b=signal_int(
                        dut.probe_fwd_b
                    ),
                )
            )

            # ----------------------------------------------
            # Timing state is continuous across epochs.
            # ----------------------------------------------
            expectation = (
                timing_oracle.observe_accept(
                    event
                )
            )

            wall_ns = (
                time.perf_counter_ns()
                - measurement_start_ns
            )

            # ----------------------------------------------
            # Resolve previous instruction's next-PC evidence.
            #
            # pending_next_pc is intentionally NOT cleared at
            # epoch boundaries, proving cross-epoch architectural
            # continuity.
            # ----------------------------------------------
            if pending_next_pc is not None:
                (
                    predecessor_id,
                    predecessor_next_pc,
                ) = pending_next_pc

                coordinator.record_successor_pc(
                    predecessor_instruction_id=(
                        predecessor_id
                    ),
                    expected_next_pc=(
                        predecessor_next_pc
                    ),
                    successor=event,
                    cycle=cycle,
                    wall_ns=wall_ns,
                )

            architectural_step = (
                architectural_model.step(
                    event
                )
            )

            coordinator.record_architectural_result(
                instruction_id=(
                    event.instruction_index
                ),
                kind="pc",
                passed=(
                    architectural_step.pc_match
                ),
                cycle=cycle,
                wall_ns=wall_ns,
            )

            assert (
                architectural_step.pc_match
            )

            pending_next_pc = (
                event.instruction_index,
                architectural_step.next_pc,
            )

            # ----------------------------------------------
            # Global accepted-instruction accounting is never
            # reset at an epoch boundary.
            # ----------------------------------------------
            assert (
                event.instruction_index
                == coverage.executed_instructions + 1
            )

            coverage.record_instruction(
                instruction_id=(
                    event.instruction_index
                ),
                cycle=cycle,
            )

            # ----------------------------------------------
            # Global L2 dependency state is also continuous.
            # ----------------------------------------------
            events_by_index[
                event.instruction_index
            ] = event

            hits = l2_coverage.observe(
                event
            )

            for hit in hits:
                producer_event = (
                    events_by_index[
                        hit.producer_instruction_index
                    ]
                )

                coordinator.register_l2_hit(
                    hit,
                    producer=producer_event,
                    consumer=event,
                    expectation=expectation,
                    cycle=cycle,
                    wall_ns=wall_ns,
                )

            stale_event_id = (
                event.instruction_index
                - 2
            )

            if stale_event_id > 0:
                events_by_index.pop(
                    stale_event_id,
                    None,
                )

            # Only RuntimeStreamWindow owns final pruning.
            released = (
                window.finalize_accepted_event(
                    event
                )
            )

            if released is not None:
                released_this_epoch += 1

            assert (
                window.accepted_count
                == coverage.executed_instructions
            )

        # ------------------------------------------------------
        # Exact complete-template epoch boundary.
        # ------------------------------------------------------
        actual_executed = (
            window.accepted_count
            - accepted_before_epoch
        )

        assert (
            actual_executed
            == current_planned_executed
        )

        assert (
            released_this_epoch
            == (
                1
                + len(current_blocks)
            )
        )

        if (
            epoch_number
            < E2_EPOCH_COUNT
        ):
            assert (
                current_next_boundary
                is not None
            )

            assert (
                window.pending_block_count
                == 1
            )

            assert (
                window.used_words
                == current_next_boundary.image_word_count
            )
        else:
            assert (
                current_next_boundary
                is None
            )

            assert (
                window.pending_block_count
                == 0
            )

            assert window.used_words == 0
        assert (
            coordinator
            .pending_attribution_witness_count
            == 0
        )

        completion = (
            coordinator.finish_epoch(
                actual_executed_instructions=(
                    actual_executed
                )
            )
        )

        assert (
            completion.start
            == current_start
        )

        assert (
            completion.bandit_update.arm_id
            is current_start.decision.arm_id
        )

        selected_arm = (
            current_start.decision.arm_id
        )

        expected_pull_counts[
            selected_arm
        ] = (
            expected_pull_counts.get(
                selected_arm,
                0,
            )
            + 1
        )

        assert (
            completion.bandit_update.pull_count
            == expected_pull_counts[
                selected_arm
            ]
        )

        assert (
            decision_engine.epoch_index
            == epoch_number
        )

        expected_reward = (
            1000.0
            * len(
                expected_new_target_bins
            )
            / actual_executed
        )

        assert math.isclose(
            completion.reward_result.reward,
            expected_reward,
            rel_tol=0.0,
            abs_tol=1e-12,
        ), (
            "multi-epoch attributable reward mismatch: "
            f"epoch={epoch_number}, "
            f"expected={expected_reward}, "
            f"observed="
            f"{completion.reward_result.reward}"
        )

        old_q = q_values_before[
            selected_arm
        ]

        expected_q = (
            old_q
            + E1_ALPHA
            * (
                expected_reward
                - old_q
            )
        )

        assert math.isclose(
            completion.bandit_update.old_q,
            old_q,
            rel_tol=0.0,
            abs_tol=1e-12,
        )

        assert math.isclose(
            completion.bandit_update.new_q,
            expected_q,
            rel_tol=0.0,
            abs_tol=1e-12,
        )

        q_values_after = (
            decision_engine.q_values()
        )

        for arm_id, q_before in (
            q_values_before.items()
        ):
            if arm_id is selected_arm:
                assert math.isclose(
                    q_values_after[
                        arm_id
                    ],
                    expected_q,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
            else:
                assert (
                    q_values_after[
                        arm_id
                    ]
                    == q_before
                )

        # ------------------------------------------------------
        # Final epoch: stop here.
        # ------------------------------------------------------
        if (
            epoch_number
            == E2_EPOCH_COUNT
        ):
            clock_task.kill()

            assert (
                clock_task.done()
            )

            break

        # ------------------------------------------------------
        # Epoch transition synchronization.
        #
        # We are currently at RisingEdge + ReadOnly, therefore clk is
        # HIGH. Kill the sole owner before any Timer-based patching.
        # ------------------------------------------------------
        clock_task.kill()

        assert (
            clock_task.done()
        )

        assert signal_int(
            dut.clk
        ) == 1

        assert not coordinator.active
        assert not planner.active

        assert (
            current_next_boundary
            is not None
        )

        expected_boundary_pc = (
            current_next_boundary
            .expected_executed_pcs[0]
        )

        expected_boundary_word = (
            current_next_boundary
            .expected_executed_words[0]
        )

        assert (
            signal_int(
                dut.probe_a_pc
            )
            == expected_boundary_pc
        ), (
            "preseeded EBD was not latched into stage A: "
            f"expected_pc=0x{expected_boundary_pc:03x}, "
            f"observed_pc="
            f"0x{signal_int(dut.probe_a_pc):03x}"
        )

        assert (
            signal_int(
                dut.probe_a_instr
            )
            == expected_boundary_word
        ), (
            "preseeded EBD word mismatch in stage A: "
            f"expected=0x{expected_boundary_word:08x}, "
            f"observed="
            f"0x{signal_int(dut.probe_a_instr):08x}"
        )
        # We arrived here from RisingEdge + ReadOnly.
        #
        # Cocotb forbids signal writes while still in the read-only phase.
        # Advance simulation time with the clock task killed so that:
        #   - clk remains HIGH;
        #   - no architectural edge occurs;
        #   - runtime IMEM patch writes become legal.
        await Timer(
            1,
            units="ns",
        )

        assert signal_int(
            dut.clk
        ) == 1

        assert signal_int(
            dut.reset
        ) == 0

        (
            current_start,
            current_boundary,
            current_blocks,
            current_planned_executed,
            current_image_words,
            next_fragment,
            current_next_boundary,
        ) = await prepare_adaptive_epoch(
            dut,
            planner=planner,
            window=window,
            preseed_next_boundary=(
                epoch_number + 1
                < E2_EPOCH_COUNT
            ),
        )
        first_next_pc = min(
            next_fragment
        )

        total_image_words += (
            current_image_words
        )

        assert (
            current_boundary.stream_entry_key
            == (
                "EBD",
                epoch_number,
            )
        )

        assert (
            total_image_words
            <= IMEM_WORD_CAPACITY
        )

        # Timing oracle state is NOT reconstructed.
        timing_oracle.append_program(
            next_fragment
        )
        assert (
            timing_oracle.program_word_count
            == total_image_words
        )

        # DUT reset must remain deasserted during the complete transition.
        assert signal_int(
            dut.reset
        ) == 0

        # ------------------------------------------------------
        # Arm a FallingEdge waiter first, then restart the clock from
        # HIGH using start_high=False.
        # ------------------------------------------------------
        clock_task = (
            await resume_clock_from_high_to_falling(
                dut,
                clock,
            )
        )

        # The helper already returned at FallingEdge + ReadOnly.
        pre_edge_ready = True
    # ----------------------------------------------------------
    # Campaign-level continuity invariants.
    # ----------------------------------------------------------

    assert (
        decision_engine.epoch_index
        == E2_EPOCH_COUNT
    )

    assert (
        timing_oracle.generated_count
        == coverage.executed_instructions
    )

    assert (
        window.accepted_count
        == coverage.executed_instructions
    )

    assert (
        planner.next_executed_instruction_index
        == coverage.executed_instructions + 1
    )

    assert (
        window.pending_block_count
        == 0
    )

    assert (
        window.used_words
        == 0
    )

    assert (
        coordinator
        .pending_attribution_witness_count
        == 0
    )

    assert signal_int(
        dut.reset
    ) == 0
