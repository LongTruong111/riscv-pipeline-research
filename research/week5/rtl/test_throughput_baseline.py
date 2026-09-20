import os
import time

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge


BENCH_CYCLES = int(
    os.getenv("BENCH_CYCLES", "100000")
)

BENCH_MODE = os.getenv(
    "BENCH_MODE",
    "minimal",
).strip().lower()


@cocotb.test()
async def test_throughput_baseline(dut):
    if BENCH_MODE not in {
        "minimal",
        "monitor",
    }:
        raise ValueError(
            f"unsupported BENCH_MODE={BENCH_MODE}"
        )

    dut.clk.value = 0

    clock = Clock(
        dut.clk,
        10,
        units="ns",
    )

    cocotb.start_soon(clock.start())

    # Preserve frozen reset timing convention.
    dut.reset.value = 1

    for _ in range(3):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()

    checksum = 0

    start = time.perf_counter()

    for _ in range(BENCH_CYCLES):
        await RisingEdge(dut.clk)

        if BENCH_MODE == "monitor":
            await ReadOnly()

            checksum ^= int(
                dut.probe_stall.value
            )

            checksum ^= (
                int(dut.probe_flush.value)
                << 1
            )

            checksum ^= (
                int(dut.probe_fwd_a.value)
                << 2
            )

            checksum ^= (
                int(dut.probe_fwd_b.value)
                << 4
            )

    elapsed = time.perf_counter() - start

    cycles_per_second = (
        BENCH_CYCLES / elapsed
    )

    dut._log.info(
        "THROUGHPUT_RESULT "
        f"mode={BENCH_MODE} "
        f"cycles={BENCH_CYCLES} "
        f"elapsed_s={elapsed:.6f} "
        f"cycles_per_second="
        f"{cycles_per_second:.3f} "
        f"checksum={checksum}"
    )
