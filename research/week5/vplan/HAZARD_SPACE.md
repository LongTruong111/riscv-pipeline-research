# T5 Hazard Space Definition

## 1. Purpose

This document defines the complete hazard verification space used by
the T5 vPlan.

It is derived from:

- frozen DUT: `DUT_BASELINE_T3`;
- completed GĐ1 baseline: `GATE_GD1_COMPLETE`;
- `research/week3/ISA_SUBSET.md`;
- `research/week5/vplan/T5_INPUT_BASELINE.md`;
- `research/week5/vplan/HAZARD_SIGNAL_MAP.md`;
- `research/week5/vplan/TIMING_CONTRACT.md`;
- frozen RTL under `design/`.

The hazard space shall be defined before the L1/L2 coverage model and
before generator-specific optimization policy.

This prevents the coverage model from being changed to favor a
particular generator or experimental outcome.

---

## 2. Hazard-Space Structure

The functional hazard space is modeled as:

`HazardType × ProducerType × ConsumerType × DependencyDistance × ForwardingPath`

where each dimension must be:

1. architecturally meaningful;
2. observable on the frozen DUT;
3. reachable within the declared ISA subset;
4. relevant to the research scope.

No combination is considered part of the required verification space
unless all four conditions hold.

---

## 3. HazardType

The core T5 hazard space contains one architectural data-hazard class:

`RAW — Read After Write`

A RAW dependency exists when:

1. an older valid producer architecturally writes a GPR;
2. `rd != x0`;
3. a younger valid consumer architecturally reads the same GPR;
4. the producer value has not yet become available through the normal
   register-file timing at the point required by the consumer.

Load-use is not treated as a separate architectural hazard type.

It is a RAW dependency whose producer is a LOAD and whose timing may
require the DUT interlock before the value becomes forwardable.

### Excluded hazard families

`WAR` and `WAW` are outside the T5 forwarding/interlock hazard space.

The frozen DUT is an in-order pipeline, and the forwarding and hazard
detection mechanisms under study address RAW dependencies.

Control redirect/flush behavior is also not included in the RAW
coverage metric. It remains a separate verification obligation.

No claim is made here that all possible structural hazards of arbitrary
microarchitectures are absent. Structural hazards are simply outside
the declared T5 RAW hazard-space metric.

Status:

**FROZEN**

---

## 4. ProducerType

A producer is an instruction that performs an architectural GPR write.

Producer classes are defined by the architectural source of the value
written back rather than only by opcode name.

| ProducerType | ISA classes | Architectural writeback source |
|---|---|---|
| `ALU_RESULT` | R-type, OP-IMM | ALU result |
| `MEM_DATA` | LOAD | load data |
| `PC_PLUS_4` | JAL, JALR | return/link address |
| `IMM` | LUI | generated immediate |
| `PC_PLUS_IMM` | AUIPC | PC plus generated immediate |

STORE and BRANCH are not producer classes because they do not perform
an architectural GPR write.

### Rationale

This classification matters for forwarding correctness.

The frozen ForwardingUnit can select:

- EX/MEM;
- MEM/WB;
- Register File.

However, EX/MEM forwarding uses the EX/MEM ALU-result datapath.

Therefore producer types whose architectural result is not the ALU
result must not automatically be assumed equivalent to
`ALU_RESULT`.

Such cases remain verification targets rather than being excluded from
the hazard space merely because the current RTL forwarding datapath may
handle them incorrectly.

Status:

**FROZEN**

---

## 5. ConsumerType

A consumer is classified according to its architectural GPR source
usage.

| ConsumerType | ISA classes | Architectural sources |
|---|---|---|
| `RS1_RS2` | R-type, STORE, BRANCH | `rs1`, `rs2` |
| `RS1_ONLY` | OP-IMM, LOAD, JALR | `rs1` |
| `NO_GPR_SOURCE` | JAL, LUI, AUIPC | none |

Only `RS1_RS2` and `RS1_ONLY` form valid architectural RAW consumers.

`NO_GPR_SOURCE` is excluded from the positive RAW space but retained
as a negative verification class.

### Reason for the negative class

The frozen HazardDetection implementation compares the raw instruction
fields corresponding to both source positions without qualifying
whether the consumer opcode architecturally uses them.

Therefore a raw bit-field match must not automatically be classified
as a valid RAW dependency.

The potential resulting false-stall behavior remains a hypothesis until
confirmed dynamically by directed testing.

Status:

**FROZEN**

---

## 6. DependencyDistance

Dependency distance is defined in executed program order.

### d1

`d1` means the consumer is the next executed instruction after the
producer.

Number of intervening executed instructions:

`0`

For an ordinary ALU producer, this corresponds to the nearest RAW case
and normally requires EX/MEM forwarding.

### d2

`d2` means exactly one executed instruction lies between producer and
consumer.

Number of intervening executed instructions:

`1`

The existing golden trace demonstrates this class through MEM/WB
forwarding.

### d3

`d3` means exactly two executed instructions lie between producer and
consumer.

Number of intervening executed instructions:

`2`

This is the register-file visibility boundary.

The frozen DUT writes the Register File at `negedge clk` and performs
asynchronous/combinational reads.

Therefore a consumer in the corresponding WB/ID overlap can obtain the
updated architectural value through the Register File before its next
ID/EX capture.

This is not a dedicated forwarding bypass.

It is classified as:

`RF_VISIBILITY_D3`

### Distances greater than d3

Distances greater than `d3` are outside the forwarding-sensitive L1
space because the producer value is expected to have become ordinary
architectural Register File state before the consumer requires it.

They may still appear in random programs but do not form distinct
forwarding-behavior classes.

Status:

**FROZEN**

---

## 7. ForwardingPath

The T5 forwarding/availability mechanism is classified as follows.

| ForwardingPath | Mechanism | RTL evidence |
|---|---|---|
| `EX_MEM` | EX/MEM → EX | forwarding select `10` |
| `MEM_WB` | MEM/WB → EX | forwarding select `01` |
| `RF_VISIBILITY_D3` | WB write → Register File → ID | forwarding select `00`; RF phase behavior |
| `STALL_THEN_MEM_WB` | load-use interlock followed by usable forwarded value | `Reg_Stall` + later MEM/WB availability |

Forwarding select `11` is not generated by the frozen ForwardingUnit
and is therefore unreachable under the current RTL.

### Priority

When EX/MEM and MEM/WB both match the same source register, EX/MEM has
priority.

This selects the newer producer.

### Important distinction

`RF_VISIBILITY_D3` is a value-availability mechanism used by the
verification model.

It is not a physical forwarding mux path.

Status:

**FROZEN**

---

## 8. Architectural x0 Rule

Architectural dependencies through `x0` are ineligible.

A valid RAW producer requires:

`rd != x0`

The ForwardingUnit explicitly applies this condition.

The separately documented Register File x0 defect does not make x0 a
valid architectural dependency class.

Therefore:

- x0 is excluded from positive RAW dependency bins;
- x0 behavior may be tested separately as a DUT defect/corner case.

Status:

**FROZEN**

---

## 9. Validity and Bubble Rule

The frozen DUT has no explicit pipeline `valid` bit.

A debug `Curr_Instr` field alone is insufficient to prove that an
instruction is functionally active.

In particular, ID/EX bubble injection can retain `B.Curr_Instr` while
clearing functional control state.

Therefore a valid hazard event must be qualified using functional
pipeline/control semantics defined in:

`research/week5/vplan/HAZARD_SIGNAL_MAP.md`

A register-index match by itself is insufficient.

Status:

**FROZEN**

---

## 10. Load-Use / False-Stall Boundary

The frozen load-use detector implements a raw field comparison between:

- ID/EX load destination;
- IF/ID bits `[19:15]`;
- IF/ID bits `[24:20]`.

It does not qualify:

- `ID_EX_rd != 0`;
- whether the consumer actually uses `rs1`;
- whether the consumer actually uses `rs2`.

Therefore two concepts must remain separate.

### Architectural RAW hazard

A real producer-consumer register dependency according to ISA source
semantics.

### Potential false stall

The RTL asserts stall because raw encoded fields match even though no
architectural source dependency exists.

The second case is not counted as a positive RAW coverage hit.

It is retained as an independent negative/robustness verification
target.

Current classification:

**HYPOTHESIS / TECHNICAL RISK — directed validation required**

---

## 11. Scope Exclusions

The following cases are excluded from the positive T5 RAW hazard
coverage space.

| Excluded class | Reason |
|---|---|
| `rd == x0` dependency | no architectural producer dependency |
| `rs == x0` as dependency on prior writer | x0 has no architectural producer |
| JAL/LUI/AUIPC as consumers | no architectural GPR source |
| WAR | outside in-order RAW forwarding/interlock problem |
| WAW | outside in-order RAW forwarding/interlock problem |
| control redirect as HazardType | verified separately from RAW metric |
| forwarding select `11` | unreachable in frozen ForwardingUnit |
| distance `> d3` | no distinct forwarding-sensitive behavior expected |
| illegal ISA encodings | outside frozen legal ISA subset |
| MISC-MEM/SYSTEM instructions | not in frozen target ISA subset |

### Non-exclusion rule

A scenario shall not be removed because:

- it is difficult for Random to generate;
- it closes slowly;
- it creates a long coverage tail;
- it exposes a DUT limitation;
- it is inconvenient for CGS.

DUT defects and implementation limitations are not dead-bin
justifications.

Status:

**FROZEN**

---

## 12. Reachability Rule

An included hazard class is considered a-priori reachable only when a
constructive sequence can be written using instructions from the frozen
ISA subset.

For a positive RAW dependency, the constructive argument must specify:

1. producer instruction class;
2. `rd != x0`;
3. consumer instruction class;
4. which architectural source (`rs1` or `rs2`) consumes `rd`;
5. dependency distance;
6. expected value-availability/forwarding mechanism.

RTL signal combinations alone do not establish architectural
reachability.

The later completeness document shall map each L1 truth-table row to a
constructive directed sequence.

L2 reachability shall be argued separately for all register-index and
distance bins.

Status:

**FROZEN**

---

## 13. Hazard-Space Freeze Summary

The T5 functional hazard space is now defined as:

`RAW × ProducerType × ConsumerType × DependencyDistance × ForwardingPath`

with:

- `HazardType = RAW`;
- five producer writeback classes;
- two positive consumer source-use classes;
- distances `d1`, `d2`, `d3`;
- four value-availability/forwarding mechanisms;
- explicit architectural and scope exclusions.

The Cartesian product is not interpreted as meaning that every
mathematical combination is legal.

Illegal, semantically impossible, behaviorally equivalent, or
microarchitecturally unreachable combinations shall be resolved
explicitly when constructing the L1 Hazard Truth Table.

This document defines the space.

The next artifact defines the required behavioral equivalence classes
within that space.

Current status:

**PASS / FROZEN**

Next artifact:

`research/week5/vplan/HAZARD_TRUTH_TABLE.md`
