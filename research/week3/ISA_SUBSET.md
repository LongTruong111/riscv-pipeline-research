# ISA Subset — DUT_BASELINE_T3

## 1. Frozen DUT

Tag: DUT_BASELINE_T3  
Commit: e0c1ae1e35f55630fd27116a19af53a19c5243bd

This document describes the instruction subset recognized by the frozen
RTL baseline. RTL implementation support must not be interpreted as
proof of functional correctness.

## 2. Baseline verified at Gate T3

Gate T3 directly verifies only the independent ADDI smoke baseline:

- `addi x1, x0, 5`
- `addi x2, x0, 7`
- `addi x3, x0, 3`

Expected architectural results:

- x1 = 5
- x2 = 7
- x3 = 3

The automated checker reports PASS.

Therefore, Gate T3 establishes only a baseline execution capability for
the tested ADDI cases. It does not verify the complete implemented ISA
subset.

## 3. Implemented / target ISA subset

The following instruction subset is derived from the frozen RTL decode
and execution paths.

| Class | Opcode | Operations with RTL support |
|---|---|---|
| R-type | `0110011` | ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND |
| OP-IMM | `0010011` | ADDI, SLLI, SLTI, SLTIU, XORI, SRLI, SRAI, ORI, ANDI |
| LOAD | `0000011` | LB, LH, LW, LBU, LHU |
| STORE | `0100011` | SB, SH, SW |
| BRANCH | `1100011` | BEQ, BNE, BLT, BGE, BLTU, BGEU |
| JAL | `1101111` | JAL |
| JALR | `1100111` | JALR |
| LUI | `0110111` | LUI |
| AUIPC | `0010111` | AUIPC |

No decode path was observed in the examined Controller RTL for the
MISC-MEM or SYSTEM opcode classes. Therefore FENCE, ECALL, EBREAK and
other SYSTEM instructions are outside the currently declared target
subset.

## 4. RTL evidence

### Main opcode decode

`Controller.sv` recognizes:

- `0110011`: R-type
- `0000011`: LOAD
- `0100011`: STORE
- `0010011`: OP-IMM
- `1100011`: BRANCH
- `1101111`: JAL
- `1100111`: JALR
- `0110111`: LUI
- `0010111`: AUIPC

### ALU operations

`ALUController.sv` and `alu.sv` provide execution paths for:

- ADD
- SUB
- AND
- OR
- XOR
- SLL
- SRL
- SRA
- signed comparison
- unsigned comparison
- equality
- inequality
- signed greater-or-equal
- unsigned greater-or-equal

### Immediate formats

`imm_Gen.sv` implements immediate generation for:

- I-type
- S-type
- B-type
- U-type
- J-type

### Memory-width operations

`datamemory.sv` contains explicit legal load paths for:

- LB
- LH
- LW
- LBU
- LHU

and store paths for:

- SB
- SH
- SW

### Branch and jump path

`BranchUnit.sv` uses the boolean ALU result to determine conditional
branch redirection through `PcSel`.

JAL redirects to `PC + immediate`.

JALR redirects using the ALU-computed target.

## 5. Known RTL limitations identified by static inspection

### L1 — ADDI decode ambiguity

R-type and OP-IMM instructions share `ALUOp = 2'b10`.

The ALU controller selects SUB when:

- `Funct3 = 000`
- bits `[31:25] = 0100000`

For an ADDI instruction, bits `[31:25]` belong to the immediate rather
than an R-type funct7 field.

Therefore ADDI cases whose immediate has:

`imm[11:5] = 0100000`

can statically satisfy the SUB-selection condition.

Status:

Static RTL decoder defect/limitation identified by inspection.
Dynamic directed validation is still required.

No RTL modification is made because DUT_BASELINE_T3 is frozen.

### L2 — JALR target bit 0

`BranchUnit.sv` directly assigns the JALR target from `AluResult`.

No explicit clearing of target bit 0 was observed in the examined RTL.

Status:

Static RTL conformance limitation identified by inspection.
Dynamic directed validation is still required.

No RTL modification is made because DUT_BASELINE_T3 is frozen.

### L3 — Permissive memory funct3 defaults

For loads, unsupported `funct3` values fall through to the default
full-word data path.

For stores, unsupported `funct3` values fall through to the default
SW behavior.

Therefore the memory decoder does not explicitly reject every illegal
load/store encoding.

This does not affect the declared legal instruction list above, but it
must not be interpreted as illegal-instruction checking.

## 6. Verification claim boundary

The table in Section 3 describes RTL implementation or target support,
not verification completeness.

At Gate T3, only the specified independent ADDI smoke cases are directly
verified.

The following still require later directed and/or coverage-driven
verification:

- complete R-type semantics;
- complete OP-IMM semantics;
- forwarding combinations;
- load-use hazards;
- load/store width and addressing behavior;
- branch taken/not-taken behavior;
- control-hazard flushing;
- JAL and JALR behavior;
- LUI and AUIPC behavior;
- identified decoder edge cases;
- architectural corner cases.

Therefore:

Implemented by RTL != Verified at Gate T3.
