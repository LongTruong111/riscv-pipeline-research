import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from research.week5.impl.signal_adapter import (
    ExecutionEventAdapter,
    PreEdgeSnapshot,
)
from research.week7.retire_monitor import (
    RetireMonitor,
    RetireTag,
)


POST_RESET_CYCLES = 12
EXPECTED_POST_RESET = 2


def signal_int(signal, name):
    try:
        return int(signal.value)
    except ValueError as exc:
        raise AssertionError(
            f"{name} contains unresolved X/Z value: {signal.value}"
        ) from exc


async def initial_reset(dut, cycles=3):
    dut.reset.value = 1

    for _ in range(cycles):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()


async def admit_cycle(
    dut,
    adapter,
    monitor,
    cycle,
):
    """
    Execute one normal observation/admission cycle.

    Returns:
        (accepted_event, retired_event)
    """

    await FallingEdge(dut.clk)
    await ReadOnly()

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

    await RisingEdge(dut.clk)
    await ReadOnly()

    accepted_event = None
    accepted_tag = None

    if pending is not None:
        assert signal_int(
            dut.probe_b_pc,
            "probe_b_pc",
        ) == pending.pc

        assert signal_int(
            dut.probe_b_instr,
            "probe_b_instr",
        ) == pending.instruction

        accepted_event = adapter.finalize_post_edge(
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

        accepted_tag = RetireTag.from_execution_event(
            accepted_event
        )

    monitor.advance_pipeline(accepted_tag)

    return accepted_event, retired


@cocotb.test()
async def test_live_reset_boundary(dut):
    """
    Reset while valid instructions are still in flight.

    Required properties:

        1. pre-reset instructions are present in B/C;
        2. reset invalidates verification-side B/C/D tags;
        3. frozen RTL clears B/C/D pipeline state;
        4. no pre-reset instruction retires after reset;
        5. executed-program-order instruction IDs restart;
        6. post-reset accepted count equals post-reset retired count.
    """

    dut.clk.value = 0

    clock = Clock(
        dut.clk,
        10,
        units="ns",
    )
    cocotb.start_soon(clock.start())

    await initial_reset(dut)

    adapter = ExecutionEventAdapter()
    monitor = RetireMonitor()

    # --------------------------------------------------------------
    # PRE-RESET:
    # admit exactly two T01 instructions.
    #
    # After two RisingEdges:
    #
    #     B = instruction 2
    #     C = instruction 1
    #     D = empty
    #
    # Therefore both instructions are still unretired.
    # --------------------------------------------------------------
    pre_reset_accepted = []

    for cycle in (1, 2):
        accepted, retired = await admit_cycle(
            dut,
            adapter,
            monitor,
            cycle,
        )

        assert retired is None
        assert accepted is not None

        pre_reset_accepted.append(
            accepted.instruction_index
        )

    assert pre_reset_accepted == [1, 2]

    assert monitor.retired_count == 0

    assert monitor.stage_instruction_ids == (
        2,
        1,
        None,
    ), (
        "expected two valid in-flight instructions "
        "before reset"
    )

    # --------------------------------------------------------------
    # ASSERT RESET at FallingEdge, away from active RisingEdge.
    # --------------------------------------------------------------
    await FallingEdge(dut.clk)
    await ReadOnly()

    # Nothing has reached D yet.
    assert monitor.d_tag is None

    dut.reset.value = 1

    # First reset-active RisingEdge clears pipeline registers.
    await RisingEdge(dut.clk)
    await ReadOnly()

    adapter.reset()
    monitor.reset()

    assert monitor.stage_instruction_ids == (
        None,
        None,
        None,
    )

    assert monitor.retired_count == 0

    # Frozen RTL pipeline registers must also be cleared.
    assert signal_int(
        dut.probe_b_control_nonzero,
        "probe_b_control_nonzero",
    ) == 0

    assert signal_int(
        dut.probe_c_instr,
        "probe_c_instr",
    ) == 0

    assert signal_int(
        dut.probe_d_instr,
        "probe_d_instr",
    ) == 0

    # Keep reset asserted for the rest of the frozen three-cycle
    # reset interval.
    for _ in range(2):
        await RisingEdge(dut.clk)
        await ReadOnly()

        assert signal_int(
            dut.probe_c_instr,
            "probe_c_instr",
        ) == 0

        assert signal_int(
            dut.probe_d_instr,
            "probe_d_instr",
        ) == 0

    # --------------------------------------------------------------
    # DEASSERT RESET at FallingEdge.
    # --------------------------------------------------------------
    await FallingEdge(dut.clk)
    dut.reset.value = 0

    await RisingEdge(dut.clk)
    await ReadOnly()

    # Verification state starts a new execution epoch.
    assert adapter.instruction_count == 0
    assert monitor.retired_count == 0
    assert monitor.stage_instruction_ids == (
        None,
        None,
        None,
    )

    # --------------------------------------------------------------
    # POST-RESET:
    # instruction memory restarts from PC=0, so T01 executes again.
    # --------------------------------------------------------------
    post_reset_accepted = []
    post_reset_retired = []

    for cycle in range(
        1,
        POST_RESET_CYCLES + 1,
    ):
        accepted, retired = await admit_cycle(
            dut,
            adapter,
            monitor,
            cycle,
        )

        if accepted is not None:
            post_reset_accepted.append(
                accepted.instruction_index
            )

        if retired is not None:
            post_reset_retired.append(
                retired.instruction_id
            )

    assert post_reset_accepted == [1, 2], (
        f"unexpected post-reset accepted stream: "
        f"{post_reset_accepted}"
    )

    assert post_reset_retired == [1, 2], (
        f"unexpected post-reset retire stream: "
        f"{post_reset_retired}"
    )

    assert (
        len(post_reset_accepted)
        == EXPECTED_POST_RESET
    )

    assert (
        len(post_reset_retired)
        == EXPECTED_POST_RESET
    )

    assert (
        monitor.retired_count
        == EXPECTED_POST_RESET
    )

    assert monitor.stage_instruction_ids == (
        None,
        None,
        None,
    )

    dut._log.info(
        "RESET_BOUNDARY_SUMMARY "
        f"pre_reset_accepted="
        f"{','.join(str(x) for x in pre_reset_accepted)} "
        f"pre_reset_retired=0 "
        f"post_reset_accepted="
        f"{','.join(str(x) for x in post_reset_accepted)} "
        f"post_reset_retired="
        f"{','.join(str(x) for x in post_reset_retired)} "
        f"pipeline_clear=1 "
        f"id_restart=1 "
        f"status=PASS"
    )
