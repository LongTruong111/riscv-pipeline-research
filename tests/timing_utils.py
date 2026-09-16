from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ReadOnly


def make_clock(signal, period_ns=10):
    """Compatible with common cocotb 1.x/2.x Clock APIs."""
    try:
        return Clock(signal, period_ns, unit="ns")
    except TypeError:
        return Clock(signal, period_ns, units="ns")


async def reset_active_low(dut, cycles=3):
    """
    Assert reset for >= cycles clock edges.
    Deassert at FallingEdge to avoid racing sequential logic.
    """
    dut.en.value = 0
    dut.rst_n.value = 0

    for _ in range(cycles):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.rst_n.value = 1


async def drive_at_falling(clk, signal, value):
    """Safe input drive: change input away from DUT sampling edge."""
    await FallingEdge(clk)
    signal.value = value


async def sample_after_rising(clk, signal):
    """
    Wait for DUT sampling edge, then move to ReadOnly so sequential
    and combinational effects for the timestep can settle.
    """
    await RisingEdge(clk)
    await ReadOnly()
    return int(signal.value)

async def capture_before_rising(clk, *signals):
    """
    Capture stable combinational intent before the next active edge.

    Suitable for signals such as:
    PcSel, Reg_Stall, forwarding selects, and WB commit intent.
    """
    await FallingEdge(clk)
    await ReadOnly()

    return tuple(int(signal.value) for signal in signals)
