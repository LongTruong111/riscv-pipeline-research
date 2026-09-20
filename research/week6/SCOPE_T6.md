# Week 6 — Golden Functional Model + Timing Oracle v0 Scope

## Frozen baseline

Week 6 extends the formally closed Week-5 baseline.

The following remain frozen and are not redefined:

* H01–H20 semantics
* L2 = 62 bins
* Intent / Validated coverage contract
* executed-program-order dependency distance
* statistical protocol
* M0–M3 experimental protocol
* Adaptive A0–A9 taxonomy
* pilot preregistration

Week-6 development must not modify the DUT merely to make verification pass.

## T6 architectural ISA subset

The Golden Functional Model shall support:

* ADD
* ADDI
* LW
* SW
* LUI
* AUIPC
* JAL
* JALR
* BEQ
* BNE
* BLT
* BGE
* BLTU
* BGEU

The subset is intentionally limited. Week 6 does not attempt full RV32I coverage.

## Deferred instructions

The following are outside the required Week-6 scope unless a later technical dependency requires them:

* SUB
* SLL
* SLT
* SLTU
* XOR
* SRL
* SRA
* OR
* AND
* remaining OP-IMM variants
* byte/halfword loads and stores

Unsupported instructions shall not be silently ignored by the architectural oracle.

## Architectural rules

The Golden Functional Model is architectural and independent of DUT implementation defects.

Required invariants include:

* x0 is permanently zero.
* Arithmetic state is normalized to 32 bits.
* Memory is byte-addressed and little-endian.
* Uninitialized memory reads as zero.
* Architectural PC semantics remain 32-bit.
* JAL writes PC+4.
* JALR writes PC+4 and uses the architectural target rule.
* Branches update PC according to architectural branch semantics.

## Timing Oracle v0 scope

Timing Oracle v0 covers only:

* no hazard
* ALU → ALU distance-1
* ALU → ALU distance-2
* load-use
* basic forwarding

The following timing interactions are deferred to Timing Oracle v1:

* branch timing
* flush penalty
* consecutive hazards
* bubbles
* pipeline fill
* pipeline drain
* reset boundary
* nested timing interactions

## Week-6 gate

Gate T6 requires:

* Golden model executes at least 50 supported instructions.
* Shared encoder/decoder tests pass.
* Immediate boundary tests pass.
* Representative encodings cross-check against objdump.
* At least 6 handcrafted Timing Oracle v0 sequences pass.
* Week-5 frozen regression remains unchanged.
