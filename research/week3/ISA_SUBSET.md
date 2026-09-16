# ISA Subset — DUT_BASELINE_T3

## Frozen DUT
Tag: DUT_BASELINE_T3
Commit: <git rev-parse DUT_BASELINE_T3^{}>

## Baseline verified at T3
ADDI

Evidence:
- addi x1,x0,5
- addi x2,x0,7
- addi x3,x0,3
- automated checker PASS

## Implemented/target subset
Liệt kê đúng instruction/opcode rút từ Controller.sv và
ALUController.sv.

## Claim boundary
T3 does not prove complete correctness of the entire declared subset.

Load/store, branches, jumps, forwarding combinations and load-use
behavior require later directed verification.
