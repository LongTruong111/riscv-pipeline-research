import cocotb

from cocotb.triggers import RisingEdge, FallingEdge, ReadOnly

from timing_utils import (
    make_clock,
    reset_active_low,
    drive_at_falling,
    sample_after_rising,
)


async def setup(dut):
    clock = make_clock(dut.clk, 10)
    cocotb.start_soon(clock.start())
    await reset_active_low(dut, cycles=3)


@cocotb.test()
async def test_drive_at_posedge_racy(dut):
    """
    Intentionally racy experiment.

    en is changed on the same rising edge on which the RTL samples en.
    The observed behavior must NOT become a portable timing rule.
    """
    await setup(dut)

    await drive_at_falling(dut.clk, dut.en, 1)

    first = await sample_after_rising(dut.clk, dut.count)
    assert first == 1

    # Intentional race:
    await RisingEdge(dut.clk)
    dut.en.value = 0

    await ReadOnly()
    second = int(dut.count.value)

    dut._log.info(
        "RACY_POS: first=%d second=%d", first, second
    )

    # Both are plausible observations for a race experiment.
    assert second in (first, first + 1)


@cocotb.test()
async def test_drive_at_fallingedge_safe(dut):
    """
    Safe experiment:
    drive en on falling edge, sample after next rising edge + ReadOnly.
    """
    await setup(dut)

    await drive_at_falling(dut.clk, dut.en, 1)

    first = await sample_after_rising(dut.clk, dut.count)
    assert first == 1

    await drive_at_falling(dut.clk, dut.en, 0)

    second = await sample_after_rising(dut.clk, dut.count)

    dut._log.info(
        "SAFE_FALL: first=%d second=%d", first, second
    )

    assert second == first


@cocotb.test()
async def test_sample_phase(dut):
    """
    Compare immediate read after RisingEdge with settled ReadOnly value.
    """
    await setup(dut)

    await drive_at_falling(dut.clk, dut.en, 1)

    await RisingEdge(dut.clk)

    immediate = int(dut.count.value)

    await ReadOnly()

    settled = int(dut.count.value)

    dut._log.info(
        "SAMPLE_PHASE: immediate=%d settled=%d",
        immediate,
        settled,
    )

    assert settled == 1
