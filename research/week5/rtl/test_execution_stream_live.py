import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week5.impl.commit_scoreboard import (
    CommitScoreboard,
    StoreObservation,
    WritebackObservation,
)

from research.week5.impl.coverage_model import L2CoverageCollector
from research.week5.impl.l1_coverage import L1CoverageCollector
from research.week5.impl.realization_checker import (
    L1ControlRealizationChecker,
)
from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)

from research.week5.impl.validated_coverage import (
    L1ValidatedCoverageCollector,
)

N_CYCLES = int(os.getenv("N_CYCLES", "120"))

EXPECT_STALL = os.getenv("EXPECT_STALL", "0") == "1"
EXPECT_FLUSH = os.getenv("EXPECT_FLUSH", "0") == "1"
EXPECT_ACCEPTED = int(os.getenv("EXPECT_ACCEPTED", "0"))
EXPECT_L1_BIN = os.getenv("EXPECT_L1_BIN", "").strip()

def signal_int(signal, name):
    """
    Convert a settled DUT signal to int.

    Raise a useful assertion if the signal contains unresolved X/Z bits.
    """
    try:
        return int(signal.value)
    except ValueError as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z value: {signal.value}"
        ) from exc


async def reset_active_high(dut, cycles=3):
    """
    Frozen DUT reset convention:

        reset = 1 -> asserted
        reset = 0 -> released

    Reset is released at FallingEdge so it is stable before the next
    active RisingEdge.
    """
    dut.reset.value = 1

    for _ in range(cycles):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


@cocotb.test()
async def test_live_execution_stream_reconstruction(dut):
    """
    Validate ExecutionEvent reconstruction against the frozen live RTL.

    This test validates the execution-stream foundation only. It does not
    attempt L1 or L2 closure.

    Checked properties include:

    - stalled IF/ID instructions do not immediately create ExecutionEvents;
    - flushed IF/ID instructions do not create ExecutionEvents;
    - accepted instructions increment executed-program-order index once;
    - accepted A-stage PC/instruction match the following B-stage state;
    - forwarding selectors are sampled after RisingEdge + ReadOnly;
    - the L2 collector accepts the reconstructed contiguous event stream.
    """

    dut.clk.value = 0

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_active_high(dut)

    adapter = ExecutionEventAdapter()
    coverage = L2CoverageCollector()
    l1_coverage = L1CoverageCollector()
    control_checker = L1ControlRealizationChecker()

    architectural_model = RV32ArchitecturalModel()
    commit_scoreboard = CommitScoreboard()
    validated_coverage = L1ValidatedCoverageCollector()

    events_by_index = {}
    steps_by_index = {}

    # Verification-side pipeline identity.
    #
    # These tags represent accepted ExecutionEvent indices, not raw
    # Curr_Instr values.
    b_tag = None
    c_tag = None
    d_tag = None

    control_checks = 0
    control_passes = 0
    control_failures = 0
    control_failed_bins = set()
    architectural_checks = 0
    architectural_passes = 0
    architectural_failures = 0
    architectural_failure_kinds = set()
    accepted_events = 0
    accepted_after_stall = 0

    stall_cycles = 0
    flush_cycles = 0
    unsupported_cycles = 0

    def record_validation_outcomes(outcomes):
        for outcome in outcomes:
            if outcome.validated:
                dut._log.info(
                    "L1_VALIDATED_HIT "
                    f"bin={outcome.bin_id} "
                    f"consumer_index="
                    f"{outcome.consumer_instruction_index} "
                    f"producer_indices="
                    f"{','.join(str(index) for index in outcome.producer_instruction_indices) or 'none'}"
                )
                continue

            if not outcome.control_passed:
                reason = "control"
            elif outcome.architectural_passed is False:
                reason = "architectural"
            else:
                reason = "unknown"

            failed_arch = ",".join(
                (
                    f"{instruction_index}:{kind}"
                )
                for instruction_index, kind
                in outcome.failed_architectural_checks
            ) or "none"

            dut._log.info(
                "L1_VALIDATION_REJECT "
                f"bin={outcome.bin_id} "
                f"consumer_index="
                f"{outcome.consumer_instruction_index} "
                f"reason={reason} "
                f"failed_arch={failed_arch}"
            )

    def record_architectural_result(result):
        nonlocal architectural_checks
        nonlocal architectural_passes
        nonlocal architectural_failures

        architectural_checks += 1

        if result.passed:
            architectural_passes += 1
        else:
            architectural_failures += 1
            architectural_failure_kinds.add(result.kind)

            failed_text = ",".join(
                (
                    f"{check.name}:"
                    f"expected={check.expected:#x},"
                    f"observed={check.observed:#x}"
                )
                for check in result.failed_checks
            )

            dut._log.warning(
                "ARCHITECTURAL_REALIZATION_FAIL "
                f"kind={result.kind} "
                f"instruction_index={result.instruction_index} "
                f"checks={failed_text}"
            )

        outcomes = validated_coverage.record_architectural_result(
            instruction_index=result.instruction_index,
            kind=result.kind,
            passed=result.passed,
        )

        record_validation_outcomes(outcomes)

    for cycle in range(1, N_CYCLES + 1):
        # --------------------------------------------------------------
        # PRE-EDGE SNAPSHOT
        #
        # Frozen timing contract:
        #
        #   FallingEdge(clk)
        #   -> ReadOnly()
        #
        # Observe IF/ID state and control intent before the next active
        # pipeline edge.
        # --------------------------------------------------------------
        await FallingEdge(dut.clk)
        await ReadOnly()
        # --------------------------------------------------------------
        # ARCHITECTURAL COMMIT OBSERVATION
        #
        # Core FallingEdge corresponds to:
        #
        #   - Register File write using the current D stage;
        #   - Data RAM write because ramOnChipData sees posedge(~clk).
        #
        # Pipeline tags still refer to the stages established by the
        # previous RisingEdge.
        # --------------------------------------------------------------

        if d_tag is not None:
            step = steps_by_index[d_tag]

            d_instr = signal_int(
                dut.probe_d_instr,
                "probe_d_instr",
            )

            assert d_instr == step.instruction, (
                f"cycle={cycle}: D-stage identity mismatch for "
                f"instruction_index={d_tag}: "
                f"expected {step.instruction:#010x}, "
                f"got {d_instr:#010x}"
            )

            wb_result = commit_scoreboard.check_writeback(
                step,
                WritebackObservation(
                    instruction_index=d_tag,
                    write_enable=bool(
                        signal_int(
                            dut.reg_write_sig,
                            "reg_write_sig",
                        )
                    ),
                    rd=signal_int(
                        dut.reg_num,
                        "reg_num",
                    ),
                    data=signal_int(
                        dut.reg_data,
                        "reg_data",
                    ),
                    instruction=d_instr,
                ),
            )

            record_architectural_result(wb_result)

            x0_result = commit_scoreboard.check_x0(
                instruction_index=d_tag,
                observed_value=signal_int(
                    dut.probe_x0,
                    "probe_x0",
                ),
            )

            record_architectural_result(x0_result)
            # D is the last pipeline stage needed by the live scoreboard.
            # Architectural evidence has already been copied into the
            # validated-coverage tracker.
            steps_by_index.pop(
                d_tag,
                None,
            )
        if c_tag is not None:
            step = steps_by_index[c_tag]

            c_instr = signal_int(
                dut.probe_c_instr,
                "probe_c_instr",
            )

            assert c_instr == step.instruction, (
                f"cycle={cycle}: C-stage identity mismatch for "
                f"instruction_index={c_tag}: "
                f"expected {step.instruction:#010x}, "
                f"got {c_instr:#010x}"
            )

            store_result = commit_scoreboard.check_store(
                step,
                StoreObservation(
                    instruction_index=c_tag,
                    write_enable=bool(
                        signal_int(
                            dut.mem_wr,
                            "mem_wr",
                        )
                    ),
                    address=signal_int(
                        dut.mem_addr,
                        "mem_addr",
                    ),
                    data=signal_int(
                        dut.mem_wr_data,
                        "mem_wr_data",
                    ),
                    instruction=c_instr,
                ),
            )

            record_architectural_result(store_result)

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

        before_count = adapter.instruction_count

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

        # A stalled or flushed IF/ID instruction must not be admitted into
        # the executed instruction stream on this edge.
        if stall or flush:
            assert pending is None, (
                f"cycle={cycle}: stall/flush incorrectly admitted "
                f"instruction {a_instr:#010x}"
            )

        # --------------------------------------------------------------
        # POST-EDGE SETTLED OBSERVATION
        #
        # Frozen timing contract:
        #
        #   RisingEdge(clk)
        #   -> ReadOnly()
        #
        # At this point sequential pipeline state is settled.
        # --------------------------------------------------------------
        await RisingEdge(dut.clk)
        await ReadOnly()
        # Verification-side pipeline identity follows the same sequential
        # movement as the DUT:
        #
        #     old C -> new D
        #     old B -> new C
        #     accepted A -> new B
        #
        # new B remains None until a pending admission is finalized below.
        d_tag = c_tag
        c_tag = b_tag
        b_tag = None
        # Frozen Datapath injects a functional ID/EX bubble when reset,
        # Reg_Stall, or PcSel is active.
        #
        # B.Curr_Instr cannot be used as a valid bit because the RTL retains
        # this debug instruction field even when its functional controls are
        # cleared.
        if stall or flush:
            b_control_nonzero = signal_int(
                dut.probe_b_control_nonzero,
                "probe_b_control_nonzero",
            )

            assert b_control_nonzero == 0, (
                f"cycle={cycle}: expected functional ID/EX bubble after "
                f"stall/flush, but B controls are non-zero"
            )

        # No instruction was accepted on this cycle.
        if pending is None:
            assert adapter.instruction_count == before_count, (
                f"cycle={cycle}: instruction_count changed without "
                f"an accepted instruction"
            )

            if (
                not reset
                and not stall
                and not flush
                and a_instr != 0
            ):
                unsupported_cycles += 1

            continue

        # --------------------------------------------------------------
        # ACCEPTED INSTRUCTION VALIDATION
        #
        # The instruction observed in A before the edge must now be present
        # in B after the edge.
        # --------------------------------------------------------------
        b_pc = signal_int(
            dut.probe_b_pc,
            "probe_b_pc",
        )

        b_instr = signal_int(
            dut.probe_b_instr,
            "probe_b_instr",
        )

        assert b_pc == pending.pc, (
            f"cycle={cycle}: ID/EX PC mismatch: "
            f"expected {pending.pc:#05x}, "
            f"got {b_pc:#05x}"
        )

        assert b_instr == pending.instruction, (
            f"cycle={cycle}: ID/EX instruction mismatch: "
            f"expected {pending.instruction:#010x}, "
            f"got {b_instr:#010x}"
        )

        # Forwarding signals are meaningful for the instruction now
        # resident in ID/EX and are sampled only after settled ReadOnly.
        fwd_a = signal_int(
            dut.probe_fwd_a,
            "probe_fwd_a",
        )

        fwd_b = signal_int(
            dut.probe_fwd_b,
            "probe_fwd_b",
        )

        event = adapter.finalize_post_edge(
            pending,
            forward_a=fwd_a,
            forward_b=fwd_b,
        )

        # The accepted instruction now owns the verification-side B tag.
        b_tag = event.instruction_index

        # Independent sequential architectural oracle.
        architectural_step = architectural_model.step(event)

        steps_by_index[event.instruction_index] = architectural_step

        pc_result = commit_scoreboard.check_pc(
            architectural_step
        )

        record_architectural_result(pc_result)

        if event.stall_cycles_before_accept > 0:
            accepted_after_stall += 1

        accepted_events += 1

        # Executed-program-order index must be contiguous and independent
        # of raw cycle count.
        assert event.instruction_index == accepted_events, (
            f"cycle={cycle}: expected instruction_index "
            f"{accepted_events}, got {event.instruction_index}"
        )

        assert event.pc == b_pc
        assert event.instruction == b_instr

        assert event.forward_a == fwd_a
        assert event.forward_b == fwd_b

        # Feeding every event into L2 also validates that the reconstructed
        # stream remains contiguous in executed-program order.
        # Preserve every executed event so realization checking can resolve
        # producer indices carried by L1Hit.
        events_by_index[event.instruction_index] = event

        coverage.observe(event)

        l1_hits = l1_coverage.observe(event)

        # --------------------------------------------------------------
        # CONTROL REALIZATION DIAGNOSTICS
        #
        # IMPORTANT:
        # This does not alter Intent Coverage and does not fail the test.
        # A control mismatch is diagnostic evidence for the later
        # Validated-Coverage layer.
        # --------------------------------------------------------------

        for l1_hit in l1_hits:
            result = control_checker.check(
                l1_hit,
                event,
                events_by_index,
            )

            control_checks += 1

            if result.passed:
                control_passes += 1
            else:
                control_failures += 1
                control_failed_bins.add(result.bin_id)

                failed_text = ",".join(
                    (
                        f"{check.name}:"
                        f"expected={check.expected},"
                        f"observed={check.observed}"
                    )
                    for check in result.failed_checks
                )

                dut._log.warning(
                    "CONTROL_REALIZATION_FAIL "
                    f"bin={result.bin_id} "
                    f"consumer_index="
                    f"{result.consumer_instruction_index} "
                    f"checks={failed_text}"
                )

            validation_outcomes = validated_coverage.register_hit(
                l1_hit,
                control_passed=result.passed,
            )

            record_validation_outcomes(
                validation_outcomes
            )

        # L1 attribution only needs producer history through d3.
        # Bound verification-side event storage independently of campaign
        # length.
        stale_event_index = (
            event.instruction_index - 4
        )

        if stale_event_index > 0:
            events_by_index.pop(
                stale_event_index,
                None,
            )

        validated_coverage.prune(
            latest_instruction_index=(
                event.instruction_index
            )
        )

    # ------------------------------------------------------------------
    # FINAL INVARIANTS
    # ------------------------------------------------------------------
    assert accepted_events > 0, (
        "Live DUT produced no accepted ExecutionEvent objects"
    )

    assert adapter.instruction_count == accepted_events
    if EXPECT_ACCEPTED > 0:
        assert accepted_events == EXPECT_ACCEPTED, (
            f"Expected {EXPECT_ACCEPTED} accepted instructions, "
            f"got {accepted_events}"
        )
    assert 0 <= coverage.intent_bins <= 62
    assert 0 <= l1_coverage.intent_bins <= 20

    if EXPECT_L1_BIN:
        assert EXPECT_L1_BIN in l1_coverage.intent_seen, (
            f"Unknown expected L1 bin: {EXPECT_L1_BIN}"
        )

        assert l1_coverage.intent_seen[EXPECT_L1_BIN], (
            f"Expected L1 bin {EXPECT_L1_BIN} was not hit"
        )

    assert control_checks == control_passes + control_failures
    assert (
        architectural_checks
        == architectural_passes + architectural_failures
    )

    validation_attempts = sum(
        validated_coverage.validation_attempt_count.values()
    )

    validated_hits = sum(
        validated_coverage.validated_hit_count.values()
    )

    rejected_hits = sum(
        validated_coverage.rejected_hit_count.values()
    )

    assert validation_attempts == control_checks

    assert (
        validation_attempts
        == validated_hits
        + rejected_hits
        + validated_coverage.pending_hits
    )

    assert (
        0
        <= validated_coverage.validated_bins
        <= l1_coverage.intent_bins
        <= 20
    )

    if EXPECT_L1_BIN:
        target_l1_validated = int(
            validated_coverage.validated_seen[
                EXPECT_L1_BIN
            ]
        )
    else:
        target_l1_validated = -1

    dut._log.info(
        "EXECUTION_STREAM_SMOKE "
        f"cycles={N_CYCLES} "
        f"accepted={accepted_events} "
        f"accepted_after_stall={accepted_after_stall} "
        f"stall_cycles={stall_cycles} "
        f"flush_cycles={flush_cycles} "
        f"unsupported_cycles={unsupported_cycles} "
        f"l1_intent_bins={l1_coverage.intent_bins} "
        f"l1_seen="
        f"{','.join(bin_id for bin_id, seen in l1_coverage.intent_seen.items() if seen)} "
        f"l2_intent_bins={coverage.intent_bins} "
        f"control_checks={control_checks} "
        f"control_passes={control_passes} "
        f"control_failures={control_failures} "
        f"control_failed_bins="
        f"{','.join(sorted(control_failed_bins)) or 'none'} "
        f"architectural_checks={architectural_checks} "
        f"architectural_passes={architectural_passes} "
        f"architectural_failures={architectural_failures} "
        f"architectural_failure_kinds="
        f"{','.join(sorted(architectural_failure_kinds)) or 'none'} "
        f"l1_validated_bins="
        f"{validated_coverage.validated_bins} "
        f"l1_validated_seen="
        f"{','.join(bin_id for bin_id, seen in validated_coverage.validated_seen.items() if seen) or 'none'} "
        f"validation_attempts={validation_attempts} "
        f"validated_hits={validated_hits} "
        f"rejected_hits={rejected_hits} "
        f"validation_pending="
        f"{validated_coverage.pending_hits} "
        f"target_l1_validated="
        f"{target_l1_validated}"
    )
    # ------------------------------------------------------------------
    # DIRECTED STALL REQUIREMENT
    # ------------------------------------------------------------------
    if EXPECT_STALL:
        assert stall_cycles > 0, (
            "Directed stall workload did not assert Reg_Stall"
        )

        assert accepted_after_stall > 0, (
            "A stalled IF/ID instruction was never subsequently accepted"
        )

    elif stall_cycles == 0:
        dut._log.warning(
            "No stall cycle occurred in the current instruction.hex; "
            "stall admission logic was not dynamically exercised."
        )

    # ------------------------------------------------------------------
    # DIRECTED FLUSH REQUIREMENT
    # ------------------------------------------------------------------
    if EXPECT_FLUSH:
        assert flush_cycles > 0, (
            "Directed flush workload did not assert PcSel"
        )

    elif flush_cycles == 0:
        dut._log.warning(
            "No redirect/flush occurred in the current instruction.hex; "
            "flush admission logic was not dynamically exercised."
        )
