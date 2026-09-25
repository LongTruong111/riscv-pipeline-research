import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from research.week5.impl.rv32_encode import jalr, nop


async def patch_word(dut, address: int, word: int) -> None:
    """Patch one aligned word through the frozen Week-10 IMEM backdoor."""
    assert address % 4 == 0
    assert 0 <= address <= 508

    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = address
    dut.imem_patch_data.value = word

    await Timer(1, units="ns")

    dut.imem_patch_strobe.value = 1
    await Timer(1, units="ns")

    dut.imem_patch_strobe.value = 0
    await Timer(1, units="ns")


@cocotb.test()
async def test_canonical_dut_jalr_missing_lsb_clear(dut):
    """
    Directed witness for the canonical DUT JALR target defect.

    Architectural rule:
        next_pc = (rs1 + imm) & ~1

    Stimulus:
        PC 0x000: jalr x5, x0, 13

    Therefore:
        raw target      = 0x00d
        expected target = 0x00c

    The current canonical RTL is expected to redirect to 0x00d because
    BranchUnit forwards ALUResult directly without clearing bit zero.

    This test PASSES only when the known baseline defect is observed.
    It does not repair or mutate the DUT.
    """

    jalr_word = jalr(5, 0, 13)

    # Stable defaults.
    dut.reset.value = 1
    dut.imem_patch_strobe.value = 0
    dut.imem_patch_addr.value = 0
    dut.imem_patch_data.value = 0

    cocotb.start_soon(
        Clock(dut.clk, 10, units="ns").start()
    )

    # Patch a completely deterministic local image.
    #
    # Extra NOP at 0x10 ensures that if the buggy DUT fetches from odd
    # address 0x00d, bytes across the 0x0c/0x10 boundary are known.
    await patch_word(dut, 0x000, jalr_word)
    await patch_word(dut, 0x004, nop())
    await patch_word(dut, 0x008, nop())
    await patch_word(dut, 0x00C, nop())
    await patch_word(dut, 0x010, nop())

    # Synchronous DUT reset.
    for _ in range(4):
        await RisingEdge(dut.clk)

    dut.reset.value = 0

    saw_redirect = False
    observed_redirect_pc = None
    observed_link = None

    # More than enough for the five-stage pipeline plus redirect.
    for _ in range(30):
        await RisingEdge(dut.clk)
        await Timer(1, units="ns")

        if int(dut.probe_flush.value) == 1:
            saw_redirect = True

        if saw_redirect:
            a_pc = int(dut.probe_a_pc.value)

            # Correct architectural target is 12.
            # Current canonical DUT is predicted to expose 13.
            if a_pc in (12, 13):
                observed_redirect_pc = a_pc

        if (
            int(dut.reg_write_sig.value) == 1
            and int(dut.reg_num.value) == 5
        ):
            observed_link = int(dut.reg_data.value)

        if (
            observed_redirect_pc is not None
            and observed_link is not None
        ):
            break

    assert saw_redirect, (
        "JALR did not activate the redirect path"
    )

    # Independent architectural expectation:
    # (x0 + 13) & ~1 = 12.
    expected_architectural_pc = 12

    assert observed_redirect_pc is not None, (
        "Did not observe either architectural target 0x00c "
        "or predicted defective target 0x00d"
    )

    assert observed_redirect_pc == 13, (
        "Canonical DUT did not exhibit the expected JALR LSB-clear "
        "defect: "
        f"architectural target=0x{expected_architectural_pc:03x}, "
        f"observed=0x{observed_redirect_pc:03x}"
    )

    # JALR link semantics are independent of target-bit clearing.
    assert observed_link == 4, (
        "Unexpected JALR link value: "
        f"expected=0x004 observed={observed_link!r}"
    )

    dut._log.info(
        "JALR_LSB_CLEAR_DEFECT_WITNESS "
        "raw_target=0x00d "
        "architectural_target=0x00c "
        f"observed_target=0x{observed_redirect_pc:03x} "
        f"link=0x{observed_link:08x} "
        "status=PASS"
    )
