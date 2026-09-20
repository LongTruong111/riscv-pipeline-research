import pytest

from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week5.impl.commit_scoreboard import (
    CommitScoreboard,
    StoreObservation,
    WritebackObservation,
)
from research.week5.impl.execution_event import ExecutionEvent
from research.week5.impl.rv32_encode import (
    addi,
    sw,
)


def event(index, pc, instruction):
    return ExecutionEvent(
        instruction_index=index,
        cycle=index,
        pc=pc,
        instruction=instruction,
        rs1=(instruction >> 15) & 0x1F,
        rs2=(instruction >> 20) & 0x1F,
        rd=(instruction >> 7) & 0x1F,
        uses_rs1=False,
        uses_rs2=False,
        writes_rd=False,
        producer_type="NONE",
        consumer_type="NONE",
    )


def test_pc_pass():
    model = RV32ArchitecturalModel()
    scoreboard = CommitScoreboard()

    step = model.step(
        event(
            1,
            0,
            addi(5, 0, 7),
        )
    )

    result = scoreboard.check_pc(step)

    assert result.passed


def test_pc_mismatch_fails():
    model = RV32ArchitecturalModel()
    scoreboard = CommitScoreboard()

    step = model.step(
        event(
            1,
            4,
            addi(5, 0, 7),
        )
    )

    result = scoreboard.check_pc(step)

    assert not result.passed
    assert result.failed_checks[0].name == "executed_pc"


def test_writeback_pass():
    model = RV32ArchitecturalModel()
    scoreboard = CommitScoreboard()

    instruction = addi(5, 0, 7)

    step = model.step(
        event(
            1,
            0,
            instruction,
        )
    )

    result = scoreboard.check_writeback(
        step,
        WritebackObservation(
            instruction_index=1,
            write_enable=True,
            rd=5,
            data=7,
            instruction=instruction,
        ),
    )

    assert result.passed


def test_writeback_wrong_data_fails():
    model = RV32ArchitecturalModel()
    scoreboard = CommitScoreboard()

    instruction = addi(5, 0, 7)

    step = model.step(
        event(
            1,
            0,
            instruction,
        )
    )

    result = scoreboard.check_writeback(
        step,
        WritebackObservation(
            instruction_index=1,
            write_enable=True,
            rd=5,
            data=8,
            instruction=instruction,
        ),
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {"write_data"}


def test_missing_writeback_fails():
    model = RV32ArchitecturalModel()
    scoreboard = CommitScoreboard()

    step = model.step(
        event(
            1,
            0,
            addi(5, 0, 7),
        )
    )

    result = scoreboard.check_writeback(
        step,
        WritebackObservation(
            instruction_index=1,
            write_enable=False,
            rd=0,
            data=0,
        ),
    )

    assert not result.passed

    assert result.failed_checks[0].name == "write_enable"


def test_physical_write_to_x0_is_not_architectural_commit():
    model = RV32ArchitecturalModel()
    scoreboard = CommitScoreboard()

    instruction = addi(0, 0, 7)

    step = model.step(
        event(
            1,
            0,
            instruction,
        )
    )

    assert step.register_write is None

    result = scoreboard.check_writeback(
        step,
        WritebackObservation(
            instruction_index=1,
            write_enable=True,
            rd=0,
            data=7,
            instruction=instruction,
        ),
    )

    # Physical write control alone does not prove architectural x0
    # corruption. x0 state is checked separately.
    assert result.passed


def test_unexpected_nonzero_register_write_fails():
    model = RV32ArchitecturalModel()
    scoreboard = CommitScoreboard()

    instruction = addi(0, 0, 7)

    step = model.step(
        event(
            1,
            0,
            instruction,
        )
    )

    result = scoreboard.check_writeback(
        step,
        WritebackObservation(
            instruction_index=1,
            write_enable=True,
            rd=5,
            data=7,
            instruction=instruction,
        ),
    )

    assert not result.passed


def test_store_pass():
    model = RV32ArchitecturalModel()
    scoreboard = CommitScoreboard()

    step1 = model.step(
        event(
            1,
            0,
            addi(5, 0, 42),
        )
    )

    assert step1.register_write.value == 42

    instruction = sw(5, 0, 0)

    step2 = model.step(
        event(
            2,
            4,
            instruction,
        )
    )

    result = scoreboard.check_store(
        step2,
        StoreObservation(
            instruction_index=2,
            write_enable=True,
            address=0,
            data=42,
            instruction=instruction,
        ),
    )

    assert result.passed


def test_store_wrong_data_fails():
    model = RV32ArchitecturalModel()
    scoreboard = CommitScoreboard()

    model.step(
        event(
            1,
            0,
            addi(5, 0, 42),
        )
    )

    instruction = sw(5, 0, 0)

    step = model.step(
        event(
            2,
            4,
            instruction,
        )
    )

    result = scoreboard.check_store(
        step,
        StoreObservation(
            instruction_index=2,
            write_enable=True,
            address=0,
            data=41,
            instruction=instruction,
        ),
    )

    assert not result.passed

    assert {
        check.name
        for check in result.failed_checks
    } == {"store_data"}


def test_missing_store_fails():
    model = RV32ArchitecturalModel()
    scoreboard = CommitScoreboard()

    model.step(
        event(
            1,
            0,
            addi(5, 0, 42),
        )
    )

    step = model.step(
        event(
            2,
            4,
            sw(5, 0, 0),
        )
    )

    result = scoreboard.check_store(
        step,
        StoreObservation(
            instruction_index=2,
            write_enable=False,
            address=0,
            data=0,
        ),
    )

    assert not result.passed
    assert result.failed_checks[0].name == "store_enable"


def test_non_store_with_unexpected_memory_write_fails():
    model = RV32ArchitecturalModel()
    scoreboard = CommitScoreboard()

    step = model.step(
        event(
            1,
            0,
            addi(5, 0, 7),
        )
    )

    result = scoreboard.check_store(
        step,
        StoreObservation(
            instruction_index=1,
            write_enable=True,
            address=0,
            data=7,
        ),
    )

    assert not result.passed


def test_x0_pass():
    scoreboard = CommitScoreboard()

    result = scoreboard.check_x0(
        instruction_index=1,
        observed_value=0,
    )

    assert result.passed


def test_x0_corruption_fails():
    scoreboard = CommitScoreboard()

    result = scoreboard.check_x0(
        instruction_index=1,
        observed_value=7,
    )

    assert not result.passed
    assert result.failed_checks[0].name == "architectural_x0"


def test_observation_index_mismatch_rejected():
    model = RV32ArchitecturalModel()
    scoreboard = CommitScoreboard()

    step = model.step(
        event(
            1,
            0,
            addi(5, 0, 7),
        )
    )

    with pytest.raises(ValueError):
        scoreboard.check_writeback(
            step,
            WritebackObservation(
                instruction_index=2,
                write_enable=True,
                rd=5,
                data=7,
            ),
        )
