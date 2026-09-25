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
    PureRandomRuntimeWindow,
    PureRandomStreamExecutionMismatch,
    build_runtime_entries,
)
from research.week13.pure_random.stream_planner import (
    generate_pure_random_plan,
)


CLOCK_NS = 10

SMOKE_ROOT_SEED = 11001
SMOKE_ACCEPTED_BUDGET = 50
SMOKE_EXPECTED_PLAN_HASH = (
    "1160ef7610cf0d93028734bd17e2d953f"
    "22d03ca70ff78a26834013e6515bb2e"
)

SMOKE_EXPECTED_BLOCK_COUNT = 34
SMOKE_EXPECTED_IMAGE_WORDS = 76

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

    This helper is used only while the DUT clock is not running in the
    first M1-PR smoke, so no architectural edge can occur while patching.
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
    Frozen Week-10 reset protocol.

      reset HIGH for >=3 cycles
      deassert at FallingEdge
      settle through RisingEdge + ReadOnly
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


@cocotb.test()
async def test_m1_pure_random_rtl_smoke_50(
    dut,
):
    """
    W13 M1-PR RTL smoke.

    Scope deliberately excludes runtime refill.

    Proves:
      - deterministic N=50 plan reaches canonical DUT;
      - IF/ID admission semantics are reconstructed by the frozen
        ExecutionEventAdapter;
      - RTL accepted PC/instruction order matches the M1 plan exactly;
      - Golden architectural fetch semantics remain consistent;
      - stalls and flushed wrong-path instructions create no event;
      - exact accepted hard cap creates no instruction N+1;
      - a partial resident final block is discarded without synthetic
        execution.
    """

    # ==========================================================
    # OFFLINE FROZEN PLAN
    # ==========================================================
    plan = generate_pure_random_plan(
        SMOKE_ROOT_SEED,
        SMOKE_ACCEPTED_BUDGET,
    )

    entries = build_runtime_entries(
        plan
    )

    assert (
        plan.accepted_instruction_count
        == SMOKE_ACCEPTED_BUDGET
    )

    total_image_words = sum(
        entry.image_word_count
        for entry in entries
    )

    assert plan.plan_hash == SMOKE_EXPECTED_PLAN_HASH
    assert len(plan.blocks) == SMOKE_EXPECTED_BLOCK_COUNT
    assert total_image_words == SMOKE_EXPECTED_IMAGE_WORDS

    # This first RTL smoke intentionally eliminates refill from the
    # failure domain.
    assert (
        total_image_words
        <= IMEM_WORD_CAPACITY
    ), (
        "N=50 smoke no longer fits one physical IMEM generation: "
        f"image_words={total_image_words}"
    )

    all_physical_words = [
        address
        for entry in entries
        for address
        in entry.physical_word_addresses
    ]

    # Because this test uses a single <=128-word generation, no physical
    # slot may be aliased/reused during prefill.
    assert (
        len(all_physical_words)
        == len(
            set(all_physical_words)
        )
    )

    families = Counter(
        block.realized.family.value
        for block in plan.blocks
    )

    dut._log.info(
        "M1-PR smoke plan "
        f"seed={SMOKE_ROOT_SEED} "
        f"accepted={SMOKE_ACCEPTED_BUDGET} "
        f"blocks={len(plan.blocks)} "
        f"image_words={total_image_words} "
        f"hash={plan.plan_hash} "
        f"families={dict(sorted(families.items()))}"
    )

    # ==========================================================
    # STATIC VERIFICATION INTERFACE INITIALIZATION
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

    # ==========================================================
    # COMPLETE PREFILL WHILE CLOCK IS STOPPED
    # ==========================================================
    window = PureRandomRuntimeWindow()

    patched_word_count = 0

    for entry in entries:
        assert window.can_commit(
            entry
        )

        # Commit ownership only after every word in the block has been
        # successfully patched.
        for (
            address,
            word,
        ) in zip(
            entry.physical_word_addresses,
            entry.image_words,
            strict=True,
        ):
            await patch_word(
                dut,
                address=address,
                word=word,
            )

            patched_word_count += 1

        window.commit_patched_entry(
            entry
        )

        assert (
            window.used_words
            <= IMEM_WORD_CAPACITY
        )

    assert (
        patched_word_count
        == total_image_words
    )

    assert (
        window.used_words
        == total_image_words
    )

    # ==========================================================
    # CONTINUOUS REFERENCE STATE
    # ==========================================================
    adapter = ExecutionEventAdapter()

    architectural_model = (
        WrapAwareRV32ArchitecturalModel()
    )

    stall_cycle_count = 0
    flush_cycle_count = 0

    cycle = 0

    max_cycles = (
        SMOKE_ACCEPTED_BUDGET
        * 12
        + 256
    )

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

    # ==========================================================
    # RTL EXECUTION
    # ==========================================================
    while not hard_cap_reached:
        if cycle >= max_cycles:
            raise AssertionError(
                "M1-PR RTL smoke exceeded bounded cycle budget: "
                f"accepted={window.accepted_count}, "
                f"cycle={cycle}"
            )

        # ------------------------------------------------------
        # FALLING EDGE + ReadOnly:
        # canonical IF/ID admission sampling point.
        # ------------------------------------------------------
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
        # RISING EDGE + ReadOnly:
        # canonical accepted A->B transition.
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

        observed_b_instruction = (
            signal_int(
                dut.probe_b_instr
            )
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

        # Exact-N guard: an event above the requested budget is never
        # legal.
        assert (
            event.instruction_index
            <= SMOKE_ACCEPTED_BUDGET
        )

        # ------------------------------------------------------
        # PLAN CONSISTENCY.
        #
        # Any PC/word divergence is a VALID_DUT_FAILURE_TERMINAL,
        # not an infrastructure-invalid replacement run.
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
        # INDEPENDENT GOLDEN ARCHITECTURAL FETCH STATE.
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
                f"golden_expected=0x"
                f"{architectural_step.expected_pc:03x}"
            )

        # Known RTL x0 defect is contained by the frozen stochastic
        # generator envelope. x0 must therefore remain zero here.
        assert signal_int(
            dut.probe_x0
        ) == 0, (
            "canonical x0 became non-zero inside frozen M1 positive "
            "stochastic envelope"
        )

        if completed is not None:
            dut._log.debug(
                "released M1 runtime entry "
                f"{completed.entry.block_index}"
            )

        assert (
            window.used_words
            <= IMEM_WORD_CAPACITY
        )

        # ======================================================
        # EXACT HARD CAP HAS PRIORITY.
        # ======================================================
        if (
            event.instruction_index
            == SMOKE_ACCEPTED_BUDGET
        ):
            hard_cap_reached = True

            # Event N is already fully admitted, checked against the
            # plan, and passed through the Golden architectural model.
            clock_task.kill()

            assert clock_task.done()

            # We are immediately after RisingEdge, therefore the frozen
            # clock must remain HIGH.
            assert signal_int(
                dut.clk
            ) == 1

            # Leave ReadOnly without creating another architectural edge.
            await Timer(
                1,
                units="ns",
            )

            assert signal_int(
                dut.clk
            ) == 1

            assert (
                window.accepted_count
                == SMOKE_ACCEPTED_BUDGET
            )

            # A partial final runtime entry remains resident by design.
            # Discard it without generating an artificial accepted event.
            if (
                window.pending_entry_count
                > 0
            ):
                discarded = (
                    window
                    .discard_unexecuted_suffix()
                )

                assert (
                    discarded
                    .accepted_count_at_termination
                    == SMOKE_ACCEPTED_BUDGET
                )

            assert (
                window.accepted_count
                == SMOKE_ACCEPTED_BUDGET
            )

            assert (
                adapter.instruction_count
                == SMOKE_ACCEPTED_BUDGET
            )

            assert (
                window.pending_entry_count
                == 0
            )

            assert window.used_words == 0

            break

    elapsed_ns = (
        time.perf_counter_ns()
        - measurement_start_ns
    )

    accepted_per_second = (
        SMOKE_ACCEPTED_BUDGET
        / (elapsed_ns / 1_000_000_000)
    )

    dut._log.info(
        "M1-PR RTL SMOKE PASS "
        f"seed={SMOKE_ROOT_SEED} "
        f"accepted={window.accepted_count} "
        f"cycles={cycle} "
        f"stall_cycles={stall_cycle_count} "
        f"flush_cycles={flush_cycle_count} "
        f"wall_ns={elapsed_ns} "
        f"accepted_per_s={accepted_per_second:.2f} "
        f"plan_hash={plan.plan_hash}"
    )
