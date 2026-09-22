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
    bne,
)


CLOCK_NS = 10
INSTRUCTION_BYTES = 4
MAX_PATCH_ADDRESS = 508

# Keep the proof comfortably below the 9-bit PC wrap boundary.
EBD_PC = 0x20

# Positive-rd predecessor:
#   - cannot satisfy H18 producer condition;
#   - has no control-flow effect.
PREDECESSOR_WORD = addi(
    5,
    0,
    1,
)

# Frozen EBD candidate.
#
# BNE x0, x0, +4:
#   - legal BRANCH instruction;
#   - reads no positive register;
#   - writes no GPR;
#   - expected not-taken;
#   - expected PcSel == 0.
EBD_WORD = bne(
    0,
    0,
    4,
)

# Sequential sentinel after the delimiter.
SENTINEL_WORD = addi(
    7,
    0,
    77,
)

# Source-independent legal filler for all other locations.
PLACEHOLDER_WORD = addi(
    31,
    0,
    0,
)


def signal_int(signal) -> int:
    return int(signal.value)


async def patch_word(
    dut,
    *,
    address: int,
    word: int,
) -> None:
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


@cocotb.test()
async def test_bne_x0_x0_epoch_boundary_delimiter(
    dut,
):
    """
    Dynamic proof for the proposed epoch-boundary delimiter (EBD).

    Program fragment:

        predecessor
        BNE x0, x0, +4      <- EBD
        sentinel

    Proof obligations:

      1. EBD reaches IF/ID at the expected PC.
      2. EBD is admissible: reset=0, stall=0, flush=0.
      3. EBD is accepted into ID/EX unchanged.
      4. Once EBD is in ID/EX, PcSel remains 0.
      5. Sequential sentinel is already present in IF/ID.
      6. Sentinel is accepted next, with no missing or duplicate
         architectural instruction between EBD and sentinel.
      7. No reset occurs during the proof.
    """

    # Lock the expected encoding independently of the RTL behavior.
    assert EBD_WORD == 0x00001263, (
        "unexpected BNE x0,x0,+4 encoding: "
        f"0x{EBD_WORD:08x}"
    )

    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    # Allow Verilog initial blocks to settle before backdoor writes.
    await Timer(
        1,
        units="ns",
    )

    # Build a deterministic straight-line region.
    for address in range(
        0,
        EBD_PC + 0x20,
        INSTRUCTION_BYTES,
    ):
        await patch_word(
            dut,
            address=address,
            word=PLACEHOLDER_WORD,
        )

    await patch_word(
        dut,
        address=EBD_PC - INSTRUCTION_BYTES,
        word=PREDECESSOR_WORD,
    )

    await patch_word(
        dut,
        address=EBD_PC,
        word=EBD_WORD,
    )

    await patch_word(
        dut,
        address=EBD_PC + INSTRUCTION_BYTES,
        word=SENTINEL_WORD,
    )

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

    observed_ebd = False
    accepted_ebd = False
    accepted_sentinel = False

    # More than enough to reach 0x20, while remaining far from wrap.
    for _ in range(32):
        await FallingEdge(
            dut.clk
        )

        await ReadOnly()

        assert signal_int(
            dut.reset
        ) == 0

        a_pc = signal_int(
            dut.probe_a_pc
        )

        a_instr = signal_int(
            dut.probe_a_instr
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

        if a_pc != EBD_PC:
            await RisingEdge(
                dut.clk
            )

            await ReadOnly()
            continue

        observed_ebd = True

        assert a_instr == EBD_WORD, (
            "IF/ID reached EBD PC with wrong instruction: "
            f"expected=0x{EBD_WORD:08x}, "
            f"observed=0x{a_instr:08x}"
        )

        assert not stall, (
            "EBD unexpectedly stalled before admission"
        )

        assert not flush, (
            "pipeline was already redirecting before EBD admission"
        )

        # Admit EBD into ID/EX.
        await RisingEdge(
            dut.clk
        )

        await ReadOnly()

        assert signal_int(
            dut.reset
        ) == 0

        assert signal_int(
            dut.probe_b_pc
        ) == EBD_PC, (
            "EBD was not admitted into ID/EX at expected PC"
        )

        assert signal_int(
            dut.probe_b_instr
        ) == EBD_WORD, (
            "EBD changed before ID/EX admission"
        )

        accepted_ebd = True

        # Critical EBD property:
        #
        # B now contains BNE x0,x0,+4.
        # The frozen BranchUnit must classify it as NOT TAKEN.
        assert signal_int(
            dut.probe_flush
        ) == 0, (
            "EBD asserted PcSel/flush; "
            "BNE x0,x0,+4 was not dynamically neutral"
        )

        # Because the EBD was not taken, the sequential instruction
        # must have entered IF/ID on the same rising edge.
        assert signal_int(
            dut.probe_a_pc
        ) == (
            EBD_PC
            + INSTRUCTION_BYTES
        ), (
            "sequential PC after EBD is incorrect"
        )

        assert signal_int(
            dut.probe_a_instr
        ) == SENTINEL_WORD, (
            "sequential sentinel was not present in IF/ID "
            "after EBD admission"
        )

        # Advance to the sentinel admission edge.
        await FallingEdge(
            dut.clk
        )

        await ReadOnly()

        assert signal_int(
            dut.probe_flush
        ) == 0, (
            "EBD asserted a delayed redirect before sentinel admission"
        )

        assert signal_int(
            dut.probe_a_pc
        ) == (
            EBD_PC
            + INSTRUCTION_BYTES
        )

        assert signal_int(
            dut.probe_a_instr
        ) == SENTINEL_WORD

        assert signal_int(
            dut.probe_stall
        ) == 0, (
            "sentinel unexpectedly stalled after EBD"
        )

        await RisingEdge(
            dut.clk
        )

        await ReadOnly()

        assert signal_int(
            dut.probe_b_pc
        ) == (
            EBD_PC
            + INSTRUCTION_BYTES
        ), (
            "sentinel was not the next admitted instruction"
        )

        assert signal_int(
            dut.probe_b_instr
        ) == SENTINEL_WORD, (
            "sentinel changed before ID/EX admission"
        )

        accepted_sentinel = True
        break

    # Stop the sole clock owner explicitly.
    clock_task.kill()

    assert observed_ebd, (
        "EBD never reached IF/ID"
    )

    assert accepted_ebd, (
        "EBD was never admitted into ID/EX"
    )

    assert accepted_sentinel, (
        "sequential sentinel was not admitted immediately after EBD"
    )

    assert signal_int(
        dut.reset
    ) == 0
