import cocotb

from cocotb.clock import Clock
from cocotb.triggers import (
    ReadOnly,
    RisingEdge,
    Timer,
)


CLOCK_NS = 10


def signal_int(signal) -> int:
    return int(signal.value)


@cocotb.test()
async def test_clock_task_kill_and_resume(dut):
    """
    T10.9e-2a proof obligation.

    Prove that Cocotb 1.9.2 allows the verification environment to:

        running clock
          -> observe RisingEdge + ReadOnly
          -> kill the sole clock task
          -> hold clock HIGH while simulation time advances
          -> restart the SAME Clock with start_high=False
          -> obtain a falling phase
          -> obtain the next rising edge normally

    No second clock owner may exist concurrently.

    DUT reset remains asserted because this test proves clock-driver
    semantics only, not architectural execution.
    """

    dut.clk.value = 0
    dut.reset.value = 1

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    await Timer(
        1,
        units="ns",
    )

    clock = Clock(
        dut.clk,
        CLOCK_NS,
        units="ns",
    )

    # ----------------------------------------------------------
    # First and only clock owner.
    # ----------------------------------------------------------
    first_task = cocotb.start_soon(
        clock.start()
    )

    await RisingEdge(
        dut.clk
    )

    await ReadOnly()

    assert signal_int(
        dut.clk
    ) == 1

    # ----------------------------------------------------------
    # Pause immediately after a rising edge.
    #
    # kill() synchronously unschedules the coroutine in cocotb 1.9.2.
    # ----------------------------------------------------------
    first_task.kill()

    assert first_task.done()

    paused_clk = signal_int(
        dut.clk
    )

    assert paused_clk == 1

    # Advance four half-periods. With no clock owner, clk must not move.
    await Timer(
        2 * CLOCK_NS,
        units="ns",
    )

    assert signal_int(
        dut.clk
    ) == paused_clk, (
        "clock changed while its sole driver task was killed"
    )

    # ----------------------------------------------------------
    # Resume.
    #
    # start_high=False is required because clk is currently HIGH.
    # The restarted task first drives LOW, then raises clk after one
    # half-period.
    # ----------------------------------------------------------
    second_task = cocotb.start_soon(
        clock.start(
            start_high=False
        )
    )

    # Give the newly scheduled coroutine time to perform its initial
    # LOW assignment without consuming a full half-period.
    await Timer(
        1,
        units="ns",
    )

    assert signal_int(
        dut.clk
    ) == 0, (
        "restarted clock did not enter the expected low phase"
    )

    # The next architectural edge must still be a normal rising edge.
    await RisingEdge(
        dut.clk
    )

    await ReadOnly()

    assert signal_int(
        dut.clk
    ) == 1

    # ----------------------------------------------------------
    # Kill the replacement owner too and prove the final state is stable.
    # ----------------------------------------------------------
    second_task.kill()

    assert second_task.done()

    await Timer(
        2 * CLOCK_NS,
        units="ns",
    )

    assert signal_int(
        dut.clk
    ) == 1, (
        "clock changed after replacement task was killed"
    )
