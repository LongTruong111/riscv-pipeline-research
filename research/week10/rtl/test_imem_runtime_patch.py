import cocotb

from cocotb.clock import Clock
from cocotb.triggers import (
    FallingEdge,
    ReadOnly,
    RisingEdge,
    Timer,
)

from research.week5.impl.rv32_encode import addi


CLOCK_NS = 10

# Keep the runtime-patched location comfortably ahead of the PC when
# the patch occurs.
TARGET_PC = 0x80

PLACEHOLDER_WORD = addi(
    31,
    0,
    0,
)

SENTINEL_WORD = addi(
    7,
    0,
    77,
)


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

    The pulse is deliberately placed away from the DUT clock edge.
    """
    if address < 0:
        raise ValueError(
            "address must be non-negative"
        )

    if address % 4 != 0:
        raise ValueError(
            "address must be 4-byte aligned"
        )

    if address > 508:
        raise ValueError(
            "word would exceed executable 9-bit PC window"
        )

    if not 0 <= word <= 0xFFFFFFFF:
        raise ValueError(
            "word must fit 32 bits"
        )

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = address
    dut.imem_patch_data.value = word

    await Timer(1, units="ns")

    dut.imem_patch_strobe.value = 1

    await Timer(1, units="ns")

    dut.imem_patch_strobe.value = 0

    await Timer(1, units="ns")


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
        await RisingEdge(dut.clk)

    # Frozen protocol:
    # deassert reset on FallingEdge.
    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


@cocotb.test()
async def test_runtime_imem_patch_without_reset(dut):
    """
    Proof obligation:

    1. Initialize a known linear instruction region through the
       verification-only backdoor.
    2. Start and reset the frozen DUT.
    3. After reset is LOW, replace one future instruction.
    4. Do NOT reset again.
    5. Prove the replacement reaches IF/ID and is accepted into ID/EX.

    Passing this test establishes that adaptive epochs can update future
    instructions within one continuous RTL simulation.
    """

    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    # Allow RTL initial blocks, including $readmemh, to complete before
    # applying verification-side patches.
    await Timer(1, units="ns")

    # Build a known, straight-line executable region.
    #
    # Every instruction writes x31 from x0 and consumes no positive
    # register source, so it creates no RAW chain.
    for address in range(
        0,
        TARGET_PC + 20,
        4,
    ):
        await patch_word(
            dut,
            address=address,
            word=PLACEHOLDER_WORD,
        )

    # Explicitly establish the pre-runtime value at the target.
    await patch_word(
        dut,
        address=TARGET_PC,
        word=PLACEHOLDER_WORD,
    )

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

    assert signal_int(dut.reset) == 0

    # Move to a falling edge while reset is already deasserted.
    await FallingEdge(dut.clk)
    await ReadOnly()

    current_pc = signal_int(
        dut.probe_a_pc
    )

    assert current_pc < TARGET_PC, (
        "runtime patch target was not sufficiently ahead of current "
        f"execution: current_pc=0x{current_pc:03x}, "
        f"target_pc=0x{TARGET_PC:03x}"
    )

    # Leave ReadOnly before driving the patch interface.
    await Timer(1, units="ns")

    # Critical operation: patch while the DUT is running and reset stays
    # LOW. There is deliberately no reset after this point.
    await patch_word(
        dut,
        address=TARGET_PC,
        word=SENTINEL_WORD,
    )

    assert signal_int(dut.reset) == 0

    observed_target_in_a = False
    accepted_target_in_b = False

    # 64 cycles is comfortably beyond the 0x80 target while remaining
    # below the 9-bit PC wrap boundary.
    for _ in range(64):
        await FallingEdge(dut.clk)
        await ReadOnly()

        assert signal_int(dut.reset) == 0

        a_pc = signal_int(
            dut.probe_a_pc
        )

        a_instr = signal_int(
            dut.probe_a_instr
        )

        stall = bool(
            signal_int(dut.probe_stall)
        )

        flush = bool(
            signal_int(dut.probe_flush)
        )

        target_is_admissible = (
            a_pc == TARGET_PC
            and not stall
            and not flush
        )

        if target_is_admissible:
            observed_target_in_a = True

            assert a_instr == SENTINEL_WORD, (
                "IF/ID reached runtime-patched address but retained the "
                "old instruction: "
                f"expected=0x{SENTINEL_WORD:08x}, "
                f"observed=0x{a_instr:08x}"
            )

        await RisingEdge(dut.clk)
        await ReadOnly()

        if target_is_admissible:
            b_pc = signal_int(
                dut.probe_b_pc
            )

            b_instr = signal_int(
                dut.probe_b_instr
            )

            assert b_pc == TARGET_PC, (
                "runtime-patched instruction was not admitted into "
                "ID/EX at the expected PC"
            )

            assert b_instr == SENTINEL_WORD, (
                "runtime-patched instruction changed before ID/EX "
                "admission"
            )

            accepted_target_in_b = True
            break

    assert observed_target_in_a, (
        "runtime-patched target never reached admissible IF/ID state"
    )

    assert accepted_target_in_b, (
        "runtime-patched target was not accepted into ID/EX"
    )

    # Most important proof condition: no reset was used to reload or
    # activate the patched instruction.
    assert signal_int(dut.reset) == 0
