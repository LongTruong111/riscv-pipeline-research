import os
import time

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

from timing_utils import make_clock, reset_active_low


N_CYCLES = int(os.getenv("N_CYCLES", "100000"))


async def setup(dut):
    clock = make_clock(dut.clk, 10)
    cocotb.start_soon(clock.start())

    dut.en.value = 0
    await reset_active_low(dut, cycles=3)

    dut.en.value = 1


def report(mode: str, cycles: int, elapsed: float):
    if elapsed <= 0.0:
        raise RuntimeError("Non-positive benchmark elapsed time")

    throughput = cycles / elapsed

    print(
        f"THROUGHPUT_RESULT "
        f"mode={mode} "
        f"cycles={cycles} "
        f"wall_s={elapsed:.6f} "
        f"cycles_per_s={throughput:.3f}"
    )


@cocotb.test()
async def test_baseline(dut):
    """
    Verilator+Cocotb baseline.

    One coroutine wake-up per rising edge.
    No signal monitor/read is executed inside the measurement loop.
    """
    await setup(dut)

    start = time.perf_counter()

    for _ in range(N_CYCLES):
        await RisingEdge(dut.clk)

    elapsed = time.perf_counter() - start

    report("baseline", N_CYCLES, elapsed)


@cocotb.test()
async def test_simple_monitor(dut):
    """
    Baseline plus one settled signal observation per cycle.

    This approximates the incremental scheduler/read overhead of a
    simple Cocotb monitor without per-cycle disk or console logging.
    """
    await setup(dut)

    checksum = 0
    start = time.perf_counter()

    for _ in range(N_CYCLES):
        await RisingEdge(dut.clk)
        await ReadOnly()
        checksum ^= int(dut.count.value)

    elapsed = time.perf_counter() - start

    report("simple_monitor", N_CYCLES, elapsed)

    # Prevent the sampled value from becoming semantically irrelevant.
    assert checksum >= 0
