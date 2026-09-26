from __future__ import annotations

from collections import Counter
import time

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import (
    FallingEdge,
    ReadOnly,
    RisingEdge,
    Timer,
)

from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week10.adaptive.wrap_aware_architectural_model import (
    WrapAwareRV32ArchitecturalModel,
)
from research.week13.pure_random.runtime_stream import (
    IMEM_WORD_CAPACITY,
    PureRandomRuntimeEntry,
    PureRandomRuntimeWindow,
    PureRandomStreamExecutionMismatch,
    build_runtime_entries,
    physical_pc_for_logical_word,
)
from research.week13.pure_random.stream_planner import (
    generate_pure_random_plan,
)


CLOCK_NS = 10

REFILL_ROOT_SEED = 11001
REFILL_ACCEPTED_BUDGET = 300

REFILL_EXPECTED_PLAN_HASH = (
    "f7fa58513856649dd1bc6d7724c19f6"
    "b5a6542bf41882e0bbb18827e0099e4c5"
)

REFILL_EXPECTED_BLOCK_COUNT = 205
REFILL_EXPECTED_IMAGE_WORDS = 457
REFILL_EXPECTED_FINAL_PC = 0x120

# Maximum M1 image block size:
# control payload + two fall-through NOPs + target NOP.
REFILL_THRESHOLD_WORDS = 4

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
    Frozen Week-10 verification-only IMEM backdoor protocol.

    Caller must ensure the CPU clock cannot create an architectural
    edge while a refill patch is in progress.
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


async def resume_clock_from_high_to_falling(
    dut,
    clock,
):
    """
    Frozen Week-10 pause/resume protocol.

    Arm FallingEdge before restarting the clock so the immediate
    HIGH->LOW transition cannot be lost.
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

    # Allow the waiter to arm while clk remains frozen HIGH.
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


def resident_physical_owners(
    window: PureRandomRuntimeWindow,
) -> dict[int, int]:
    """
    Return:
        physical_pc -> resident logical word index

    No two live logical words may own the same physical IMEM slot.
    """
    owners: dict[int, int] = {}

    for entry in window.pending_entries:
        for offset, physical_pc in enumerate(
            entry.physical_word_addresses
        ):
            logical_word = (
                entry.logical_word_start
                + offset
            )

            if physical_pc in owners:
                raise AssertionError(
                    "two live logical words alias one physical slot: "
                    f"pc=0x{physical_pc:03x}, "
                    f"old={owners[physical_pc]}, "
                    f"new={logical_word}"
                )

            owners[
                physical_pc
            ] = logical_word

    assert len(owners) == window.used_words

    return owners


def assert_patch_slots_are_unowned(
    entry: PureRandomRuntimeEntry,
    window: PureRandomRuntimeWindow,
) -> None:
    """
    Prove that every physical slot about to be patched has already
    lost its previous live owner.
    """
    owners = resident_physical_owners(
        window
    )

    for offset, physical_pc in enumerate(
        entry.physical_word_addresses
    ):
        logical_word = (
            entry.logical_word_start
            + offset
        )

        assert physical_pc not in owners, (
            "attempted M1 RTL patch before old owner release: "
            f"pc=0x{physical_pc:03x}, "
            f"new_logical_word={logical_word}, "
            f"old_logical_word="
            f"{owners.get(physical_pc)}"
        )


@cocotb.test()
async def test_m1_pure_random_rtl_refill_wrap_300(
    dut,
):
    """
    W13 M1-PR live refill / physical-wrap smoke.

    Proves on canonical DUT:
      - deterministic N=300 plan;
      - >128-word logical program streams through 128-word IMEM;
      - physical slots are reused only after old ownership release;
      - clock is frozen HIGH during every runtime patch;
      - execution crosses multiple logical IMEM generations;
      - RTL accepted (PC,word) order exactly matches the frozen plan;
      - Golden architectural fetch state remains consistent;
      - exact-N termination handles a partial final block without
        fabricating post-budget execution.
    """

    # ==========================================================
    # FROZEN OFFLINE PLAN
    # ==========================================================
    plan = generate_pure_random_plan(
        REFILL_ROOT_SEED,
        REFILL_ACCEPTED_BUDGET,
    )

    entries = build_runtime_entries(
        plan
    )

    total_image_words = sum(
        entry.image_word_count
        for entry in entries
    )

    assert (
        plan.accepted_instruction_count
        == REFILL_ACCEPTED_BUDGET
    )

    assert (
        plan.plan_hash
        == REFILL_EXPECTED_PLAN_HASH
    )

    assert (
        len(plan.blocks)
        == REFILL_EXPECTED_BLOCK_COUNT
    )

    assert (
        total_image_words
        == REFILL_EXPECTED_IMAGE_WORDS
    )

    assert (
        plan.final_expected_pc
        == REFILL_EXPECTED_FINAL_PC
    )

    assert plan.blocks[-1].is_partial

    assert (
        total_image_words
        > IMEM_WORD_CAPACITY
    )

    # 457 words span logical generations 0..3.
    assert (
        (total_image_words - 1)
        // IMEM_WORD_CAPACITY
        == 3
    )

    families = Counter(
        block.realized.family.value
        for block in plan.blocks
    )

    # Exact accepted logical-word sequence. This is independent of
    # runtime residency and allows generation/wrap evidence per event.
    accepted_logical_words = tuple(
        entry.logical_word_start + offset
        for entry in entries
        for offset in (
            entry.planned_accepted_word_offsets
        )
    )

    assert (
        len(accepted_logical_words)
        == REFILL_ACCEPTED_BUDGET
    )

    assert (
        accepted_logical_words[-1]
        // IMEM_WORD_CAPACITY
        == 3
    )

    dut._log.info(
        "M1-PR refill plan "
        f"seed={REFILL_ROOT_SEED} "
        f"accepted={REFILL_ACCEPTED_BUDGET} "
        f"blocks={len(plan.blocks)} "
        f"image_words={total_image_words} "
        f"logical_generations=4 "
        f"hash={plan.plan_hash} "
        f"partial_final={plan.blocks[-1].is_partial} "
        f"families={dict(sorted(families.items()))}"
    )

    # ==========================================================
    # STATIC INTERFACE INITIALIZATION
    # ==========================================================
    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    await Timer(
        1,
        units="ns",
    )

    window = PureRandomRuntimeWindow()

    next_entry_index = 0

    patched_word_count = 0
    patch_reuse_count = 0

    patched_physical_slots: set[int] = set()

    max_resident_words = 0

    async def fill_available_capacity():
        """
        Greedily patch complete future entries while capacity permits.

        Required ordering:
          prove free ownership
          -> patch complete physical image
          -> publish runtime ownership

        No stream entry is split.
        """
        nonlocal next_entry_index
        nonlocal patched_word_count
        nonlocal patch_reuse_count
        nonlocal max_resident_words

        patched_entries_now = 0
        patched_words_now = 0

        while (
            next_entry_index
            < len(entries)
        ):
            entry = entries[
                next_entry_index
            ]

            if not window.can_commit(
                entry
            ):
                break

            assert_patch_slots_are_unowned(
                entry,
                window,
            )

            for (
                physical_pc,
                word,
            ) in zip(
                entry.physical_word_addresses,
                entry.image_words,
                strict=True,
            ):
                # Any second write to one physical slot is real
                # wrap/reuse evidence. Ownership was proven absent above.
                if (
                    physical_pc
                    in patched_physical_slots
                ):
                    patch_reuse_count += 1

                await patch_word(
                    dut,
                    address=physical_pc,
                    word=word,
                )

                patched_physical_slots.add(
                    physical_pc
                )

                patched_word_count += 1
                patched_words_now += 1

            window.commit_patched_entry(
                entry
            )

            next_entry_index += 1
            patched_entries_now += 1

            max_resident_words = max(
                max_resident_words,
                window.used_words,
            )

            assert (
                window.used_words
                <= IMEM_WORD_CAPACITY
            )

            resident_physical_owners(
                window
            )

        return (
            patched_entries_now,
            patched_words_now,
        )

    # ==========================================================
    # INITIAL GREEDY FILL — CLOCK STOPPED
    # ==========================================================
    (
        initial_entries,
        initial_words,
    ) = await fill_available_capacity()

    assert initial_entries > 0
    assert initial_words > 0

    assert (
        window.used_words
        <= IMEM_WORD_CAPACITY
    )

    # Entire N=300 image must not fit before execution.
    assert (
        next_entry_index
        < len(entries)
    )

    dut._log.info(
        "M1-PR initial fill "
        f"entries={initial_entries} "
        f"words={initial_words} "
        f"resident={window.used_words} "
        f"next_entry={next_entry_index}"
    )

    # ==========================================================
    # CONTINUOUS REFERENCE STATE
    # ==========================================================
    adapter = ExecutionEventAdapter()

    architectural_model = (
        WrapAwareRV32ArchitecturalModel()
    )

    cycle = 0

    max_cycles = (
        REFILL_ACCEPTED_BUDGET
        * 16
        + 1024
    )

    stall_cycle_count = 0
    flush_cycle_count = 0

    refill_pause_count = 0
    released_entry_count = 0

    observed_generations: set[int] = set()

    max_executed_logical_word = -1

    measurement_start_ns = (
        time.perf_counter_ns()
    )

    # ==========================================================
    # ONE CLOCK OWNER
    # ==========================================================
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

    hard_cap_reached = False

    # resume_clock_from_high_to_falling() already returns at a settled
    # FallingEdge, so the next iteration must consume that point rather
    # than wait for another falling edge.
    pre_edge_ready = False

    # ==========================================================
    # RTL EXECUTION + REFILL
    # ==========================================================
    while not hard_cap_reached:
        if cycle >= max_cycles:
            raise AssertionError(
                "M1-PR refill smoke exceeded bounded cycle budget: "
                f"accepted={window.accepted_count}, "
                f"cycle={cycle}, "
                f"next_entry={next_entry_index}"
            )

        # ------------------------------------------------------
        # FALLING EDGE + ReadOnly
        # ------------------------------------------------------
        if pre_edge_ready:
            pre_edge_ready = False
        else:
            await FallingEdge(
                dut.clk
            )

            await ReadOnly()

        cycle += 1

        reset = bool(
            signal_int(
                dut.reset
            )
        )

        stall = bool(
            signal_int(
                dut.probe_stall
            )
        )

        flush = bool(
            signal_int(
                dut.probe_flush
            )
        )

        if stall:
            stall_cycle_count += 1

        if flush:
            flush_cycle_count += 1

        snapshot = PreEdgeSnapshot(
            cycle=cycle,
            reset=reset,
            stall=stall,
            flush_redirect=flush,
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

        observed_b_pc = signal_int(
            dut.probe_b_pc
        )

        observed_b_instruction = signal_int(
            dut.probe_b_instr
        )

        assert observed_b_pc == pending.pc, (
            "ID/EX PC does not match admitted IF/ID PC: "
            f"pending=0x{pending.pc:03x}, "
            f"observed=0x{observed_b_pc:03x}"
        )

        assert (
            observed_b_instruction
            == pending.instruction
        ), (
            "ID/EX instruction does not match admitted IF/ID word: "
            f"pc=0x{pending.pc:03x}, "
            f"pending=0x{pending.instruction:08x}, "
            f"observed=0x{observed_b_instruction:08x}"
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

        assert (
            event.instruction_index
            <= REFILL_ACCEPTED_BUDGET
        )

        # ------------------------------------------------------
        # EXACT RUNTIME PLAN CONSISTENCY
        #
        # This must run before secondary diagnostic checks so that
        # any PC/instruction divergence is classified through the
        # frozen terminal-failure contract.
        # ------------------------------------------------------
        try:
            completed = (
                window.finalize_accepted_event(
                    event
                )
            )

        except PureRandomStreamExecutionMismatch as exc:
            clock_task.kill()

            raise AssertionError(
                "VALID_DUT_FAILURE_TERMINAL: "
                f"{exc}"
            ) from exc

        assert (
            window.accepted_count
            == event.instruction_index
        )

        # ------------------------------------------------------
        # LOGICAL GENERATION EVIDENCE
        #
        # Reached only after the event has passed exact runtime
        # PC/instruction validation.
        # ------------------------------------------------------
        logical_word = accepted_logical_words[
            event.instruction_index - 1
        ]

        assert (
            physical_pc_for_logical_word(
                logical_word
            )
            == event.pc
        )

        generation = (
            logical_word
            // IMEM_WORD_CAPACITY
        )

        observed_generations.add(
            generation
        )

        max_executed_logical_word = max(
            max_executed_logical_word,
            logical_word,
        )

        # ------------------------------------------------------
        # INDEPENDENT GOLDEN FETCH SEMANTICS
        # ------------------------------------------------------
        architectural_step = (
            architectural_model.step(
                event
            )
        )

        if not architectural_step.pc_match:
            clock_task.kill()

            raise AssertionError(
                "VALID_DUT_FAILURE_TERMINAL_ARCH_PC: "
                f"instruction_index={event.instruction_index}, "
                f"event_pc=0x{event.pc:03x}, "
                f"golden_expected="
                f"0x{architectural_step.expected_pc:03x}"
            )

        # Frozen M1 positive envelope must not activate the canonical
        # x0-write defect.
        assert signal_int(
            dut.probe_x0
        ) == 0, (
            "canonical x0 became non-zero inside frozen "
            "M1 positive stochastic envelope"
        )

        if completed is not None:
            released_entry_count += 1

            # Release performed by RuntimeWindow must have removed all
            # physical ownership of this completed block.
            current_owners = (
                resident_physical_owners(
                    window
                )
            )

            for physical_pc in (
                completed
                .entry
                .physical_word_addresses
            ):
                # A later still-resident logical generation could own
                # the same slot only if >128 live words existed, which
                # is forbidden. Therefore released addresses must be free
                # at this exact point, before refill.
                assert (
                    physical_pc
                    not in current_owners
                )

        assert (
            window.used_words
            <= IMEM_WORD_CAPACITY
        )

        # ======================================================
        # EXACT-N TERMINATION HAS PRIORITY OVER REFILL
        # ======================================================
        if (
            event.instruction_index
            == REFILL_ACCEPTED_BUDGET
        ):
            hard_cap_reached = True

            clock_task.kill()

            assert clock_task.done()

            assert signal_int(
                dut.clk
            ) == 1

            # Exit ReadOnly without allowing another architectural edge.
            await Timer(
                1,
                units="ns",
            )

            assert signal_int(
                dut.clk
            ) == 1

            assert (
                window.accepted_count
                == REFILL_ACCEPTED_BUDGET
            )

            assert (
                adapter.instruction_count
                == REFILL_ACCEPTED_BUDGET
            )

            # All offline entries needed to reach N must already have
            # been patched.
            assert (
                next_entry_index
                == len(entries)
            )

            # Frozen known-answer N=300 ends inside its final block.
            assert (
                window.pending_entry_count
                == 1
            )

            final_plan_block = (
                plan.blocks[-1]
            )

            assert final_plan_block.is_partial

            discarded = (
                window
                .discard_unexecuted_suffix()
            )

            assert (
                discarded
                .accepted_count_at_termination
                == REFILL_ACCEPTED_BUDGET
            )

            assert (
                discarded
                .head_accepted_instruction_count
                == len(
                    final_plan_block
                    .accepted_word_indices
                )
            )

            assert (
                len(discarded.entries)
                == 1
            )

            assert (
                window.pending_entry_count
                == 0
            )

            assert window.used_words == 0

            break

        # ======================================================
        # CAPACITY-SAFE RUNTIME REFILL
        # ======================================================
        if (
            completed is not None
            and next_entry_index < len(entries)
            and window.free_words
            >= REFILL_THRESHOLD_WORDS
        ):
            # We are at RisingEdge + ReadOnly with clk HIGH.
            clock_task.kill()

            assert clock_task.done()

            assert signal_int(
                dut.clk
            ) == 1

            # Exit ReadOnly without generating an edge.
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
                patched_entries_now,
                patched_words_now,
            ) = await fill_available_capacity()

            assert patched_entries_now > 0
            assert patched_words_now > 0

            refill_pause_count += 1

            assert (
                window.used_words
                <= IMEM_WORD_CAPACITY
            )

            resident_physical_owners(
                window
            )

            # Resume and return at the exact next FallingEdge sampling
            # point.
            clock_task = (
                await resume_clock_from_high_to_falling(
                    dut,
                    clock,
                )
            )

            pre_edge_ready = True

    # ==========================================================
    # POSTCONDITIONS
    # ==========================================================
    elapsed_ns = (
        time.perf_counter_ns()
        - measurement_start_ns
    )

    assert (
        window.accepted_count
        == REFILL_ACCEPTED_BUDGET
    )

    assert (
        adapter.instruction_count
        == REFILL_ACCEPTED_BUDGET
    )

    assert (
        patched_word_count
        == total_image_words
    )

    assert (
        next_entry_index
        == len(entries)
    )

    assert refill_pause_count > 0
    assert patch_reuse_count > 0

    assert (
        max_resident_words
        <= IMEM_WORD_CAPACITY
    )

    # N=300 must actually execute in all four logical generations,
    # not merely plan them.
    assert observed_generations == {
        0,
        1,
        2,
        3,
    }

    assert (
        max_executed_logical_word
        // IMEM_WORD_CAPACITY
        == 3
    )

    accepted_per_second = (
        REFILL_ACCEPTED_BUDGET
        / (elapsed_ns / 1_000_000_000)
    )

    dut._log.info(
        "M1-PR RTL REFILL PASS "
        f"seed={REFILL_ROOT_SEED} "
        f"accepted={window.accepted_count} "
        f"cycles={cycle} "
        f"released_entries={released_entry_count} "
        f"refill_pauses={refill_pause_count} "
        f"patched_words={patched_word_count} "
        f"patch_reuses={patch_reuse_count} "
        f"max_resident_words={max_resident_words} "
        f"generations={sorted(observed_generations)} "
        f"stall_cycles={stall_cycle_count} "
        f"flush_cycles={flush_cycle_count} "
        f"wall_ns={elapsed_ns} "
        f"accepted_per_s={accepted_per_second:.2f} "
        f"plan_hash={plan.plan_hash}"
    )
