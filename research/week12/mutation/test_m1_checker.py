import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import (
    FallingEdge,
    ReadOnly,
    RisingEdge,
)

from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week7.retire_monitor import (
    RetireMonitor,
    RetireTag,
)
from research.week7.timing_oracle_v1 import (
    build_timing_schedule_v1,
)
from research.week11.integrated_sequence import (
    WEEK11_INTEGRATED_INSTRUCTION_COUNT,
    build_week11_integrated_sequence,
)
from research.week12.telemetry.first_failure import (
    FailureRecord,
    FirstFailureRecorder,
)


TARGET = WEEK11_INTEGRATED_INSTRUCTION_COUNT
N_CYCLES = int(
    os.getenv("N_CYCLES", "90")
)


def signal_int(signal, name):
    try:
        return int(signal.value)
    except (TypeError, ValueError) as exc:
        raise AssertionError(
            f"{name} is not a known integer: "
            f"{signal.value}"
        ) from exc


def build_program(words):
    return {
        index * 4: instruction
        for index, instruction in enumerate(words)
    }


async def reset_active_high(dut):
    dut.reset.value = 1

    for _ in range(3):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


def write_raw_result(path, payload):
    output = Path(path)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )


@cocotb.test()
async def test_m1_authoritative_checker_catches_mutant(
    dut,
):
    result_path = os.getenv(
        "WEEK12_M1_RESULT_PATH"
    )

    assert result_path, (
        "WEEK12_M1_RESULT_PATH is required"
    )

    words = tuple(
        build_week11_integrated_sequence()
    )

    assert len(words) == TARGET
    assert TARGET == 50

    schedule = build_timing_schedule_v1(
        build_program(words),
        max_instructions=TARGET,
    )

    assert schedule.instruction_count == TARGET

    expected_by_id = {
        item.instruction_id: item
        for item in schedule.expectations
    }

    dut.clk.value = 0

    clock = Clock(
        dut.clk,
        10,
        units="ns",
    )

    cocotb.start_soon(clock.start())

    await reset_active_high(dut)

    adapter = ExecutionEventAdapter()
    retire_monitor = RetireMonitor()
    first_failure = FirstFailureRecorder()

    observed_accept_ids = []
    observed_retire_ids = []

    observed_stall_cycles = 0
    observed_flush_cycles = 0

    target_activation_count = 0
    target_suppressed_count = 0
    checker_failure_count = 0

    observed_forward_a_10_count = 0

    first_target_instruction_id = None
    first_target_pc = None

    for cycle in range(
        1,
        N_CYCLES + 1,
    ):
        await FallingEdge(dut.clk)
        await ReadOnly()

        d_tag = retire_monitor.d_tag

        if d_tag is not None:
            d_instr = signal_int(
                dut.probe_d_instr,
                "probe_d_instr",
            )

            assert d_instr == d_tag.instruction, (
                "D-stage identity mismatch: "
                f"instruction_id="
                f"{d_tag.instruction_id}"
            )

        retired = (
            retire_monitor.observe_falling_edge(
                cycle=cycle,
                regwrite=bool(
                    signal_int(
                        dut.reg_write_sig,
                        "reg_write_sig",
                    )
                ),
                rd=signal_int(
                    dut.reg_num,
                    "reg_num",
                ),
                wdata=signal_int(
                    dut.reg_data,
                    "reg_data",
                ),
            )
        )

        if retired is not None:
            expected = expected_by_id[
                retired.instruction_id
            ]

            assert (
                retired.cycle
                == expected.retire_cycle
            ), (
                "retire cycle mismatch: "
                f"instruction_id="
                f"{retired.instruction_id}, "
                f"expected="
                f"{expected.retire_cycle}, "
                f"observed={retired.cycle}"
            )

            observed_retire_ids.append(
                retired.instruction_id
            )

        reset = bool(
            signal_int(
                dut.reset,
                "reset",
            )
        )

        stall = bool(
            signal_int(
                dut.probe_stall,
                "probe_stall",
            )
        )

        flush = bool(
            signal_int(
                dut.probe_flush,
                "probe_flush",
            )
        )

        if stall:
            observed_stall_cycles += 1

        if flush:
            observed_flush_cycles += 1

        pending = adapter.observe_pre_edge(
            PreEdgeSnapshot(
                cycle=cycle,
                reset=reset,
                stall=stall,
                flush_redirect=flush,
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

        if reset:
            retire_monitor.reset()
            continue

        accepted_tag = None

        if pending is not None:
            b_pc = signal_int(
                dut.probe_b_pc,
                "probe_b_pc",
            )

            b_instr = signal_int(
                dut.probe_b_instr,
                "probe_b_instr",
            )

            assert b_pc == pending.pc
            assert b_instr == pending.instruction

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

            instruction_id = (
                event.instruction_index
            )

            assert instruction_id in expected_by_id

            expected = expected_by_id[
                instruction_id
            ]

            assert event.pc == expected.pc
            assert (
                event.instruction
                == expected.instruction
            )
            assert (
                event.cycle
                == expected.accept_cycle
            )
            assert (
                event.stall_cycles_before_accept
                == expected.stall_cycles_before_accept
            )

            # Forward_B is outside M1 and must remain exact.
            assert (
                event.forward_b
                == expected.forward_b
            ), (
                "unexpected Forward_B mismatch: "
                f"instruction_id={instruction_id}"
            )

            target_active = (
                expected.forward_a == 0b10
            )

            if target_active:
                target_activation_count += 1

                if (
                    first_target_instruction_id
                    is None
                ):
                    first_target_instruction_id = (
                        instruction_id
                    )
                    first_target_pc = event.pc

            if event.forward_a == 0b10:
                observed_forward_a_10_count += 1

            if (
                event.forward_a
                != expected.forward_a
            ):
                # Any Forward_A mismatch outside the
                # independently identified mutation target
                # is not a valid M1 kill.
                assert target_active, (
                    "unexpected non-target "
                    "Forward_A mismatch: "
                    f"instruction_id="
                    f"{instruction_id}, "
                    f"expected="
                    f"{expected.forward_a:02b}, "
                    f"observed="
                    f"{event.forward_a:02b}"
                )

                failure = FailureRecord(
                    instruction_id=instruction_id,
                    cycle=event.cycle,
                    pc=event.pc,
                    instruction=event.instruction,
                    checker=(
                        "week11_integrated_timing"
                    ),
                    check_name="forward_a",
                    expected=expected.forward_a,
                    observed=event.forward_a,
                    forward_a=event.forward_a,
                    forward_b=event.forward_b,
                    stall_cycles_before_accept=(
                        event
                        .stall_cycles_before_accept
                    ),
                )

                # Evidence is recorded before the mutation
                # verdict is evaluated.
                first_failure.record(
                    "control",
                    failure,
                )

                checker_failure_count += 1
                target_suppressed_count += 1

            observed_accept_ids.append(
                instruction_id
            )

            accepted_tag = (
                RetireTag.from_execution_event(
                    event
                )
            )

        retire_monitor.advance_pipeline(
            accepted_tag
        )

    expected_ids = list(
        range(1, TARGET + 1)
    )

    # Stream/timing integrity remains mandatory.
    assert observed_accept_ids == expected_ids
    assert observed_retire_ids == expected_ids

    assert retire_monitor.retired_count == TARGET

    assert (
        retire_monitor.stage_instruction_ids
        == (None, None, None)
    )

    assert (
        observed_stall_cycles
        == schedule.total_stall_cycles
    )

    assert observed_flush_cycles == 0

    first = first_failure.first_failure

    raw_result = {
        "accepted_instructions": len(
            observed_accept_ids
        ),
        "retired_instructions": len(
            observed_retire_ids
        ),
        "target_activation_count": (
            target_activation_count
        ),
        "target_suppressed_count": (
            target_suppressed_count
        ),
        "checker_failure_count": (
            checker_failure_count
        ),
        "observed_forward_a_10_count": (
            observed_forward_a_10_count
        ),
        "first_target_instruction_id": (
            first_target_instruction_id
        ),
        "first_target_pc": first_target_pc,
        "first_failure": (
            None
            if first is None
            else first.to_dict()
        ),
        "first_control_failure": (
            None
            if first_failure
            .first_control_failure
            is None
            else first_failure
            .first_control_failure
            .to_dict()
        ),
    }

    # Persist structured evidence before evaluating
    # the expected mutation-kill verdict.
    write_raw_result(
        result_path,
        raw_result,
    )

    assert target_activation_count > 0, (
        "M1 target was never activated"
    )

    assert checker_failure_count > 0, (
        "authoritative checker did not catch M1"
    )

    assert (
        target_suppressed_count
        == target_activation_count
    )

    assert observed_forward_a_10_count == 0

    assert first is not None
    assert (
        first_failure.first_control_failure
        == first
    )

    assert first.check_name == "forward_a"

    assert (
        first.instruction_id
        == first_target_instruction_id
    )

    dut._log.info(
        "WEEK12_M1_CHECKER "
        f"accepted="
        f"{len(observed_accept_ids)} "
        f"retired="
        f"{len(observed_retire_ids)} "
        f"target_activations="
        f"{target_activation_count} "
        f"checker_failures="
        f"{checker_failure_count} "
        f"first_failure_instruction_id="
        f"{first.instruction_id} "
        f"first_failure_cycle="
        f"{first.cycle} "
        f"expected_forward_a="
        f"{first.expected:02b} "
        f"observed_forward_a="
        f"{first.observed:02b}"
    )
