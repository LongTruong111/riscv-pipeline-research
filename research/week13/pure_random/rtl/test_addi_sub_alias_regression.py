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


def encode_sub(
    rd: int,
    rs1: int,
    rs2: int,
) -> int:
    for value in (rd, rs1, rs2):
        if not 0 <= value <= 31:
            raise ValueError(
                "register must be in [0, 31]"
            )

    return (
        (0b0100000 << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (0b000 << 12)
        | (rd << 7)
        | 0b0110011
    )


@cocotb.test()
async def test_addi_alias_boundaries_and_rtype_sub(
    dut,
):
    """
    Revision-C qualification for the ADDI/SUB decode alias.

    Checks:
      - immediately below the affected region;
      - lower boundary;
      - original witness;
      - upper boundary;
      - immediately above the affected region;
      - genuine R-type SUB remains subtraction.
    """

    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    await Timer(1, units="ns")

    program = (
        addi(1, 0, 1023),
        addi(2, 0, 1024),
        addi(3, 0, 1026),
        addi(4, 0, 1055),
        addi(5, 0, 1056),

        addi(6, 0, 7),
        addi(7, 0, 3),

        # Remove forwarding as a confounder for the SUB witness.
        nop(),
        nop(),

        encode_sub(
            8,
            6,
            7,
        ),

        nop(),
        nop(),
        nop(),
        nop(),
    )

    for index, word in enumerate(program):
        await patch_word(
            dut,
            address=index * 4,
            word=word,
        )

    expected_by_rd = {
        1: 1023,
        2: 1024,
        3: 1026,
        4: 1055,
        5: 1056,
        6: 7,
        7: 3,
        8: 4,
    }

    observed_by_rd = {}

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

    for _ in range(64):
        await FallingEdge(dut.clk)
        await ReadOnly()

        if not signal_int(
            dut.reg_write_sig,
            "reg_write_sig",
        ):
            continue

        rd = signal_int(
            dut.reg_num,
            "reg_num",
        )

        if rd not in expected_by_rd:
            continue

        value = signal_int(
            dut.reg_data,
            "reg_data",
        )

        if rd in observed_by_rd:
            raise AssertionError(
                "duplicate directed writeback: "
                f"x{rd}"
            )

        observed_by_rd[rd] = value

        if (
            len(observed_by_rd)
            == len(expected_by_rd)
        ):
            break

    clock_task.kill()

    assert (
        set(observed_by_rd)
        == set(expected_by_rd)
    ), (
        "missing directed writebacks: "
        f"expected={sorted(expected_by_rd)}, "
        f"observed={sorted(observed_by_rd)}"
    )

    for rd, expected in expected_by_rd.items():
        observed = observed_by_rd[rd]

        assert observed == expected, (
            "ALU-control boundary regression: "
            f"x{rd}, "
            f"expected=0x{expected:08x}, "
            f"observed=0x{observed:08x}"
        )
