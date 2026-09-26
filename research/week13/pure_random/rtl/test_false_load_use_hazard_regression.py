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
    auipc,
    lw,
    nop,
)


CLOCK_NS = 10


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


async def run_and_count_stalls(
    dut,
    program,
    *,
    observation_cycles: int = 20,
) -> int:
    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    await Timer(1, units="ns")

    image = tuple(program) + (
        nop(),
        nop(),
        nop(),
        nop(),
        nop(),
        nop(),
    )

    for index, word in enumerate(image):
        await patch_word(
            dut,
            address=index * 4,
            word=word,
        )

    clock = Clock(
        dut.clk,
        CLOCK_NS,
        units="ns",
    )

    clock_task = cocotb.start_soon(
        clock.start()
    )

    for _ in range(3):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.reset.value = 0

    stall_cycles = 0

    for _ in range(observation_cycles):
        await FallingEdge(dut.clk)
        await ReadOnly()

        if signal_int(
            dut.probe_stall,
            "probe_stall",
        ):
            stall_cycles += 1

    clock_task.kill()

    return stall_cycles


@cocotb.test()
async def test_auipc_raw_rs2_bits_do_not_create_load_use_stall(
    dut,
):
    """
    Exact class of the M1 #451 -> #452 false dependency.

    AUIPC uses neither rs1 nor rs2. Its instruction payload must not
    participate in load-use hazard comparison.
    """

    consumer = auipc(
        5,
        0x01400,
    )

    # Deliberately make raw instr[24:20] equal x20.
    assert (
        (consumer >> 20) & 0x1F
    ) == 20

    stall_cycles = await run_and_count_stalls(
        dut,
        (
            lw(20, 0, 0),
            consumer,
        ),
    )

    assert stall_cycles == 0, (
        "false load-use hazard: AUIPC does not use "
        f"rs1/rs2 but observed {stall_cycles} stall cycle(s)"
    )


@cocotb.test()
async def test_true_load_use_dependency_still_stalls_once(
    dut,
):
    """
    Control case: a real LW -> ADDI rs1 dependency must retain the
    canonical one-cycle load-use stall.
    """

    stall_cycles = await run_and_count_stalls(
        dut,
        (
            lw(20, 0, 0),
            addi(5, 20, 1),
        ),
    )

    assert stall_cycles == 1, (
        "true load-use hazard must stall exactly once: "
        f"observed={stall_cycles}"
    )
