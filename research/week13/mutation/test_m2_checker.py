import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from research.week5.impl.directed_cases import DIRECTED_CASES
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week12.telemetry.first_failure import (
    FailureRecord,
    FirstFailureRecorder,
)


TARGET_ID = 2
N_CYCLES = int(os.getenv("N_CYCLES", "20"))


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


def write_result(path, payload):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@cocotb.test()
async def test_m2_x0_forwarding_exclusion(dut):
    mode = os.getenv("WEEK13_M2_MODE")
    result_path = os.getenv("WEEK13_M2_RESULT_PATH")

    assert mode in {"canonical", "mutant"}
    assert result_path

    case = DIRECTED_CASES["T18"]

    assert case.target_bin == "H18"
    assert case.expected_accepted == 2
    assert len(case.words) == 2

    producer = case.words[0]
    consumer = case.words[1]

    # Static proof that the frozen T18 fixture activates the intended
    # x0 forwarding-exclusion condition.
    assert ((producer >> 7) & 0x1F) == 0
    assert ((consumer >> 15) & 0x1F) == 0

    dut.clk.value = 0
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_active_high(dut)

    adapter = ExecutionEventAdapter()
    first_failure = FirstFailureRecorder()

    accepted_ids = []

    target_activation_count = 0
    checker_failure_count = 0

    target_forward_a = None
    target_cycle = None
    target_pc = None

    for cycle in range(1, N_CYCLES + 1):
        await FallingEdge(dut.clk)
        await ReadOnly()

        reset = bool(signal_int(dut.reset, "reset"))
        stall = bool(signal_int(dut.probe_stall, "probe_stall"))
        flush = bool(signal_int(dut.probe_flush, "probe_flush"))

        pending = adapter.observe_pre_edge(
            PreEdgeSnapshot(
                cycle=cycle,
                reset=reset,
                stall=stall,
                flush_redirect=flush,
                pc=signal_int(dut.probe_a_pc, "probe_a_pc"),
                instruction=signal_int(
                    dut.probe_a_instr,
                    "probe_a_instr",
                ),
            )
        )

        await RisingEdge(dut.clk)
        await ReadOnly()

        if reset:
            continue

        if pending is None:
            continue

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

        accepted_ids.append(event.instruction_index)

        if event.instruction_index != TARGET_ID:
            continue

        # Frozen H18 control-realization requirement:
        # rd=x0 must not become a forwarding dependency.
        target_activation_count += 1
        target_forward_a = event.forward_a
        target_cycle = event.cycle
        target_pc = event.pc

        expected_forward_a = 0b00

        if event.forward_a != expected_forward_a:
            checker_failure_count += 1

            first_failure.record(
                "control",
                FailureRecord(
                    instruction_id=event.instruction_index,
                    cycle=event.cycle,
                    pc=event.pc,
                    instruction=event.instruction,
                    checker="week5_h18_control",
                    check_name="forward_a_x0_exclusion",
                    expected=expected_forward_a,
                    observed=event.forward_a,
                    forward_a=event.forward_a,
                    forward_b=event.forward_b,
                    stall_cycles_before_accept=(
                        event.stall_cycles_before_accept
                    ),
                ),
            )

        break

    first = first_failure.first_failure

    payload = {
        "mode": mode,
        "accepted_instruction_ids": accepted_ids,
        "target_activation_count": target_activation_count,
        "checker_failure_count": checker_failure_count,
        "target_instruction_id": TARGET_ID,
        "target_cycle": target_cycle,
        "target_pc": target_pc,
        "target_forward_a": target_forward_a,
        "authoritative_expected_forward_a": 0,
        "first_failure": (
            None if first is None else first.to_dict()
        ),
    }

    write_result(result_path, payload)

    assert accepted_ids[:2] == [1, 2]
    assert target_activation_count == 1

    if mode == "canonical":
        assert checker_failure_count == 0
        assert target_forward_a == 0b00
        assert first is None

    else:
        assert checker_failure_count == 1
        assert target_forward_a == 0b10

        assert first is not None
        assert first.checker == "week5_h18_control"
        assert first.check_name == "forward_a_x0_exclusion"
        assert first.expected == 0b00
        assert first.observed == 0b10

    dut._log.info(
        "WEEK13_M2 "
        f"mode={mode} "
        f"target_activations={target_activation_count} "
        f"checker_failures={checker_failure_count} "
        f"forward_a={target_forward_a:02b}"
    )
