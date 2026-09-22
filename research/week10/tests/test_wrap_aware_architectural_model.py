from research.week7.timing_oracle_v1 import (
    _decode_checked,
    _execution_event,
)
from research.week10.adaptive.wrap_aware_architectural_model import (
    WrapAwareRV32ArchitecturalModel,
)


PC_MASK = 0x1FF


def encode_addi(
    rd: int,
    rs1: int,
    immediate: int,
) -> int:
    assert -2048 <= immediate <= 2047

    return (
        ((immediate & 0xFFF) << 20)
        | ((rs1 & 0x1F) << 15)
        | (0b000 << 12)
        | ((rd & 0x1F) << 7)
        | 0b0010011
    )


def encode_jal(
    rd: int,
    immediate: int,
) -> int:
    assert immediate % 2 == 0
    assert -(1 << 20) <= immediate < (1 << 20)

    encoded = (
        immediate
        & ((1 << 21) - 1)
    )

    return (
        (((encoded >> 20) & 0x1) << 31)
        | (
            ((encoded >> 1) & 0x3FF)
            << 21
        )
        | (
            ((encoded >> 11) & 0x1)
            << 20
        )
        | (
            ((encoded >> 12) & 0xFF)
            << 12
        )
        | ((rd & 0x1F) << 7)
        | 0b1101111
    )


def encode_jalr(
    rd: int,
    rs1: int,
    immediate: int,
) -> int:
    assert -2048 <= immediate <= 2047

    return (
        ((immediate & 0xFFF) << 20)
        | ((rs1 & 0x1F) << 15)
        | (0b000 << 12)
        | ((rd & 0x1F) << 7)
        | 0b1100111
    )


def make_event(
    *,
    instruction_index: int,
    pc: int,
    instruction: int,
):
    decoded = _decode_checked(
        instruction
    )

    return _execution_event(
        instruction_id=instruction_index,
        cycle=instruction_index,
        pc=pc,
        instruction=instruction,
        decoded=decoded,
    )


def advance_to_pc_508(
    model: WrapAwareRV32ArchitecturalModel,
) -> int:
    """Execute PCs 0..504, leaving next expected fetch at 508."""

    addi_word = encode_addi(
        1,
        1,
        1,
    )

    instruction_index = 1

    for logical_word in range(127):
        pc = (
            logical_word * 4
        ) & PC_MASK

        step = model.step(
            make_event(
                instruction_index=(
                    instruction_index
                ),
                pc=pc,
                instruction=addi_word,
            )
        )

        assert step.pc_match

        instruction_index += 1

    assert model.expected_pc == 508

    return instruction_index


def test_sequential_fetch_wraps_from_508_to_zero():
    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    instruction_index = (
        advance_to_pc_508(model)
    )

    word = encode_addi(
        1,
        1,
        1,
    )

    step = model.step(
        make_event(
            instruction_index=(
                instruction_index
            ),
            pc=508,
            instruction=word,
        )
    )

    assert step.pc_match
    assert step.expected_pc == 508

    assert step.next_pc == 0
    assert model.expected_pc == 0

    # 128 ADDI x1,x1,1 instructions executed.
    assert model.read_register(1) == 128


def test_jal_at_508_keeps_full_link_but_wraps_fetch_target():
    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    instruction_index = (
        advance_to_pc_508(model)
    )

    # A7-style local target:
    #
    #   start       = 508
    #   target      = 508 + 12 = 520
    #   fetch target low 9 bits = 8
    #
    # Link value remains full PC+4 = 512.
    jal_word = encode_jal(
        5,
        12,
    )

    step = model.step(
        make_event(
            instruction_index=(
                instruction_index
            ),
            pc=508,
            instruction=jal_word,
        )
    )

    assert step.pc_match

    assert model.read_register(5) == 512

    assert step.register_write is not None
    assert step.register_write.rd == 5
    assert step.register_write.value == 512

    assert step.next_pc == 8
    assert model.expected_pc == 8

    consumer_word = encode_addi(
        6,
        5,
        1,
    )

    consumer_step = model.step(
        make_event(
            instruction_index=(
                instruction_index + 1
            ),
            pc=8,
            instruction=consumer_word,
        )
    )

    assert consumer_step.pc_match
    assert model.read_register(6) == 513


def test_jalr_at_508_keeps_full_link_but_truncates_target():
    model = (
        WrapAwareRV32ArchitecturalModel()
    )

    instruction_index = (
        advance_to_pc_508(model)
    )

    # A7 JALR realization uses:
    #
    #   jalr rd, x0, target_pc
    #
    # start_pc  = 508
    # target_pc = 520
    #
    # BranchUnit supplies full 32-bit target to BrPC, while the
    # Datapath PC mux consumes only BrPC[8:0].
    jalr_word = encode_jalr(
        5,
        0,
        520,
    )

    step = model.step(
        make_event(
            instruction_index=(
                instruction_index
            ),
            pc=508,
            instruction=jalr_word,
        )
    )

    assert step.pc_match

    assert model.read_register(5) == 512

    assert step.register_write is not None
    assert step.register_write.value == 512

    assert step.next_pc == 8
    assert model.expected_pc == 8
