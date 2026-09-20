from research.week5.impl.architectural_model import (
    RV32ArchitecturalModel,
)
from research.week5.impl.execution_event import ExecutionEvent
from research.week5.impl.isa_decode import decode_instruction
from research.week6.expected_retire import (
    build_expected_retire_log,
)
from research.week6.golden_program import (
    GOLDEN_PROGRAM_INSTRUCTION_COUNT,
    build_golden_program,
)


def build_events(words):
    events = []

    for index, instruction in enumerate(words, start=1):
        decoded = decode_instruction(instruction)

        assert decoded is not None

        pc = (index - 1) * 4

        events.append(
            ExecutionEvent(
                instruction_index=index,
                cycle=index,
                pc=pc,
                instruction=instruction,
                rs1=decoded.rs1,
                rs2=decoded.rs2,
                rd=decoded.rd,
                uses_rs1=decoded.uses_rs1,
                uses_rs2=decoded.uses_rs2,
                writes_rd=decoded.writes_rd,
                producer_type=decoded.producer_type,
                consumer_type=decoded.consumer_type,
            )
        )

    return tuple(events)


def test_gate_t6_golden_program_executes_58_instructions():
    words = build_golden_program()

    assert len(words) == GOLDEN_PROGRAM_INSTRUCTION_COUNT
    assert len(words) >= 50

    events = build_events(words)

    model = RV32ArchitecturalModel()
    steps = []

    for event in events:
        step = model.step(event)

        assert step.pc_match
        steps.append(step)

    assert len(steps) == 58

    # --------------------------------------------------------------
    # Final architectural register state.
    # --------------------------------------------------------------
    assert model.read_register(0) == 0
    assert model.read_register(1) == 100
    assert model.read_register(2) == 11
    assert model.read_register(3) == 67
    assert model.read_register(4) == 67
    assert model.read_register(5) == 68
    assert model.read_register(6) == 0x12345000

    # AUIPC is instruction #8:
    # PC = (8 - 1) * 4 = 28.
    assert model.read_register(7) == 28

    # --------------------------------------------------------------
    # Final architectural memory state.
    # --------------------------------------------------------------
    assert model.read_word(100) == 3
    assert model.read_word(104) == 67

    # 58 sequential instructions x 4 bytes.
    assert model.expected_pc == 232


def test_gate_t6_golden_program_retire_log():
    words = build_golden_program()
    events = build_events(words)

    retire_log = build_expected_retire_log(events)

    assert len(retire_log) == 58

    assert [
        retire.instruction_id
        for retire in retire_log
    ] == list(range(1, 59))

    # Setup has 7 architectural register writes.
    # Each of 10 repeated blocks has 4 register writes.
    assert sum(
        retire.regwrite
        for retire in retire_log
    ) == 47

    # Initial store + one store in each repeated block.
    stores = [
        retire
        for retire in retire_log
        if retire.store_address is not None
    ]

    assert len(stores) == 11

    assert stores[0].store_address == 100
    assert stores[0].store_data == 3

    assert stores[-1].store_address == 104
    assert stores[-1].store_data == 67
