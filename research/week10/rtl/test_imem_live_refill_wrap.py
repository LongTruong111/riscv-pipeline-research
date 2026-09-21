import cocotb

from cocotb.clock import Clock
from cocotb.triggers import (
    FallingEdge,
    ReadOnly,
    RisingEdge,
    Timer,
)

from research.week5.impl.rv32_encode import (
    addi,
)
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)


CLOCK_NS = 10

IMEM_BYTES = 512
INSTRUCTION_BYTES = 4
IMEM_WORDS = IMEM_BYTES // INSTRUCTION_BYTES

# Keep the first encounter comfortably after reset/startup.
TARGET_PC = 0x40

# Straight-line, source-independent instruction used everywhere else.
# No positive-register RAW dependency is introduced.
BASE_WORD = addi(
    31,
    0,
    0,
)

# First contents of TARGET_PC.
FIRST_SENTINEL = addi(
    7,
    0,
    11,
)

# Contents written into the same physical slot after FIRST_SENTINEL
# has been architecturally accepted into ID/EX.
SECOND_SENTINEL = addi(
    7,
    0,
    22,
)

# Same 9-bit PC occurs again after exactly 128 sequential accepted
# RV32 instructions.
EXPECTED_SAME_PC_DISTANCE = IMEM_WORDS

# Enough cycles for startup + first encounter + one complete wrap.
MAX_CYCLES = 220


def signal_int(signal) -> int:
    return int(signal.value)


async def patch_word(
    dut,
    *,
    address: int,
    word: int,
) -> None:
    """
    Pulse the verification-only IMEM backdoor.

    Caller must leave ReadOnly before calling this helper when the
    simulation clock is already running.
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

    if address > 508:
        raise ValueError(
            "word would exceed executable 9-bit PC window"
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
      - reset high for >= 3 cycles;
      - deassert at FallingEdge;
      - observe settled state at RisingEdge + ReadOnly.
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
async def test_live_refill_same_slot_after_pc_wrap(
    dut,
):
    """
    RTL proof obligation:

      1. Fill the complete 128-word executable IMEM window with a
         straight-line supported instruction stream.

      2. Place FIRST_SENTINEL at TARGET_PC.

      3. Run the frozen DUT and observe FIRST_SENTINEL becoming an
         architecturally accepted ExecutionEvent.

      4. After its RisingEdge + ReadOnly acceptance point, leave
         ReadOnly and patch the *same physical IMEM slot* with
         SECOND_SENTINEL.

      5. Do not reset.

      6. Continue execution through the 9-bit PC wrap.

      7. When TARGET_PC is encountered again, prove:
           - it is SECOND_SENTINEL;
           - it becomes an accepted ExecutionEvent;
           - the two occurrences are exactly 128 accepted
             instructions apart.

    This establishes live physical-slot reuse across PC wrap without
    relying on reset or $readmemh reinitialization.
    """

    # ----------------------------------------------------------
    # Initial signal state
    # ----------------------------------------------------------
    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    # Allow RTL initial blocks, including $readmemh, to complete.
    await Timer(
        1,
        units="ns",
    )

    # ----------------------------------------------------------
    # Initialize the complete 512-byte executable window.
    #
    # This eliminates dependence on instruction.hex contents and
    # guarantees straight-line execution across the wrap boundary.
    # ----------------------------------------------------------
    for address in range(
        0,
        IMEM_BYTES,
        INSTRUCTION_BYTES,
    ):
        word = (
            FIRST_SENTINEL
            if address == TARGET_PC
            else BASE_WORD
        )

        await patch_word(
            dut,
            address=address,
            word=word,
        )

    # ----------------------------------------------------------
    # Single clock owner.
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

    # The adapter begins only after reset initialization is complete.
    adapter = ExecutionEventAdapter()

    first_target_event = None
    second_target_event = None

    patched_after_first_accept = False
    observed_wrap_after_patch = False

    # ----------------------------------------------------------
    # Continuous execution loop.
    # ----------------------------------------------------------
    for cycle in range(
        1,
        MAX_CYCLES + 1,
    ):
        # ------------------------------------------------------
        # FALLING EDGE + ReadOnly:
        # frozen pre-edge admission sampling point.
        # ------------------------------------------------------
        await FallingEdge(
            dut.clk
        )
        await ReadOnly()

        assert signal_int(
            dut.reset
        ) == 0

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
        # RISING EDGE + ReadOnly:
        # frozen post-edge acceptance point.
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

        b_instr = signal_int(
            dut.probe_b_instr
        )

        assert b_pc == pending.pc, (
            "accepted ID/EX PC does not match pending admission: "
            f"pending=0x{pending.pc:03x}, "
            f"observed=0x{b_pc:03x}"
        )

        assert b_instr == pending.instruction, (
            "accepted ID/EX instruction does not match "
            "pending admission: "
            f"pc=0x{pending.pc:03x}, "
            f"pending=0x{pending.instruction:08x}, "
            f"observed=0x{b_instr:08x}"
        )

        event = adapter.finalize_post_edge(
            pending,
            forward_a=signal_int(
                dut.probe_fwd_a
            ),
            forward_b=signal_int(
                dut.probe_fwd_b
            ),
        )

        # Once the first target has executed, seeing accepted PC=0
        # proves that the architectural stream crossed the 9-bit wrap.
        if (
            first_target_event is not None
            and event.pc == 0
        ):
            observed_wrap_after_patch = True

        if event.pc != TARGET_PC:
            continue

        # ------------------------------------------------------
        # First execution of the target physical slot.
        # ------------------------------------------------------
        if first_target_event is None:
            assert (
                event.instruction
                == FIRST_SENTINEL
            ), (
                "first target execution did not observe "
                "FIRST_SENTINEL: "
                f"expected=0x{FIRST_SENTINEL:08x}, "
                f"observed=0x{event.instruction:08x}"
            )

            first_target_event = event

            # We are currently in RisingEdge + ReadOnly.
            #
            # Leave ReadOnly before driving the asynchronous patch
            # interface. With a 10 ns clock, this operation completes
            # before the next FallingEdge.
            await Timer(
                1,
                units="ns",
            )

            await patch_word(
                dut,
                address=TARGET_PC,
                word=SECOND_SENTINEL,
            )

            patched_after_first_accept = True

            # Critical invariant: slot reuse does not use reset.
            assert signal_int(
                dut.reset
            ) == 0

            continue

        # ------------------------------------------------------
        # Second execution of the same physical slot after wrap.
        # ------------------------------------------------------
        second_target_event = event

        assert patched_after_first_accept

        assert observed_wrap_after_patch, (
            "TARGET_PC was encountered again before an accepted "
            "PC wrap to zero was observed"
        )

        assert (
            second_target_event.instruction
            == SECOND_SENTINEL
        ), (
            "same physical IMEM slot retained stale contents "
            "after live refill: "
            f"expected=0x{SECOND_SENTINEL:08x}, "
            f"observed="
            f"0x{second_target_event.instruction:08x}"
        )

        break

    # ----------------------------------------------------------
    # Final proof conditions
    # ----------------------------------------------------------
    assert first_target_event is not None, (
        "FIRST_SENTINEL was never architecturally accepted"
    )

    assert patched_after_first_accept, (
        "same-slot live refill was never performed"
    )

    assert observed_wrap_after_patch, (
        "no accepted 9-bit PC wrap was observed after refill"
    )

    assert second_target_event is not None, (
        "SECOND_SENTINEL was not accepted after PC wrap"
    )

    accepted_distance = (
        second_target_event.instruction_index
        - first_target_event.instruction_index
    )

    assert (
        accepted_distance
        == EXPECTED_SAME_PC_DISTANCE
    ), (
        "same physical PC did not recur after exactly one "
        "128-word accepted-program wrap: "
        f"expected={EXPECTED_SAME_PC_DISTANCE}, "
        f"observed={accepted_distance}"
    )

    # Most important continuity invariant.
    assert signal_int(
        dut.reset
    ) == 0
