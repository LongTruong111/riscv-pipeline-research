import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from research.week5.impl.directed_cases import DIRECTED_CASES
from research.week5.impl.l1_coverage import L1CoverageCollector
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week7.hazard_attribution import (
    TimingObservation,
    correlate_hazard,
)
from research.week7.retire_monitor import (
    RetireMonitor,
    RetireTag,
)
from research.week7.timing_oracle_v1 import (
    build_timing_schedule_v1,
)


N_CYCLES = int(os.getenv("N_CYCLES", "60"))
ATTRIBUTION_CASE = os.getenv(
    "ATTRIBUTION_CASE",
    "",
).strip()


def signal_int(signal, name):
    try:
        return int(signal.value)
    except ValueError as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z value: "
            f"{signal.value}"
        ) from exc


async def reset_active_high(dut, cycles=3):
    dut.reset.value = 1

    for _ in range(cycles):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


def build_program(words):
    return {
        index * 4: instruction
        for index, instruction in enumerate(words)
    }


@cocotb.test()
async def test_live_hazard_attribution(dut):
    """
    Trace canonical L1 Intent hits through:

        L1 Intent
            -> Timing Oracle v1
            -> observed admission/control
            -> instruction_id
            -> observed retirement

    The expected timing model is constructed only from the canonical
    program. DUT-observed stall/forward/flush values are observations,
    never oracle inputs.
    """

    assert ATTRIBUTION_CASE in DIRECTED_CASES, (
        f"unknown ATTRIBUTION_CASE="
        f"{ATTRIBUTION_CASE!r}"
    )

    case = DIRECTED_CASES[ATTRIBUTION_CASE]

    schedule = build_timing_schedule_v1(
        build_program(case.words)
    )

    assert (
        schedule.instruction_count
        == case.expected_accepted
    )

    expected_by_id = {
        expectation.instruction_id: expectation
        for expectation in schedule.expectations
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
    l1_coverage = L1CoverageCollector()
    monitor = RetireMonitor()

    timing_observations = {}
    pending_hits = {}

    accepted_ids = []
    retired_ids = []

    attribution_results = []

    stall_cycles = 0
    flush_cycles = 0
    unsupported_cycles = 0

    for cycle in range(1, N_CYCLES + 1):
        # ----------------------------------------------------------
        # FALLING EDGE:
        # observe logical retirement for current D tag.
        # ----------------------------------------------------------
        await FallingEdge(dut.clk)
        await ReadOnly()

        current_d_tag = monitor.d_tag

        if current_d_tag is not None:
            d_instr = signal_int(
                dut.probe_d_instr,
                "probe_d_instr",
            )

            assert (
                d_instr
                == current_d_tag.instruction
            ), (
                f"{ATTRIBUTION_CASE}: "
                f"cycle={cycle}: "
                f"D identity mismatch for "
                f"instruction_id="
                f"{current_d_tag.instruction_id}"
            )

        retired = monitor.observe_falling_edge(
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

        if retired is not None:
            instruction_id = retired.instruction_id

            retired_ids.append(instruction_id)

            hits = pending_hits.pop(
                instruction_id,
                (),
            )

            for hit in hits:
                result = correlate_hazard(
                    hit,
                    expected_by_id[instruction_id],
                    timing_observations[
                        instruction_id
                    ],
                    retired,
                )

                attribution_results.append(result)

                failed = ",".join(
                    (
                        f"{check.name}:"
                        f"expected={check.expected},"
                        f"observed={check.observed}"
                    )
                    for check in result.failed_checks
                )

                dut._log.info(
                    "HAZARD_ATTRIBUTION "
                    f"case={ATTRIBUTION_CASE} "
                    f"bin={result.bin_id} "
                    f"producer_ids="
                    f"{','.join(str(value) for value in result.producer_instruction_ids) or 'none'} "
                    f"consumer_id="
                    f"{result.consumer_instruction_id} "
                    f"accept_cycle="
                    f"{timing_observations[instruction_id].accept_cycle} "
                    f"retire_cycle={retired.cycle} "
                    f"status="
                    f"{'PASS' if result.passed else 'FAIL'} "
                    f"failed={failed or 'none'}"
                )

                assert result.passed, (
                    f"{ATTRIBUTION_CASE}: "
                    f"{result.bin_id} attribution failed: "
                    f"{failed}"
                )

        # ----------------------------------------------------------
        # PRE-RISING-EDGE:
        # inspect admission eligibility.
        # ----------------------------------------------------------
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

        a_pc = signal_int(
            dut.probe_a_pc,
            "probe_a_pc",
        )

        a_instr = signal_int(
            dut.probe_a_instr,
            "probe_a_instr",
        )

        if stall:
            stall_cycles += 1

        if flush:
            flush_cycles += 1

        pending = adapter.observe_pre_edge(
            PreEdgeSnapshot(
                cycle=cycle,
                reset=reset,
                stall=stall,
                flush_redirect=flush,
                pc=a_pc,
                instruction=a_instr,
            )
        )

        if (
            pending is None
            and not reset
            and not stall
            and not flush
            and a_instr != 0
        ):
            unsupported_cycles += 1

        # ----------------------------------------------------------
        # RISING EDGE:
        # finalize accepted instruction and advance tags.
        # ----------------------------------------------------------
        await RisingEdge(dut.clk)
        await ReadOnly()

        if reset:
            monitor.reset()
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

            # Structural identity must agree before attribution.
            assert event.pc == expected.pc
            assert (
                event.instruction
                == expected.instruction
            )

            timing_observations[
                instruction_id
            ] = TimingObservation.from_execution_event(
                event
            )

            accepted_ids.append(instruction_id)

            # Frozen Intent classifier operates only on the
            # reconstructed executed-program stream.
            hits = l1_coverage.observe(event)

            if hits:
                pending_hits[
                    instruction_id
                ] = hits

            accepted_tag = (
                RetireTag.from_execution_event(
                    event
                )
            )

        monitor.advance_pipeline(
            accepted_tag
        )

    # --------------------------------------------------------------
    # FINAL ATTRIBUTION INVARIANTS
    # --------------------------------------------------------------
    expected_ids = list(
        range(
            1,
            schedule.instruction_count + 1,
        )
    )

    assert unsupported_cycles == 0

    assert accepted_ids == expected_ids
    assert retired_ids == expected_ids

    assert (
        monitor.retired_count
        == schedule.instruction_count
    )

    assert monitor.stage_instruction_ids == (
        None,
        None,
        None,
    )

    # Every Intent hit must have reached retirement and therefore
    # been consumed by the attribution layer.
    assert pending_hits == {}, (
        f"unretired attribution hits remain: "
        f"{pending_hits}"
    )

    assert attribution_results, (
        f"{ATTRIBUTION_CASE}: no L1 Intent "
        "attribution was produced"
    )

    attributed_bins = {
        result.bin_id
        for result in attribution_results
    }

    assert case.target_bin in attributed_bins, (
        f"{ATTRIBUTION_CASE}: target bin "
        f"{case.target_bin} was not attributed; "
        f"got {sorted(attributed_bins)}"
    )

    assert all(
        result.passed
        for result in attribution_results
    )

    expected_has_redirect = any(
        item.redirect
        for item in schedule.expectations
    )

    if expected_has_redirect:
        assert flush_cycles > 0
    else:
        assert flush_cycles == 0

    dut._log.info(
        "HAZARD_ATTRIBUTION_SUMMARY "
        f"case={ATTRIBUTION_CASE} "
        f"target_bin={case.target_bin} "
        f"accepted={len(accepted_ids)} "
        f"retired={len(retired_ids)} "
        f"attributions="
        f"{len(attribution_results)} "
        f"bins="
        f"{','.join(sorted(attributed_bins))} "
        f"stall_cycles={stall_cycles} "
        f"flush_cycles={flush_cycles} "
        f"status=PASS"
    )
