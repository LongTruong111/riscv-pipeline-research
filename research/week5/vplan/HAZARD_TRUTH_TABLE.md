# T5 Hazard Truth Table — L1

## 1. Purpose

This document freezes the L1 hazard truth table derived from:

- `DUT_BASELINE_T3`;
- `GATE_GD1_COMPLETE`;
- `research/week5/vplan/HAZARD_SPACE.md`;
- `research/week5/vplan/HAZARD_SIGNAL_MAP.md`;
- `research/week5/vplan/TIMING_CONTRACT.md`;
- the frozen RTL under `design/`.

The truth table defines 20 behavioral coverage bins.

Each row has a corresponding directed verification target.

Coverage occurrence and functional correctness are intentionally
separate:

`bin hit != DUT pass`

A scenario may hit its coverage bin while the scoreboard simultaneously
reports an architectural failure.

This distinction is required so that coverage cannot hide a DUT defect.

---

## 2. Oracle Precedence

Expected behavior is derived in the following order:

1. architectural instruction semantics;
2. declared pipeline timing contract;
3. intended producer-consumer dependency semantics;
4. RTL signals used only for observability and implementation checking.

The frozen RTL must not be used as the correctness oracle for behavior
that is itself under verification.

Therefore a known or suspected RTL limitation remains coverable and
testable rather than being encoded as the expected correct behavior.

---

## 3. Source-Role Refinement

`SourceRole` is used inside this truth table as a refinement of
`ConsumerType`.

It is not an additional top-level Hazard-Space dimension.

Values are:

- `RS1`
- `RS2`
- `RF_BOUNDARY`
- `SPECIAL`

RS1 and RS2 behavior is checked separately where forwarding mux
selection differs.

After L1 establishes this symmetry, the later L2 model may abstract
source-port identity where explicitly justified.

---

## 4. Twenty-Bin Derivation

The 20 L1 bins are behavioral equivalence classes:

| Group | Purpose | Bins |
|---|---|---:|
| A | canonical ALU forwarding | 4 |
| B | d3 Register-File boundary | 1 |
| C | LOAD/interlock behavior | 4 |
| D | simultaneous dual forwarding | 1 |
| E | non-ALU writeback producers | 4 |
| F | link producer across redirect | 1 |
| G | store-data forwarding | 1 |
| H | newest-producer priority | 1 |
| I | semantic negative cases | 3 |
| **Total** | | **20** |

The number 20 is therefore not the raw Cartesian-product size.

The Cartesian product defined in `HAZARD_SPACE.md` is reduced only when
two combinations are justified as behaviorally equivalent or when a
combination is architecturally invalid/unreachable.

---

## 5. L1 Hazard Truth Table

| Bin | Producer | Consumer / role | Distance | Architectural expectation | Expected control / availability | Stall | Directed test |
|---|---|---|---|---|---|---:|---|
| H01 | `ALU_RESULT` | `RS1_ONLY / RS1` | d1 | consumer receives newest ALU value | `EX_MEM`, FwdA=`10` | 0 | T01 |
| H02 | `ALU_RESULT` | `RS1_RS2 / RS2` | d1 | consumer receives newest ALU value | `EX_MEM`, FwdB=`10` | 0 | T02 |
| H03 | `ALU_RESULT` | `RS1_ONLY / RS1` | d2 | consumer receives producer value | `MEM_WB`, FwdA=`01` | 0 | T03 |
| H04 | `ALU_RESULT` | `RS1_RS2 / RS2` | d2 | consumer receives producer value | `MEM_WB`, FwdB=`01` | 0 | T04 |
| H05 | any valid GPR producer | RF boundary | d3 | consumer sees committed architectural value | `RF_VISIBILITY_D3`, forwarding=`00` | 0 | T05 |
| H06 | `MEM_DATA` | `RS1_ONLY / RS1` | d1 | consumer receives loaded data | one interlock, then `MEM_WB` | 1 | T06 |
| H07 | `MEM_DATA` | `RS1_RS2 / RS2` | d1 | consumer receives loaded data | one interlock, then `MEM_WB` | 1 | T07 |
| H08 | `MEM_DATA` | `RS1_ONLY / RS1` | d2 | consumer receives loaded data | `MEM_WB`, FwdA=`01` | 0 | T08 |
| H09 | `MEM_DATA` | `RS1_RS2 / RS2` | d2 | consumer receives loaded data | `MEM_WB`, FwdB=`01` | 0 | T09 |
| H10 | two ALU producers | dual-source consumer | d1+d2 | both newest required operands reach consumer | FwdA=`10`, FwdB=`01` in canonical witness | 0 | T10 |
| H11 | `IMM` / LUI | `RS1` consumer | d1 | consumer receives LUI architectural immediate | architectural value must be correct; current EX/MEM path is a static risk | 0 | T11 |
| H12 | `IMM` / LUI | `RS1` consumer | d2 | consumer receives LUI architectural immediate | `MEM_WB`, FwdA=`01` | 0 | T12 |
| H13 | `PC_PLUS_IMM` / AUIPC | `RS1` consumer | d1 | consumer receives producer PC+imm value | architectural value must be correct; current EX/MEM path is a static risk | 0 | T13 |
| H14 | `PC_PLUS_IMM` / AUIPC | `RS1` consumer | d2 | consumer receives producer PC+imm value | `MEM_WB`, FwdA=`01` | 0 | T14 |
| H15 | `PC_PLUS_4` / JAL or JALR | next executed target consumer | executed d1 | target consumer receives link value | redirect bubbles allow RF visibility; no fall-through dependency is counted | 0 | T15 |
| H16 | `ALU_RESULT` | STORE data / `RS2` | d1 | stored data equals newest producer value | FwdB=`10` into `C.RD_Two` | 0 | T16 |
| H17 | two producers to same `rd` | consumer of same `rd` | latest d1, older d2 | newer producer wins | EX/MEM priority, Fwd=`10` | 0 | T17 |
| H18 | producer destination `x0` | source field matches x0 | special | no architectural RAW dependency | no forwarding due `rd != 0` rule | 0 | T18 |
| H19 | LOAD destination `x0` | valid consumer using x0 | adjacent | no architectural dependency and no required stall | expected stall=`0`; frozen detector has static false-stall risk | 0 | T19 |
| H20 | LOAD | instruction whose raw `rs2` field matches but does not use rs2 | adjacent | no architectural dependency and no required stall | expected stall=`0`; frozen detector has static false-stall risk | 0 | T20 |

---

## 6. Constructive Directed Witnesses

### T01 — ALU d1 / RS1

Example:

`addi x5, x0, 7`
`addi x6, x5, 1`

Expected:

- FwdA = `10`;
- no stall;
- x6 = 8.

### T02 — ALU d1 / RS2

Example:

`addi x5, x0, 7`
`add x6, x0, x5`

Expected:

- FwdB = `10`;
- no stall;
- x6 = 7.

### T03 — ALU d2 / RS1

Example:

`addi x5, x0, 7`
`addi x9, x0, 0`
`addi x6, x5, 1`

Expected FwdA = `01`.

### T04 — ALU d2 / RS2

Example:

`addi x5, x0, 7`
`addi x9, x0, 0`
`add x6, x0, x5`

Expected FwdB = `01`.

### T05 — d3 Register-File boundary

A valid producer is followed by two independent executed instructions,
then a consumer.

A LOAD producer is a suitable canonical witness because it verifies
that a value whose original availability was late has become ordinary
architectural Register-File state.

Expected:

- no forwarding;
- no stall;
- consumer obtains committed value from the Register File.

### T06 — LOAD d1 / RS1

Example structure:

`lw x5, 0(x1)`
`addi x6, x5, 1`

Expected:

- exactly one load-use stall;
- consumer subsequently obtains load value through MEM/WB.

### T07 — LOAD d1 / RS2

Example structure:

`lw x5, 0(x1)`
`add x6, x0, x5`

Expected:

- exactly one load-use stall;
- subsequent MEM/WB forwarding.

### T08 — LOAD d2 / RS1

Example:

`lw x5, 0(x1)`
`addi x9, x0, 0`
`addi x6, x5, 1`

Expected:

- no stall;
- FwdA = `01`.

### T09 — LOAD d2 / RS2

Example:

`lw x5, 0(x1)`
`addi x9, x0, 0`
`add x6, x0, x5`

Expected:

- no stall;
- FwdB = `01`.

### T10 — Simultaneous EX/MEM and MEM/WB forwarding

Canonical existing sequence:

`addi x1, x0, 10`
`addi x2, x1, 5`
`add  x3, x2, x1`

At the final consumer:

- x2 arrives through EX/MEM;
- x1 arrives through MEM/WB;
- FwdA = `10`;
- FwdB = `01`;
- x3 = 25.

### T11 — LUI d1

Example:

`lui x5, nontrivial_imm`
`addi x6, x5, 1`

The immediate must be selected so that the expected LUI result is not
numerically equal to the frozen EX/MEM `C.Alu_Result` value.

The architectural scoreboard determines correctness.

Current RTL datapath inspection predicts a potential incorrect d1
forwarding value.

This is a static risk, not a pre-declared dynamic failure.

### T12 — LUI d2

LUI, one independent instruction, then dependent consumer.

Expected:

- FwdA = `01`;
- forwarded value equals architectural LUI result.

### T13 — AUIPC d1

AUIPC immediately followed by a consumer of its destination register.

The architectural expected value is:

`producer_PC + U-immediate`

The current EX/MEM forwarding path exposes `C.Alu_Result`, so this case
is retained specifically as a correctness-sensitive directed target.

### T14 — AUIPC d2

AUIPC, one independent instruction, then dependent consumer.

Expected:

- MEM/WB forwarding;
- value equals architectural PC+immediate result.

### T15 — Link producer across redirect

Canonical form:

`jal x5, target`

followed at `target` by a consumer of x5.

The sequential fall-through instruction flushed by the jump is not a
valid consumer.

The next executed target instruction is the architectural consumer.

Expected:

- x5 contains the link address;
- redirect/flush creates sufficient pipeline separation for Register
  File visibility;
- no spurious RAW stall.

JALR may be exercised as a second subcase of the same
`PC_PLUS_4` producer class.

### T16 — Store-data forwarding

Example:

`addi x5, x0, 42`
`sw x5, 0(x1)`

Expected:

- FwdB = `10`;
- the forwarded value enters `C.RD_Two`;
- memory receives 42.

This bin is distinct because STORE uses an immediate for the ALU SrcB
while the forwarded RS2 value is still required as store data.

### T17 — Newest producer priority

Example:

`addi x5, x0, 1`
`addi x5, x0, 2`
`addi x6, x5, 0`

When the consumer executes:

- both EX/MEM and MEM/WB destinations can match x5;
- EX/MEM must win;
- consumer must observe 2, not 1.

Expected FwdA = `10`.

### T18 — x0 forwarding exclusion

Create a producer whose encoded destination is x0 followed by an
instruction whose source field is x0.

Expected hazard behavior:

- no valid architectural RAW dependency;
- forwarding select remains `00`.

Architectural x0 correctness is checked independently by the scoreboard
because the frozen Register File has a separately documented x0 risk.

### T19 — LOAD-to-x0 false-stall negative case

Example structure:

`lw x0, 0(x1)`
`addi x6, x0, 1`

Architecturally, the LOAD does not create a producer dependency.

Expected:

- no required load-use stall.

The frozen HazardDetection predicate does not test `rd != 0`, so this
directed case dynamically determines whether the previously documented
false-stall hypothesis is realized.

### T20 — unused-rs2 false-stall negative case

Example:

`lw   x5, 0(x1)`
`addi x6, x2, 5`

For ADDI, instruction bits `[24:20]` belong to the immediate and are
not an architectural rs2 operand.

Immediate value 5 intentionally makes the raw field equal x5 while
`rs1 = x2`.

Therefore:

- there is no architectural dependency on x5;
- expected stall = 0.

If the frozen detector stalls, the directed test confirms the
previously documented raw-field false-positive risk.

---

## 7. Coverage-Hit Rule

A positive RAW bin hit requires semantic qualification:

`ValidProducer`
AND `ValidConsumer`
AND `rd != x0`
AND `rd == architecturally-used source`
AND `required distance`
AND `bin-specific producer/consumer condition`

Negative bins H18-H20 are hit by occurrence of their explicitly defined
stimulus/semantic condition.

They do not require the DUT to exhibit the suspected incorrect
behavior.

Therefore:

- coverage measures whether the verification scenario occurred;
- scoreboard/checkers determine whether the DUT behaved correctly.

A DUT failure does not erase the coverage hit.

---

## 8. Sampling Rule

Coverage must follow the frozen timing contract.

Pipeline state:

`RisingEdge(clk) -> ReadOnly()`

Pre-edge control intent where required:

`FallingEdge(clk) -> ReadOnly()`

No L1 bin shall be inferred from an unsettled same-edge observation.

---

## 9. Relationship to L2

L1 establishes behavioral correctness classes including:

- RS1 versus RS2 selection;
- EX/MEM versus MEM/WB;
- load interlock behavior;
- d3 Register-File visibility;
- special writeback-source producers;
- forwarding priority;
- negative semantic cases.

The later L2 model is a register-index reachability model and shall not
duplicate all L1 behavioral dimensions.

Its proposed register cross-product must therefore be justified only
after these L1 distinctions are frozen.

---

## 10. Implementation Complexity

A direct collector implementation may evaluate all 20 fixed L1
predicates per qualified event.

For B = 20 bins:

`T_event = O(B) = O(20) = O(1)` for the frozen vPlan.

The computational bottleneck is expected to be RTL simulation and trace
processing rather than L1 predicate evaluation.

The collector should nevertheless avoid using scoreboard correctness
as a precondition for recording coverage.

---

## 11. Freeze Status

Number of L1 bins:

`20`

Required mapping:

`20 truth-table rows <-> 20 coverage bins <-> 20 directed test targets`

Current status:

**PASS / FROZEN**

Next artifact:

`research/week5/vplan/L1_COVERAGE_MODEL.md`
