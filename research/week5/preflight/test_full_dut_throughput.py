import os
import time

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ReadOnly


N_CYCLES = int(os.getenv("N_CYCLES", "100000"))


async def reset_active_high(dut, cycles=3):
    """
    Frozen DUT reset convention:
    reset=1 asserts reset, reset=0 releases reset.
    """
    dut.reset.value = 1

    for _ in range(cycles):
        await RisingEdge(dut.clk)

    # Release away from the active rising sampling edge.
    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


async def setup(dut):
    dut.clk.value = 0

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_active_high(dut, cycles=3)


def report(mode, cycles, elapsed):
    if elapsed <= 0:
        raise RuntimeError("Non-positive benchmark elapsed time")

    throughput = cycles / elapsed

    print(
        f"FULL_DUT_THROUGHPUT "
        f"mode={mode} "
        f"cycles={cycles} "
        f"wall_s={elapsed:.6f} "
        f"cycles_per_s={throughput:.3f}"
    )


@cocotb.test()
async def test_full_dut_baseline(dut):
    """
    Full RTL DUT baseline.

    One Cocotb wake-up per rising edge.
    No per-cycle DUT signal sampling inside the measured loop.
    """
    await setup(dut)

    start = time.perf_counter()

    for _ in range(N_CYCLES):
        await RisingEdge(dut.clk)

    elapsed = time.perf_counter() - start

    report("baseline", N_CYCLES, elapsed)


@cocotb.test()
async def test_full_dut_simple_monitor(dut):
    """
    Full DUT with lightweight settled signal sampling.

    No per-cycle console or disk logging.
    """
    await setup(dut)

    last_sample = None

    start = time.perf_counter()

    for _ in range(N_CYCLES):
        await RisingEdge(dut.clk)
        await ReadOnly()

        # Read exposed architectural/memory-interface signals.
        # Keep BinaryValue objects directly so unknown values, if any,
        # do not cause integer-conversion failures.
        last_sample = (
            dut.reg_write_sig.value,
            dut.reg_num.value,
            dut.WB_Data.value,
            dut.wr.value,
            dut.rd.value,
            dut.addr.value,
        )

    elapsed = time.perf_counter() - start

    if last_sample is None:
        raise RuntimeError("Monitor did not collect any sample")

    report("simple_monitor", N_CYCLES, elapsed)
