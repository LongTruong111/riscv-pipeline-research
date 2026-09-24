import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week9.benchmark.streaming_timing import (
    StreamingTimingOracleV1,
)
from research.week11.integrated_sequence import (
    WEEK11_INTEGRATED_INSTRUCTION_COUNT,
    build_week11_integrated_sequence,
)


TARGET = WEEK11_INTEGRATED_INSTRUCTION_COUNT
MAX_CYCLES = 120


def signal_int(signal, name):
    try:
        return int(signal.value)
    except (TypeError, ValueError) as exc:
        raise AssertionError(
            f"{name} is not a known integer: {signal.value}"
        ) from exc


async def reset_active_high(dut):
    dut.reset.value = 1

    for _ in range(3):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


@cocotb.test()
async def test_m1_exmem_forward_a_target_is_activated(dut):
    words = tuple(
        build_week11_integrated_sequence()
    )

    assert len(words) == TARGET
    assert TARGET == 50

    program = {
        index * 4: word
        for index, word in enumerate(words)
    }

    clock = Clock(
        dut.clk,
        10,
        units="ns",
    )

    cocotb.start_soon(clock.start())

    await reset_active_high(dut)

    adapter = ExecutionEventAdapter()
    timing_oracle = StreamingTimingOracleV1(
        program
    )

    accepted_count = 0

    target_activation_count = 0
    target_suppressed_count = 0
    observed_forward_a_10_count = 0

    first_target_instruction_id = None
    first_target_pc = None

    for cycle in range(1, MAX_CYCLES + 1):
        await FallingEdge(dut.clk)
        await ReadOnly()

        pending = adapter.observe_pre_edge(
            PreEdgeSnapshot(
                cycle=cycle,
                reset=signal_int(
                    dut.reset,
                    "reset",
                ),
                stall=signal_int(
                    dut.probe_stall,
                    "probe_stall",
                ),
                flush_redirect=signal_int(
                    dut.probe_flush,
                    "probe_flush",
                ),
                pc=signal_int(
                    dut.probe_a_pc,
                    "probe_a_pc",
                ),
                instruction=signal_int(
                    dut.probe_a_instr,
                    "probe_a_instr",
                ),
            )
        )

        await RisingEdge(dut.clk)
        await ReadOnly()

        if pending is None:
            continue

        observed_b_pc = signal_int(
            dut.probe_b_pc,
            "probe_b_pc",
        )

        observed_b_instr = signal_int(
            dut.probe_b_instr,
            "probe_b_instr",
        )

        assert observed_b_pc == pending.pc, (
            "accepted B-stage PC mismatch: "
            f"pending=0x{pending.pc:03x}, "
            f"observed=0x{observed_b_pc:03x}"
        )

        assert observed_b_instr == pending.instruction, (
            "accepted B-stage instruction mismatch: "
            f"pending=0x{pending.instruction:08x}, "
            f"observed=0x{observed_b_instr:08x}"
        )

        event = adapter.finalize_post_edge(
            pending,
            forward_a=signal_int(
                dut.probe_fwd_a,
                "probe_fwd_a",
            ),
            forward_b=signal_int(
                dut.probe_fwd_b,
                "probe_fwd_b",
            ),
        )

        accepted_count += 1

        assert event.instruction_index == accepted_count

        expectation = timing_oracle.observe_accept(
            event
        )

        # Mutation target activation is defined independently
        # from the mutant's observed output.
        if expectation.forward_a == 0b10:
            target_activation_count += 1

            if first_target_instruction_id is None:
                first_target_instruction_id = (
                    event.instruction_index
                )
                first_target_pc = event.pc

            if event.forward_a != 0b10:
                target_suppressed_count += 1

        if event.forward_a == 0b10:
            observed_forward_a_10_count += 1

        if accepted_count == TARGET:
            break

    assert accepted_count == TARGET, (
        "integrated-50 workload did not complete: "
        f"accepted={accepted_count}"
    )

    assert target_activation_count > 0, (
        "M1 target never activated: workload does not "
        "exercise canonical EX/MEM -> Forward_A"
    )

    # This mutant has no code path capable of generating
    # Forward_A=10. Every independently predicted EX/MEM Forward_A
    # activation must therefore be suppressed.
    assert observed_forward_a_10_count == 0, (
        "M1 mutant unexpectedly emitted Forward_A=10"
    )

    assert (
        target_suppressed_count
        == target_activation_count
    ), (
        "not every M1 target activation was suppressed"
    )

    assert first_target_instruction_id is not None
    assert first_target_pc is not None

    dut._log.info(
        "WEEK12_M1_ACTIVATION "
        f"accepted={accepted_count} "
        f"target_activations={target_activation_count} "
        f"target_suppressed={target_suppressed_count} "
        f"observed_forward_a_10="
        f"{observed_forward_a_10_count} "
        f"first_target_instruction_id="
        f"{first_target_instruction_id} "
        f"first_target_pc=0x{first_target_pc:03x}"
    )
