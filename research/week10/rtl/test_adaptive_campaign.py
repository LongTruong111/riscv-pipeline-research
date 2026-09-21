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


@cocotb.test()
async def test_one_epoch_adaptive_rtl_end_to_end(
    dut,
):
    """
    T10.9e-1 proof obligation:

        bandit decision
          -> uncovered-first target
          -> concrete adaptive templates
          -> deterministic 80:20 filler
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

    This test deliberately does not exercise multi-epoch live refill;
    that requires a dynamically updateable timing-oracle program view
    and belongs to T10.9e-2.
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
    # ADAPTATION / GENERATION:
    # select one arm and construct complete templates until the
    # nominal executed-instruction target is reached or exceeded.
    # ----------------------------------------------------------
    epoch_start = (
        planner.begin_epoch()
    )

    assert coordinator.active

    blocks = []

    while not planner.epoch_plan_complete:
        block = planner.build_next_block()
        blocks.append(block)

    assert blocks

    planned_executed = sum(
        block.expected_executed_instruction_count
        for block in blocks
    )

    planned_image_words = sum(
        block.image_word_count
        for block in blocks
    )

    assert (
        planned_executed
        >= E1_NOMINAL_EXECUTED
    )

    # Complete-template overshoot is allowed by the frozen protocol.
    assert (
        planned_executed
        == planner.planned_epoch_executed_instructions
    )

    # e-1 must remain wholly resident in one physical IMEM image.
    assert (
        planned_image_words
        <= IMEM_WORD_CAPACITY
    )

    program = build_static_epoch_program(
        blocks
    )

    # ----------------------------------------------------------
    # IMEM PATCH + COMMIT.
    #
    # Each block becomes live in provenance/ring state only AFTER all
    # of its image words have successfully been written.
    # ----------------------------------------------------------
    for block in blocks:
        for address, word in zip(
            block.physical_word_addresses,
            block.image_words,
        ):
            await patch_word(
                dut,
                address=address,
                word=word,
            )

        window.commit_patched_block(
            block
        )

    assert (
        window.pending_block_count
        == len(blocks)
    )

    assert (
        coordinator
        .pending_attribution_witness_count
        > 0
    )

    # Important:
    # do NOT call planner.register_block_witnesses().
    # RuntimeStreamWindow.commit_patched_block() already owns witness
    # registration.

    planner.close_planning_epoch()

    assert not planner.active
    assert coordinator.active

    # ----------------------------------------------------------
    # Independent streaming reference models.
    #
    # Timing oracle owns a separate architectural model internally.
    # The explicit architectural model below independently supplies
    # architectural evidence to L2 validation.
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

    released_block_count = 0

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

    cocotb.start_soon(
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
        # FALLING EDGE + ReadOnly
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
        # RISING EDGE + ReadOnly
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

        # ------------------------------------------------------
        # Resolve predecessor next-PC evidence before processing
        # current architectural state.
        # ------------------------------------------------------
        wall_ns = (
            time.perf_counter_ns()
            - measurement_start_ns
        )

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
        # L2 Intent classification.
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
        # EXACT OWNER OF PRUNE + BLOCK RELEASE.
        #
        # Do not call coordinator.prune_validation_state() separately.
        # ------------------------------------------------------
        released = (
            window.finalize_accepted_event(
                event
            )
        )

        if released is not None:
            released_block_count += 1

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
        "RTL did not consume the complete planned epoch: "
        f"planned={planned_executed}, "
        f"accepted={window.accepted_count}"
    )

    assert (
        coverage.executed_instructions
        == planned_executed
    )

    assert (
        released_block_count
        == len(blocks)
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
    # Every single-distance adaptive arm therefore contributes exactly
    # one new attributable target bin; A4 contributes two.
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
    # Q_new = 0 + alpha * reward
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

    # No reset occurred between execution start and epoch completion.
    assert signal_int(
        dut.reset
    ) == 0
