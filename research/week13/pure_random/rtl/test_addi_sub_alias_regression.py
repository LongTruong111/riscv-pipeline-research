from __future__ import annotations

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
    nop,
)


CLOCK_NS = 10
EXPECTED = 1026


def signal_int(signal, name: str) -> int:
    try:
        return int(signal.value)
    except ValueError as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z: "
            f"{signal.value}"
        ) from exc


async def patch_word(
    dut,
    *,
    address: int,
    word: int,
) -> None:
    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = address
    dut.imem_patch_data.value = word

    await Timer(1, units="ns")

    dut.imem_patch_strobe.value = 1
    await Timer(1, units="ns")

    dut.imem_patch_strobe.value = 0
    await Timer(1, units="ns")


@cocotb.test()
async def test_addi_imm_0x402_is_add_not_sub(
    dut,
):
    """
    Directed witness for the I-type/R-type ALU-control alias.

    ADDI x13, x0, 1026 encodes:
        imm[11:5] = 7'b0100000

    Those bits must remain immediate payload. They must not be
    interpreted as the R-type SUB funct7 field.
    """

    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    await Timer(1, units="ns")

    instruction = addi(
        13,
        0,
        EXPECTED,
    )

    assert instruction == 0x40200693

    await patch_word(
        dut,
        address=0,
        word=instruction,
    )

    for address in (4, 8, 12, 16):
        await patch_word(
            dut,
            address=address,
            word=nop(),
        )

    clock = Clock(
        dut.clk,
        CLOCK_NS,
        units="ns",
    )

    clock_task = cocotb.start_soon(
        clock.start()
    )

    dut.reset.value = 1

    for _ in range(3):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)

    dut.reset.value = 0

    observed = None

    for _ in range(20):
        await FallingEdge(dut.clk)
        await ReadOnly()

        if (
            signal_int(
                dut.reg_write_sig,
                "reg_write_sig",
            )
            and signal_int(
                dut.reg_num,
                "reg_num",
            )
            == 13
        ):
            observed = signal_int(
                dut.reg_data,
                "reg_data",
            )
            break

    clock_task.kill()

    assert observed is not None, (
        "x13 writeback was not observed"
    )

    assert observed == EXPECTED, (
        "ADDI immediate aliased R-type SUB: "
        f"expected=0x{EXPECTED:08x}, "
        f"observed=0x{observed:08x}"
    )
