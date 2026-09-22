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
from research.week10.adaptive.wrap_aware_architectural_model import (
    WrapAwareRV32ArchitecturalModel,
)
from research.week10.adaptive.wrap_aware_timing_oracle import (
    WrapAwareMutableTimingOracleV1,
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
from research.week10.adaptive.post_instruction_cut import (
    complete_post_instruction_cut,
)
from research.week10.adaptive.campaign_telemetry import (
    CampaignTelemetryRecorder,
)
from research.week10.adaptive.intra_epoch_feeder import (
    plan_next_capacity_safe_entry,
    refill_threshold_words,
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
# Six nominal adaptive epochs intentionally cross the 128-word
# physical IMEM boundary, exercising bounded slot release/reuse
# without resetting DUT, timing, architectural, coverage, or Q state.
E2_EPOCH_COUNT = 6
G2B_NOMINAL_EXECUTED = 500

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

def build_adaptive_stack(
    *,
    nominal_epoch_instructions: int = E1_NOMINAL_EXECUTED,
):
    """
    Construct the complete pure-Python adaptive stack used by the RTL
    integration gates.

    RNG streams are deliberately independent so one subsystem's draw
    count cannot silently perturb another subsystem.

    The default preserves the historical small integration-gate batch.
    Larger proof obligations, including the frozen b=500 engineering
    configuration, must request their nominal epoch size explicitly.
    """
    if (
        isinstance(nominal_epoch_instructions, bool)
        or not isinstance(
            nominal_epoch_instructions,
            int,
        )
        or nominal_epoch_instructions <= 0
    ):
        raise ValueError(
            "nominal_epoch_instructions must be positive"
        )

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
            nominal_epoch_instructions
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
    Build one bounded physical program fragment.

    Logical stream order may cross the 128-word IMEM boundary, e.g.

        logical 126 -> PC 504
        logical 127 -> PC 508
        logical 128 -> PC   0
        logical 129 -> PC   4

    A single fragment must not contain two simultaneously-live logical
    words that alias the same physical IMEM address.
    """

    program: dict[int, int] = {}

    for block in blocks:
        for address, word in zip(
            block.physical_word_addresses,
            block.image_words,
        ):
            if address in program:
                raise AssertionError(
                    "adaptive epoch fragment reused one "
                    "physical IMEM address while both logical "
                    "owners are live: "
                    f"pc=0x{address:03x}"
                )

            program[address] = word

    if not program:
        raise AssertionError(
            "adaptive epoch produced an empty program fragment"
        )

    if len(program) > IMEM_WORD_CAPACITY:
        raise AssertionError(
            "adaptive epoch fragment exceeds physical IMEM capacity"
        )

    return program

async def patch_stream_entries(
    dut,
    *,
    entries,
    window,
    timing_oracle=None,
):
    """
    Patch one contiguous group of complete runtime stream entries.

    Ordering is intentionally frozen:

        prove ownership/capacity
          -> physical RTL patch
          -> RuntimeStreamWindow commit
          -> timing-oracle append

    The helper is valid for a single refill block as well as for the
    historical whole-epoch fragment.

    It never splits a stream entry.
    """
    entries = tuple(entries)

    if not entries:
        raise ValueError(
            "entries must contain at least one stream entry"
        )

    if (
        timing_oracle is not None
        and not isinstance(
            timing_oracle,
            WrapAwareMutableTimingOracleV1,
        )
    ):
        raise TypeError(
            "timing_oracle must be "
            "WrapAwareMutableTimingOracleV1"
        )

    fragment = build_epoch_program_fragment(
        entries
    )

    patched_image_words = sum(
        entry.image_word_count
        for entry in entries
    )

    assert (
        len(fragment)
        == patched_image_words
    )

    fragment_first_logical_word = (
        entries[0].logical_word_start
    )

    expected_logical_word = (
        fragment_first_logical_word
    )

    # ----------------------------------------------------------
    # Prevalidate the complete requested patch before mutation.
    # ----------------------------------------------------------
    projected_used_words = (
        window.used_words
    )

    for entry in entries:
        assert (
            entry.logical_word_start
            == expected_logical_word
        )

        projected_used_words += (
            entry.image_word_count
        )

        assert (
            projected_used_words
            <= IMEM_WORD_CAPACITY
        )

        for offset, address in enumerate(
            entry.physical_word_addresses
        ):
            logical_word_index = (
                entry.logical_word_start
                + offset
            )

            expected_physical_pc = (
                WrapAwareMutableTimingOracleV1
                .physical_pc_for_logical_word(
                    logical_word_index
                )
            )

            assert (
                address
                == expected_physical_pc
            )

            if timing_oracle is not None:
                existing_owner = (
                    timing_oracle
                    .logical_owner_for_pc(
                        address
                    )
                )

                assert existing_owner is None, (
                    "attempted RTL patch before old timing "
                    "owner was released: "
                    f"pc=0x{address:03x}, "
                    f"new_logical_word="
                    f"{logical_word_index}, "
                    f"old_logical_word="
                    f"{existing_owner}"
                )

        expected_logical_word = (
            entry.logical_word_end_exclusive
        )

    if timing_oracle is not None:
        assert (
            timing_oracle
            .next_append_logical_word_index
            == fragment_first_logical_word
        )

    # ----------------------------------------------------------
    # Physical image first. Runtime ownership is published only
    # after the complete entry image has been written.
    # ----------------------------------------------------------
    for entry in entries:
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

    assert (
        window.used_words
        <= IMEM_WORD_CAPACITY
    )

    # ----------------------------------------------------------
    # Timing ownership follows successful RTL + runtime commit.
    # ----------------------------------------------------------
    if timing_oracle is not None:
        timing_oracle.append_program(
            fragment,
            first_logical_word_index=(
                fragment_first_logical_word
            ),
        )

        assert (
            timing_oracle.resident_word_count
            == window.used_words
        )

        assert (
            timing_oracle.resident_word_count
            <= IMEM_WORD_CAPACITY
        )

    return (
        fragment,
        patched_image_words,
    )

async def prepare_adaptive_epoch(
    dut,
    *,
    planner,
    window,
    preseed_next_boundary: bool,
    allow_physical_wrap: bool = False,
    timing_oracle=None,
):
    """
    Plan and patch exactly one adaptive epoch while preserving the
    one-instruction EBD lookahead required by the RTL fetch pipeline.

    In wrap-aware mode:

      * logical word indices remain monotonic;
      * physical PCs wrap modulo the 128-word IMEM;
      * an old physical owner must already have been released before
        that physical slot can be patched for a new logical generation;
      * the mutable timing oracle is extended only after the RTL image
        and RuntimeStreamWindow have accepted the new fragment.

    First epoch:
        EBD_t is created by begin_epoch(), then patched here.

    Later epochs:
        EBD_t was already preseeded and committed during preparation of
        the preceding epoch. begin_epoch() only claims its ownership.
    """

    if not isinstance(
        preseed_next_boundary,
        bool,
    ):
        raise TypeError(
            "preseed_next_boundary must be bool"
        )

    if not isinstance(
        allow_physical_wrap,
        bool,
    ):
        raise TypeError(
            "allow_physical_wrap must be bool"
        )

    if (
        timing_oracle is not None
        and not isinstance(
            timing_oracle,
            WrapAwareMutableTimingOracleV1,
        )
    ):
        raise TypeError(
            "timing_oracle must be "
            "WrapAwareMutableTimingOracleV1"
        )

    if (
        timing_oracle is not None
        and not allow_physical_wrap
    ):
        raise ValueError(
            "timing_oracle extension requires "
            "allow_physical_wrap=True"
        )

    pending_before_begin = (
        planner.pending_boundary_delimiter
    )

    if (
        allow_physical_wrap
        and pending_before_begin is not None
        and timing_oracle is None
    ):
        raise ValueError(
            "later wrap-aware epochs require the live timing oracle"
        )

    if pending_before_begin is None:
        assert window.pending_block_count == 0
        assert window.used_words == 0
    else:
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

    if (
        not allow_physical_wrap
        and planner.next_logical_word_index
        > IMEM_WORD_CAPACITY
    ):
        raise AssertionError(
            "non-wrapping adaptive RTL gate exceeded "
            "the 128-word IMEM proof boundary"
        )

    newly_patched_entries = []

    # For the first epoch EBD_0 is new.
    # For later epochs active_boundary was already patched/preseeded.
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

    assert newly_patched_entries

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

    fragment_first_logical_word = (
        newly_patched_entries[
            0
        ].logical_word_start
    )

    expected_logical_word = (
        fragment_first_logical_word
    )

    # ----------------------------------------------------------
    # Prove logical continuity and, in wrap-aware mode, prove that
    # every physical slot is free in the timing backing store before
    # the RTL backdoor overwrites it.
    # ----------------------------------------------------------
    for entry in newly_patched_entries:
        assert (
            entry.logical_word_start
            == expected_logical_word
        )

        for offset, address in enumerate(
            entry.physical_word_addresses
        ):
            logical_word_index = (
                entry.logical_word_start
                + offset
            )

            expected_physical_pc = (
                WrapAwareMutableTimingOracleV1
                .physical_pc_for_logical_word(
                    logical_word_index
                )
            )

            assert (
                address
                == expected_physical_pc
            )

            if timing_oracle is not None:
                existing_owner = (
                    timing_oracle
                    .logical_owner_for_pc(
                        address
                    )
                )

                assert existing_owner is None, (
                    "attempted RTL patch before old timing "
                    "owner was released: "
                    f"pc=0x{address:03x}, "
                    f"new_logical_word="
                    f"{logical_word_index}, "
                    f"old_logical_word="
                    f"{existing_owner}"
                )

        expected_logical_word = (
            entry.logical_word_end_exclusive
        )

    if timing_oracle is not None:
        assert (
            timing_oracle
            .next_append_logical_word_index
            == fragment_first_logical_word
        )

    # ----------------------------------------------------------
    # Physical RTL patch first, then RuntimeStreamWindow commit.
    # ----------------------------------------------------------
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

    assert (
        window.used_words
        <= IMEM_WORD_CAPACITY
    )

    # The first epoch constructs the oracle immediately after this
    # helper returns. Later epochs extend that same live oracle.
    if timing_oracle is not None:
        timing_oracle.append_program(
            fragment,
            first_logical_word_index=(
                fragment_first_logical_word
            ),
        )

        assert (
            timing_oracle.resident_word_count
            == window.used_words
        )

        assert (
            timing_oracle.resident_word_count
            <= IMEM_WORD_CAPACITY
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

    telemetry = CampaignTelemetryRecorder(
        seed=E1_DECISION_SEED,
        epsilon=E1_EPSILON,
        alpha=E1_ALPHA,
        q_floor=E1_Q_FLOOR,
        nominal_batch=E1_NOMINAL_EXECUTED,
        instruction_budget=planned_executed,
        retain_records=True,
    )

    coverage.checkpoint_sink = (
        lambda checkpoint: telemetry.record_checkpoint(
            checkpoint,
            epoch_index=decision_engine.epoch_index,
            decision_state=decision_engine,
        )
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
    l2_observed_count = 0

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

        def observe_l2_for_event():
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

        l2_observed_count = (
            complete_post_instruction_cut(
                observed_count=l2_observed_count,
                instruction_index=(
                    event.instruction_index
                ),
                cycle=cycle,
                coverage=coverage,
                observe_coverage=(
                    observe_l2_for_event
                ),
            )
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

    epoch_telemetry = telemetry.record_epoch(
        completion,
        decision_state=decision_engine,
    )

    assert (
        epoch_telemetry.epoch_index
        == 0
    )

    assert (
        epoch_telemetry.actual_executed_instructions
        == planned_executed
    )

    assert (
        epoch_telemetry.last_executed_instruction
        == coverage.executed_instructions
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
        l2_observed_count
        == coverage.executed_instructions
    )

    assert (
        planner.next_executed_instruction_index
        == coverage.executed_instructions + 1
    )

    telemetry_summary = telemetry.finalize(
        termination_reason="one_epoch_gate_complete",
        executed_instructions=(
            coverage.executed_instructions
        ),
        final_l1_intent_count=sum(
            state.intent_seen
            for state in coverage.l1_state.values()
        ),
        final_l1_validated_count=sum(
            state.validated_seen
            for state in coverage.l1_state.values()
        ),
        final_l2_intent_count=sum(
            state.intent_seen
            for state in coverage.l2_state.values()
        ),
        final_l2_validated_count=sum(
            state.validated_seen
            for state in coverage.l2_state.values()
        ),
        decision_state=decision_engine,
    )

    assert telemetry_summary.completed_epochs == 1

    assert (
        telemetry_summary.executed_instructions
        == coverage.executed_instructions
    )

    assert len(telemetry.epoch_records) == 1

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
    T10.9e-2e-4 wrap-aware adaptive RTL proof obligation:

        multi-epoch RTL execution
          -> continuous adaptive Q/coverage state
          -> runtime IMEM patch without DUT reset
          -> bounded physical-slot release and reuse
          -> logical instruction order remains monotonic
          -> physical fetch PC wraps modulo 512 bytes
          -> mutable timing state survives physical-PC reuse
          -> continuous ExecutionEvent numbering
          -> continuous architectural/L2 state
          -> generation-1 logical instructions execute after wrap

    The campaign intentionally crosses the frozen 128-word physical
    instruction-memory boundary while retaining at most 128 resident
    physical program words.
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
    telemetry = CampaignTelemetryRecorder(
        seed=E1_DECISION_SEED,
        epsilon=E1_EPSILON,
        alpha=E1_ALPHA,
        q_floor=E1_Q_FLOOR,
        nominal_batch=E1_NOMINAL_EXECUTED,
        instruction_budget=None,
        retain_records=True,
    )

    coverage.checkpoint_sink = (
        lambda checkpoint: telemetry.record_checkpoint(
            checkpoint,
            epoch_index=decision_engine.epoch_index,
            decision_state=decision_engine,
        )
    )

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
        allow_physical_wrap=True,
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
        WrapAwareMutableTimingOracleV1(
            first_fragment
        )
    )

    assert (
        timing_oracle.program_word_count
        == current_image_words
    )

    architectural_model = (
        WrapAwareRV32ArchitecturalModel()
    )

    adapter = ExecutionEventAdapter()

    # Must remain live across epoch boundaries.
    events_by_index = {}
    l2_observed_count = 0
    pending_next_pc = None

    cycle = 0

    total_image_words = (
        current_image_words
    )

    max_timing_resident_words = (
        timing_oracle.resident_word_count
    )

    max_executed_logical_word_index = -1

    observed_generation_one_execution = False

    positive_reward_epoch_count = 0

    assert (
        timing_oracle.next_append_logical_word_index
        == total_image_words
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

        if expected_new_target_bins:
            positive_reward_epoch_count += 1

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
            logical_owner = (
                timing_oracle
                .logical_owner_for_pc(
                    event.pc
                )
            )

            assert logical_owner is not None, (
                "accepted RTL instruction has no "
                "resident logical timing owner: "
                f"pc=0x{event.pc:03x}"
            )

            assert (
                event.pc
                == timing_oracle
                .physical_pc_for_logical_word(
                    logical_owner
                )
            )

            assert (
                timing_oracle
                .generation_for_pc(
                    event.pc
                )
                == (
                    logical_owner
                    // IMEM_WORD_CAPACITY
                )
            )

            max_executed_logical_word_index = max(
                max_executed_logical_word_index,
                logical_owner,
            )

            if (
                logical_owner
                >= IMEM_WORD_CAPACITY
            ):
                observed_generation_one_execution = True
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
            # T10.9f post-instruction consistent coverage cut.
            #
            # This state is continuous across epoch boundaries.
            # ----------------------------------------------
            def observe_l2_for_event():
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

            l2_observed_count = (
                complete_post_instruction_cut(
                    observed_count=(
                        l2_observed_count
                    ),
                    instruction_index=(
                        event.instruction_index
                    ),
                    cycle=cycle,
                    coverage=coverage,
                    observe_coverage=(
                        observe_l2_for_event
                    ),
                )
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

                released_block = (
                    released.block
                )

                timing_oracle.release_logical_words(
                    first_logical_word_index=(
                        released_block
                        .logical_word_start
                    ),
                    word_count=(
                        released_block
                        .image_word_count
                    ),
                )

                assert (
                    timing_oracle
                    .resident_word_count
                    == window.used_words
                )

                assert (
                    timing_oracle
                    .resident_word_count
                    <= IMEM_WORD_CAPACITY
                )

                for logical_word_index in range(
                    released_block.logical_word_start,
                    released_block.logical_word_end_exclusive,
                ):
                    physical_pc = (
                        timing_oracle
                        .physical_pc_for_logical_word(
                            logical_word_index
                        )
                    )

                    assert (
                        timing_oracle
                        .logical_owner_for_pc(
                            physical_pc
                        )
                        is None
                    )

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
            timing_oracle.resident_word_count
            == window.used_words
        )

        max_timing_resident_words = max(
            max_timing_resident_words,
            timing_oracle.resident_word_count,
        )

        assert (
            max_timing_resident_words
            <= IMEM_WORD_CAPACITY
        )

        assert (
            coordinator
            .pending_attribution_witness_count
            == 0
        )

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

        epoch_telemetry = telemetry.record_epoch(
            completion,
            decision_state=decision_engine,
        )

        assert (
            epoch_telemetry.epoch_index
            == epoch_number - 1
        )

        assert (
            epoch_telemetry.actual_executed_instructions
            == actual_executed
        )

        assert (
            epoch_telemetry.last_executed_instruction
            == coverage.executed_instructions
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
            telemetry_summary = telemetry.finalize(
                termination_reason=(
                    "fixed_epoch_count_reached"
                ),
                executed_instructions=(
                    coverage.executed_instructions
                ),
                final_l1_intent_count=sum(
                    state.intent_seen
                    for state in coverage.l1_state.values()
                ),
                final_l1_validated_count=sum(
                    state.validated_seen
                    for state in coverage.l1_state.values()
                ),
                final_l2_intent_count=sum(
                    state.intent_seen
                    for state in coverage.l2_state.values()
                ),
                final_l2_validated_count=sum(
                    state.validated_seen
                    for state in coverage.l2_state.values()
                ),
                decision_state=decision_engine,
            )

            assert (
                telemetry_summary.completed_epochs
                == E2_EPOCH_COUNT
            )

            assert (
                telemetry_summary.executed_instructions
                == coverage.executed_instructions
            )

            assert (
                len(telemetry.epoch_records)
                == E2_EPOCH_COUNT
            )

            assert telemetry.checkpoint_records == ()

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
            allow_physical_wrap=True,
            timing_oracle=timing_oracle,
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

        # Timing oracle state is NOT reconstructed.
        # prepare_adaptive_epoch() already appended the new logical
        # fragment after proving old physical owners had been released.
        assert (
            timing_oracle
            .next_append_logical_word_index
            == total_image_words
        )

        assert (
            timing_oracle.resident_word_count
            == window.used_words
        )

        max_timing_resident_words = max(
            max_timing_resident_words,
            timing_oracle.resident_word_count,
        )

        assert (
            max_timing_resident_words
            <= IMEM_WORD_CAPACITY
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
        l2_observed_count
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
    # ----------------------------------------------------------
    # T10.9e-2e-4 physical-wrap closure.
    # ----------------------------------------------------------

    assert (
        total_image_words
        > IMEM_WORD_CAPACITY
    ), (
        "RTL adaptive campaign did not cross "
        "the physical IMEM wrap boundary"
    )

    assert (
        planner.next_logical_word_index
        == total_image_words
    )

    assert (
        timing_oracle
        .next_append_logical_word_index
        == total_image_words
    )

    assert (
        timing_oracle
        .next_release_logical_word_index
        == total_image_words
    )

    assert observed_generation_one_execution

    assert (
        max_executed_logical_word_index
        >= IMEM_WORD_CAPACITY
    )

    assert (
        max_timing_resident_words
        <= IMEM_WORD_CAPACITY
    )

    assert (
        timing_oracle.resident_word_count
        == 0
    )

    assert window.used_words == 0

    assert window.pending_block_count == 0

    assert (
        positive_reward_epoch_count
        >= 1
    )

    assert signal_int(
        dut.reset
    ) == 0

@cocotb.test()
async def test_intra_epoch_streaming_b500(
    dut,
):
    """
    T10.9g-2b proof obligation:

        one adaptive epoch with nominal b=500
          -> complete-template planning
          -> bounded 128-word physical IMEM residency
          -> accepted execution releases FIFO stream entries
          -> released timing ownership is reclaimed
          -> clock pauses HIGH without DUT reset
          -> new logical blocks patch into released physical slots
          -> mutable timing oracle extends across physical-PC reuse
          -> logical execution crosses generation 0 -> generation 1+
          -> coverage post-instruction cut remains exact
          -> epoch closes only after the complete planned payload executes

    This is a final single epoch, therefore no EBD_(t+1) is required.
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
    ) = build_adaptive_stack(
        nominal_epoch_instructions=(
            G2B_NOMINAL_EXECUTED
        ),
    )

    # ----------------------------------------------------------
    # Begin exactly one adaptive epoch.
    #
    # begin_epoch() creates EBD_0 because this is the first epoch.
    # Unlike prepare_adaptive_epoch(), planning deliberately remains
    # active while RTL execution is in progress.
    # ----------------------------------------------------------
    epoch_start = planner.begin_epoch()

    active_boundary = (
        planner.active_boundary_delimiter
    )

    assert active_boundary is not None
    assert active_boundary.epoch_index == 0

    assert (
        active_boundary.logical_word_start
        == 0
    )

    assert (
        active_boundary
        .expected_executed_instruction_count
        == 1
    )

    assert coordinator.active
    assert planner.active

    assert (
        planner.planned_epoch_executed_instructions
        == 1
    )

    # ----------------------------------------------------------
    # Patch EBD_0 first and use it to construct the live mutable
    # timing oracle.
    # ----------------------------------------------------------
    (
        initial_fragment,
        initial_image_words,
    ) = await patch_stream_entries(
        dut,
        entries=(active_boundary,),
        window=window,
        timing_oracle=None,
    )

    assert initial_image_words == 1

    timing_oracle = (
        WrapAwareMutableTimingOracleV1(
            initial_fragment
        )
    )

    assert (
        timing_oracle.resident_word_count
        == window.used_words
    )

    total_image_words = (
        initial_image_words
    )

    max_timing_resident_words = (
        timing_oracle.resident_word_count
    )

    refill_entry_count = 0

    final_planned_executed = None

    # ----------------------------------------------------------
    # Capacity-fill helper.
    #
    # It may be called before execution starts or while the sole clock
    # owner is killed HIGH.  Every planner mutation is capacity-admitted
    # before build_next_block().
    # ----------------------------------------------------------
    async def fill_available_capacity(
        *,
        count_as_refill: bool,
    ):
        nonlocal total_image_words
        nonlocal max_timing_resident_words
        nonlocal refill_entry_count
        nonlocal final_planned_executed

        patched_entries = 0

        while planner.active:
            if planner.epoch_plan_complete:
                final_planned_executed = (
                    planner
                    .planned_epoch_executed_instructions
                )

                planner.close_planning_epoch()

                assert not planner.active

                break

            entry = (
                plan_next_capacity_safe_entry(
                    planner,
                    free_words=window.free_words,
                    preseed_next_boundary=False,
                )
            )

            if entry is None:
                break

            (
                _fragment,
                patched_image_words,
            ) = await patch_stream_entries(
                dut,
                entries=(entry,),
                window=window,
                timing_oracle=timing_oracle,
            )

            patched_entries += 1

            if count_as_refill:
                refill_entry_count += 1

            total_image_words += (
                patched_image_words
            )

            assert (
                timing_oracle.resident_word_count
                == window.used_words
            )

            assert (
                timing_oracle.resident_word_count
                <= IMEM_WORD_CAPACITY
            )

            max_timing_resident_words = max(
                max_timing_resident_words,
                timing_oracle.resident_word_count,
            )

            if planner.epoch_plan_complete:
                final_planned_executed = (
                    planner
                    .planned_epoch_executed_instructions
                )

                assert (
                    final_planned_executed
                    >= G2B_NOMINAL_EXECUTED
                )

                planner.close_planning_epoch()

                assert not planner.active

                break

        return patched_entries

    # ----------------------------------------------------------
    # Initial resident fill.
    #
    # b=500 cannot complete here because physical residency is bounded
    # to 128 words.  Planning must remain active after this fill.
    # ----------------------------------------------------------
    initial_payload_entries = (
        await fill_available_capacity(
            count_as_refill=False,
        )
    )

    assert initial_payload_entries > 0

    assert planner.active

    assert final_planned_executed is None

    assert (
        planner.planned_epoch_executed_instructions
        < G2B_NOMINAL_EXECUTED
    )

    assert (
        window.used_words
        <= IMEM_WORD_CAPACITY
    )

    assert (
        timing_oracle.resident_word_count
        == window.used_words
    )

    assert (
        timing_oracle.next_append_logical_word_index
        == total_image_words
    )

    # ----------------------------------------------------------
    # Continuous reference state.
    # ----------------------------------------------------------
    architectural_model = (
        WrapAwareRV32ArchitecturalModel()
    )

    adapter = ExecutionEventAdapter()

    events_by_index = {}

    l2_observed_count = 0

    pending_next_pc = None

    max_executed_logical_word_index = -1

    observed_generation_one_execution = False

    released_entry_count = 0

    refill_pause_count = 0

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

    # Conservative bounded-cycle guard.  Refilling consumes simulation
    # time while the clock is stopped, not architectural clock cycles.
    max_cycles = (
        G2B_NOMINAL_EXECUTED * 12
        + 256
    )

    cycle = 0

    # resume_clock_from_high_to_falling() already returns at
    # FallingEdge + ReadOnly.  This flag prevents consuming a second
    # falling edge after a refill pause.
    pre_edge_ready = False

    # ----------------------------------------------------------
    # RTL execution with intra-epoch refill.
    # ----------------------------------------------------------
    while True:
        if cycle >= max_cycles:
            raise AssertionError(
                "b=500 intra-epoch RTL execution exceeded "
                "the bounded cycle budget"
            )

        # ------------------------------------------------------
        # FALLING EDGE + ReadOnly.
        # ------------------------------------------------------
        if pre_edge_ready:
            pre_edge_ready = False
        else:
            await FallingEdge(
                dut.clk
            )

            await ReadOnly()

        cycle += 1

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

        # ------------------------------------------------------
        # Wrap-aware timing ownership.
        # ------------------------------------------------------
        logical_owner = (
            timing_oracle
            .logical_owner_for_pc(
                event.pc
            )
        )

        assert logical_owner is not None, (
            "accepted b=500 RTL instruction has no "
            "resident logical timing owner: "
            f"pc=0x{event.pc:03x}"
        )

        assert (
            event.pc
            == timing_oracle
            .physical_pc_for_logical_word(
                logical_owner
            )
        )

        assert (
            timing_oracle
            .generation_for_pc(
                event.pc
            )
            == (
                logical_owner
                // IMEM_WORD_CAPACITY
            )
        )

        max_executed_logical_word_index = max(
            max_executed_logical_word_index,
            logical_owner,
        )

        if (
            logical_owner
            >= IMEM_WORD_CAPACITY
        ):
            observed_generation_one_execution = True

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
        # Independent wrap-aware architectural model.
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

        assert architectural_step.pc_match

        pending_next_pc = (
            event.instruction_index,
            architectural_step.next_pc,
        )

        # ------------------------------------------------------
        # Post-instruction consistent coverage cut.
        # ------------------------------------------------------
        def observe_l2_for_event():
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

        l2_observed_count = (
            complete_post_instruction_cut(
                observed_count=(
                    l2_observed_count
                ),
                instruction_index=(
                    event.instruction_index
                ),
                cycle=cycle,
                coverage=coverage,
                observe_coverage=(
                    observe_l2_for_event
                ),
            )
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

        # ------------------------------------------------------
        # RuntimeStreamWindow is the sole final prune/release owner.
        # ------------------------------------------------------
        released = (
            window.finalize_accepted_event(
                event
            )
        )

        if released is not None:
            released_entry_count += 1

            released_block = (
                released.block
            )

            timing_oracle.release_logical_words(
                first_logical_word_index=(
                    released_block
                    .logical_word_start
                ),
                word_count=(
                    released_block
                    .image_word_count
                ),
            )

            assert (
                timing_oracle.resident_word_count
                == window.used_words
            )

            assert (
                timing_oracle.resident_word_count
                <= IMEM_WORD_CAPACITY
            )

            for logical_word_index in range(
                released_block.logical_word_start,
                released_block.logical_word_end_exclusive,
            ):
                physical_pc = (
                    timing_oracle
                    .physical_pc_for_logical_word(
                        logical_word_index
                    )
                )

                assert (
                    timing_oracle
                    .logical_owner_for_pc(
                        physical_pc
                    )
                    is None
                )

            # --------------------------------------------------
            # Intra-epoch refill.
            #
            # Capacity must be available before planning mutates.
            # Refilling happens only after coverage + runtime release.
            # --------------------------------------------------
            if (
                planner.active
                and window.free_words
                >= refill_threshold_words(
                    preseed_next_boundary=False
                )
            ):
                # We are at RisingEdge + ReadOnly with clk HIGH.
                clock_task.kill()

                assert clock_task.done()

                assert signal_int(
                    dut.clk
                ) == 1

                # Exit the read-only phase without creating an
                # architectural edge.
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

                patched_now = (
                    await fill_available_capacity(
                        count_as_refill=True,
                    )
                )

                assert patched_now > 0

                refill_pause_count += 1

                assert (
                    timing_oracle
                    .resident_word_count
                    == window.used_words
                )

                assert (
                    timing_oracle
                    .resident_word_count
                    <= IMEM_WORD_CAPACITY
                )

                assert (
                    timing_oracle
                    .next_append_logical_word_index
                    == total_image_words
                )

                clock_task = (
                    await resume_clock_from_high_to_falling(
                        dut,
                        clock,
                    )
                )

                pre_edge_ready = True

        assert (
            window.accepted_count
            == coverage.executed_instructions
        )

        # ------------------------------------------------------
        # Stop exactly after the final planned accepted instruction.
        # ------------------------------------------------------
        if (
            final_planned_executed is not None
            and window.accepted_count
            == final_planned_executed
        ):
            break

    # ----------------------------------------------------------
    # Stop the sole clock owner at the final RisingEdge.
    # ----------------------------------------------------------
    clock_task.kill()

    assert clock_task.done()

    assert signal_int(
        dut.clk
    ) == 1

    assert signal_int(
        dut.reset
    ) == 0

    # ----------------------------------------------------------
    # Final bounded-stream proof obligations.
    # ----------------------------------------------------------
    assert final_planned_executed is not None

    actual_executed = (
        window.accepted_count
    )

    assert (
        actual_executed
        == final_planned_executed
    )

    assert (
        actual_executed
        >= G2B_NOMINAL_EXECUTED
    )

    assert (
        coverage.executed_instructions
        == actual_executed
    )

    assert not planner.active

    assert (
        planner.pending_boundary_delimiter
        is None
    )

    assert (
        planner.next_executed_instruction_index
        == actual_executed + 1
    )

    assert (
        planner.next_logical_word_index
        == total_image_words
    )

    # Logical image must greatly exceed the physical 128-word IMEM.
    assert (
        total_image_words
        > IMEM_WORD_CAPACITY
    )

    assert (
        max_timing_resident_words
        <= IMEM_WORD_CAPACITY
    )

    assert refill_pause_count > 0
    assert refill_entry_count > 0

    # Physical-PC generation reuse must have been observed by RTL.
    assert observed_generation_one_execution

    assert (
        max_executed_logical_word_index
        >= IMEM_WORD_CAPACITY
    )

    # Every final stream entry must have completed and been reclaimed.
    assert released_entry_count > 0

    assert (
        window.pending_block_count
        == 0
    )

    assert window.used_words == 0

    assert (
        timing_oracle.resident_word_count
        == 0
    )

    assert (
        timing_oracle.next_append_logical_word_index
        == total_image_words
    )

    assert (
        timing_oracle.next_release_logical_word_index
        == total_image_words
    )

    assert (
        coordinator
        .pending_attribution_witness_count
        == 0
    )

    # ----------------------------------------------------------
    # Close the adaptive feedback epoch only after all accepted
    # execution has completed.
    # ----------------------------------------------------------
    completion = (
        coordinator.finish_epoch(
            actual_executed_instructions=(
                actual_executed
            )
        )
    )

    assert (
        completion.start
        == epoch_start
    )

    assert (
        completion
        .reward_result
        .actual_executed_instructions
        == actual_executed
    )

    assert (
        completion.bandit_update.arm_id
        is epoch_start.decision.arm_id
    )

    assert (
        decision_engine.epoch_index
        == 1
    )

    assert not coordinator.active

@cocotb.test()
async def test_exact_n_hard_cap_termination(
    dut,
):
    """
    T10.9h-3 proof obligation:

        exact architectural hard cap
          -> final instruction completes normal timing/architecture/L2 cut
          -> no accepted instruction beyond Nmax
          -> clock stops HIGH without reset
          -> partially consumed resident template is not fake-executed
          -> unexecuted stream suffix is discarded explicitly
          -> timing ownership is released for the same resident suffix
          -> accepted count remains exactly Nmax
          -> final partial adaptive epoch receives exactly one finish/update

    This gate deliberately terminates after the first accepted payload
    instruction, so Nmax lies strictly inside the first payload template.
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

    # Nominal size is deliberately much larger than the chosen hard cap.
    # Two payload entries therefore remain valid complete planner entries
    # while architectural execution terminates inside the first one.
    (
        l2_coverage,
        coverage,
        decision_engine,
        coordinator,
        planner,
        window,
    ) = build_adaptive_stack(
        nominal_epoch_instructions=16,
    )

    # ----------------------------------------------------------
    # Begin one adaptive epoch.
    # ----------------------------------------------------------
    epoch_start = planner.begin_epoch()

    active_boundary = (
        planner.active_boundary_delimiter
    )

    assert active_boundary is not None
    assert active_boundary.epoch_index == 0

    assert (
        active_boundary
        .first_executed_instruction_index
        == 1
    )

    # ----------------------------------------------------------
    # Patch EBD_0 first and construct the live timing oracle.
    # ----------------------------------------------------------
    (
        initial_fragment,
        initial_image_words,
    ) = await patch_stream_entries(
        dut,
        entries=(active_boundary,),
        window=window,
        timing_oracle=None,
    )

    assert initial_image_words == 1

    timing_oracle = (
        WrapAwareMutableTimingOracleV1(
            initial_fragment
        )
    )

    assert (
        timing_oracle.resident_word_count
        == window.used_words
    )

    # ----------------------------------------------------------
    # Plan and patch two complete payload entries.
    #
    # Hard termination will occur inside the first entry.  The second
    # entry proves that later fully resident stream state is also
    # discarded without execution.
    # ----------------------------------------------------------
    first_payload = (
        planner.build_next_block()
    )

    second_payload = (
        planner.build_next_block()
    )

    assert (
        first_payload
        .expected_executed_instruction_count
        >= 2
    )

    assert (
        second_payload
        .expected_executed_instruction_count
        >= 2
    )

    assert planner.active

    assert not planner.epoch_plan_complete

    (
        _payload_fragment,
        patched_payload_words,
    ) = await patch_stream_entries(
        dut,
        entries=(
            first_payload,
            second_payload,
        ),
        window=window,
        timing_oracle=timing_oracle,
    )

    assert patched_payload_words == (
        first_payload.image_word_count
        + second_payload.image_word_count
    )

    assert (
        timing_oracle.resident_word_count
        == window.used_words
    )

    assert (
        timing_oracle.resident_word_count
        <= IMEM_WORD_CAPACITY
    )

    # EBD_0 is instruction 1.  Therefore the first accepted payload
    # instruction is instruction 2.
    hard_cap = (
        first_payload
        .first_executed_instruction_index
    )

    assert hard_cap == 2

    # Cutting after the first instruction must be strictly inside the
    # current payload entry.
    assert (
        hard_cap
        < (
            first_payload
            .first_executed_instruction_index
            + first_payload
            .expected_executed_instruction_count
        )
    )

    # ----------------------------------------------------------
    # Continuous reference state.
    # ----------------------------------------------------------
    architectural_model = (
        WrapAwareRV32ArchitecturalModel()
    )

    adapter = ExecutionEventAdapter()

    events_by_index = {}

    l2_observed_count = 0

    pending_next_pc = None

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

    max_cycles = 128
    cycle = 0

    hard_cap_event = None

    # ----------------------------------------------------------
    # Execute exactly through Nmax.
    # ----------------------------------------------------------
    while True:
        if cycle >= max_cycles:
            raise AssertionError(
                "exact-N RTL termination exceeded "
                "the bounded cycle budget"
            )

        # ------------------------------------------------------
        # FALLING EDGE + ReadOnly.
        # ------------------------------------------------------
        await FallingEdge(
            dut.clk
        )

        await ReadOnly()

        cycle += 1

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

        # The DUT must never architecturally accept beyond Nmax.
        assert (
            event.instruction_index
            <= hard_cap
        )

        # ------------------------------------------------------
        # Wrap-aware timing ownership.
        # ------------------------------------------------------
        logical_owner = (
            timing_oracle
            .logical_owner_for_pc(
                event.pc
            )
        )

        assert logical_owner is not None

        assert (
            event.pc
            == timing_oracle
            .physical_pc_for_logical_word(
                logical_owner
            )
        )

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
        # Independent wrap-aware architectural model.
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

        assert architectural_step.pc_match

        pending_next_pc = (
            event.instruction_index,
            architectural_step.next_pc,
        )

        # ------------------------------------------------------
        # Post-instruction consistent coverage cut.
        # ------------------------------------------------------
        def observe_l2_for_event():
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

        l2_observed_count = (
            complete_post_instruction_cut(
                observed_count=(
                    l2_observed_count
                ),
                instruction_index=(
                    event.instruction_index
                ),
                cycle=cycle,
                coverage=coverage,
                observe_coverage=(
                    observe_l2_for_event
                ),
            )
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

        # ------------------------------------------------------
        # RuntimeStreamWindow remains the sole final prune owner.
        # ------------------------------------------------------
        released = (
            window.finalize_accepted_event(
                event
            )
        )

        if released is not None:
            released_block = (
                released.block
            )

            timing_oracle.release_logical_words(
                first_logical_word_index=(
                    released_block
                    .logical_word_start
                ),
                word_count=(
                    released_block
                    .image_word_count
                ),
            )

            assert (
                timing_oracle.resident_word_count
                == window.used_words
            )

        assert (
            window.accepted_count
            == coverage.executed_instructions
        )

        assert (
            l2_observed_count
            == coverage.executed_instructions
        )

        # ------------------------------------------------------
        # Exact hard-cap boundary.
        #
        # The event at Nmax has already completed:
        #   timing
        #   architectural evidence
        #   L2 observation
        #   post-instruction cut
        #   runtime final prune
        #
        # No subsequent architectural edge is allowed.
        # ------------------------------------------------------
        if (
            event.instruction_index
            == hard_cap
        ):
            hard_cap_event = event

            # We deliberately stop inside first_payload.
            assert released is None

            break

    assert hard_cap_event is not None

    assert (
        hard_cap_event.instruction_index
        == hard_cap
    )

    assert (
        window.accepted_count
        == hard_cap
    )

    assert (
        coverage.executed_instructions
        == hard_cap
    )

    assert (
        l2_observed_count
        == hard_cap
    )

    # ----------------------------------------------------------
    # Stop sole clock owner HIGH before any next architectural edge.
    # ----------------------------------------------------------
    clock_task.kill()

    assert clock_task.done()

    assert signal_int(
        dut.clk
    ) == 1

    assert signal_int(
        dut.reset
    ) == 0

    # Exit ReadOnly without creating a clock edge.
    await Timer(
        1,
        units="ns",
    )

    assert signal_int(
        dut.clk
    ) == 1

    accepted_at_stop = (
        window.accepted_count
    )

    coverage_at_stop = (
        coverage.executed_instructions
    )

    resident_words_before_cleanup = (
        window.used_words
    )

    timing_words_before_cleanup = (
        timing_oracle.resident_word_count
    )

    assert (
        accepted_at_stop
        == hard_cap
    )

    assert (
        coverage_at_stop
        == hard_cap
    )

    assert resident_words_before_cleanup > 0

    assert (
        timing_words_before_cleanup
        == resident_words_before_cleanup
    )

    # EBD_0 must already have completed and been released.  Therefore
    # the FIFO-oldest resident logical word belongs to first_payload.
    assert (
        timing_oracle
        .next_release_logical_word_index
        == first_payload.logical_word_start
    )

    # ----------------------------------------------------------
    # Exact-N resident suffix termination.
    # ----------------------------------------------------------
    discarded = (
        window.discard_unexecuted_suffix(
            last_executed_instruction_index=(
                hard_cap
            )
        )
    )

    assert (
        discarded.entries[0]
        == first_payload
    )

    assert (
        discarded.entries[1]
        == second_payload
    )

    assert (
        discarded.first_logical_word_index
        == first_payload.logical_word_start
    )

    assert (
        discarded.reclaimed_resident_word_count
        == resident_words_before_cleanup
    )

    assert (
        discarded.first_unexecuted_instruction_index
        == hard_cap + 1
    )

    assert (
        discarded.accepted_count_at_termination
        == hard_cap
    )

    assert (
        discarded.head_accepted_instruction_count
        == 1
    )

    assert (
        discarded
        .discarded_expected_instruction_count
        >= 1
    )

    # Runtime cleanup must never fabricate execution.
    assert (
        window.accepted_count
        == accepted_at_stop
    )

    assert (
        coverage.executed_instructions
        == coverage_at_stop
    )

    assert window.pending_block_count == 0

    assert window.used_words == 0

    assert (
        coordinator
        .pending_attribution_witness_count
        == 0
    )

    # ----------------------------------------------------------
    # Mirror exactly the same reclaimed resident range into timing.
    # ----------------------------------------------------------
    timing_oracle.release_logical_words(
        first_logical_word_index=(
            discarded
            .first_logical_word_index
        ),
        word_count=(
            discarded
            .reclaimed_resident_word_count
        ),
    )

    assert (
        timing_oracle.resident_word_count
        == 0
    )

    assert (
        timing_oracle.resident_word_count
        == window.used_words
    )

    assert (
        timing_oracle
        .next_release_logical_word_index
        == timing_oracle
        .next_append_logical_word_index
    )

    # ----------------------------------------------------------
    # Keep simulated time moving while the clock is dead.
    #
    # This proves there is no hidden Nmax+1 architectural edge.
    # ----------------------------------------------------------
    await Timer(
        CLOCK_NS * 2,
        units="ns",
    )

    assert signal_int(
        dut.clk
    ) == 1

    assert signal_int(
        dut.reset
    ) == 0

    assert (
        window.accepted_count
        == hard_cap
    )

    assert (
        coverage.executed_instructions
        == hard_cap
    )

    assert (
        l2_observed_count
        == hard_cap
    )

    # ----------------------------------------------------------
    # Finalize the partial adaptive epoch exactly once.
    #
    # Epoch 0 begins at instruction 1, so its actual denominator equals
    # the global accepted count at this test's hard cap.
    # ----------------------------------------------------------
    completion = coordinator.finish_epoch(
        actual_executed_instructions=(
            hard_cap
        )
    )

    assert completion is not None

    assert (
        completion.start
        == epoch_start
    )

    assert not coordinator.active

    # No DUT reset occurred during terminal cleanup.
    assert signal_int(
        dut.reset
    ) == 0
