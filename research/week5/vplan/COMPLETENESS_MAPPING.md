# COMPLETENESS AND REACHABILITY MAPPING

## 1. Purpose

This document freezes the completeness argument for the declared
Week-5 hazard verification coverage model.

It establishes:

1. traceability between the frozen L1 truth table, L1 bins, and directed
   test targets;
2. a-priori reachability of every frozen L2 bin;
3. explicit exclusions from the declared coverage space;
4. the boundary of the resulting completeness claim.

This document does not claim complete verification of RV32I.

The permitted claim is:

> complete within the declared verification scope.

---

## 2. Normative Inputs

This mapping is derived from the frozen:

* `HAZARD_SPACE.md`
* `HAZARD_TRUTH_TABLE.md`
* `L1_COVERAGE_MODEL.md`
* `L2_COVERAGE_MODEL.md`
* `TIMING_CONTRACT.md`
* `HAZARD_SIGNAL_MAP.md`

If a semantic conflict is discovered, the upstream frozen artifact must
be reviewed explicitly rather than silently reinterpreted here.

---

## 3. Coverage Layers

The verification plan uses two complementary coverage layers.

### L1

L1 captures behavioral hazard classes.

Frozen cardinality:

`20 bins`

### L2

L2 captures forwarding-sensitive RAW register-index reachability.

Frozen cardinality:

`62 bins`

defined as:

`DependencyDistance × DependentRegister`

with:

`DependencyDistance in {d1, d2}`

and:

`DependentRegister in {x1, ..., x31}`

Therefore:

`2 × 31 = 62`

L1 and L2 answer different verification questions and shall not be
combined into a single Cartesian product.

---

## 4. L1 Traceability Requirement

The frozen L1 model requires:

`20 truth-table rows <-> 20 L1 bins <-> 20 canonical directed-test targets`

The mapping is:

| Truth-table bin | L1 coverage bin | Canonical directed target |
| --------------- | --------------- | ------------------------- |
| H01             | H01             | T01                       |
| H02             | H02             | T02                       |
| H03             | H03             | T03                       |
| H04             | H04             | T04                       |
| H05             | H05             | T05                       |
| H06             | H06             | T06                       |
| H07             | H07             | T07                       |
| H08             | H08             | T08                       |
| H09             | H09             | T09                       |
| H10             | H10             | T10                       |
| H11             | H11             | T11                       |
| H12             | H12             | T12                       |
| H13             | H13             | T13                       |
| H14             | H14             | T14                       |
| H15             | H15             | T15                       |
| H16             | H16             | T16                       |
| H17             | H17             | T17                       |
| H18             | H18             | T18                       |
| H19             | H19             | T19                       |
| H20             | H20             | T20                       |

The semantic meaning of H01-H20 remains normative in
`HAZARD_TRUTH_TABLE.md`.

This document does not duplicate those definitions.

---

## 5. L1 Completeness Argument

L1 completeness is structural rather than statistical.

For each frozen truth-table row:

1. exactly one corresponding L1 bin exists;
2. exactly one canonical directed-test target exists;
3. the test target is intended to construct the semantic condition
   defined by that truth-table row;
4. the coverage collector independently determines whether the bin was
   actually exercised;
5. realization/checker logic independently determines whether the DUT
   behavior was valid.

Therefore no frozen truth-table row is absent from the L1 coverage
model.

Conversely, no L1 coverage bin exists without a frozen truth-table row.

Hence the mapping is bijective at the specification level:

`TruthTableRows <-> L1Bins`

with cardinality:

`20 <-> 20`

The directed tests provide canonical traceability:

`L1Bins -> DirectedTargets`

with one canonical target for each bin.

A directed test may incidentally exercise other bins, but incidental
coverage does not remove the requirement for its canonical target.

---

## 6. L1 Intent Versus Validated Completeness

L1 completeness must distinguish two questions.

### Intent completeness

All 20 scenarios have been exercised:

`C_L1_intent = 20 / 20`

### Validated completeness

All 20 scenarios have been exercised and successfully realized by the
DUT:

`C_L1_validated = 20 / 20`

A DUT defect may therefore permit complete Intent Coverage while
preventing complete Validated Coverage.

This distinction prevents stimulus reachability from being confused
with DUT correctness.

---

## 7. L2 Bin Universe

For each:

`R in {x1, ..., x31}`

the L2 model contains:

`(d1, R)`

and:

`(d2, R)`

Therefore the complete bin set is:

`{d1, d2} × {x1, ..., x31}`

with cardinality:

`62`

There are no off-diagonal `(rd, rs)` register-pair bins because a valid
RAW dependency requires:

`rd_producer == rs_dependent`

---

## 8. Constructive Reachability Criterion

An L2 bin is considered a-priori reachable only if a legal instruction
sequence can be constructed before observing campaign results.

The construction must establish:

1. a valid architectural producer;
2. `rd != x0`;
3. a valid architectural consumer;
4. a consumer source that architecturally uses the producer register;
5. the required dependency distance;
6. executed-program-order validity.

Reachability does not require the DUT to behave correctly.

It establishes only that the scenario can legally be generated within
the declared stimulus and ISA scope.

---

## 9. Constructive Reachability of d1 Bins

For arbitrary:

`R in {x1, ..., x31}`

construct:

```text
P: valid instruction writing R
C: valid instruction architecturally reading R
```

with no executed instruction between P and C.

Then C has a RAW dependency on P with:

`DependencyDistance = d1`

and the L2 bin is:

`(d1, R)`

Because R is arbitrary over all 31 eligible architectural registers,
all:

`31`

d1 bins are constructively reachable.

---

## 10. Constructive Reachability of d2 Bins

For arbitrary:

`R in {x1, ..., x31}`

construct:

```text
P: valid instruction writing R
F: independent valid filler instruction
C: valid instruction architecturally reading R
```

The filler F must:

* not write R;
* not introduce a nearer writer of R;
* not redirect control flow away from C;
* remain within the frozen ISA subset.

Then the producer-consumer relationship has:

`DependencyDistance = d2`

and the corresponding bin is:

`(d2, R)`

Because an independent filler can be selected for every eligible R,
all:

`31`

d2 bins are constructively reachable.

---

## 11. Total L2 Reachability

From Sections 9 and 10:

`reachable_d1 = 31`

`reachable_d2 = 31`

Therefore:

`reachable_L2 = 31 + 31 = 62`

which equals the complete frozen L2 bin count.

Hence:

`reachable_L2 / defined_L2 = 62 / 62`

All frozen L2 bins are reachable a priori.

---

## 12. Operand Attribution

`rs1` and `rs2` are checked independently according to architectural
source usage.

They are not separate L2 dimensions.

If both source operands refer to the same producer register and the
same producer-consumer relationship, the event maps to one:

`(distance, register)`

bin.

If the two sources depend on different valid producers, each dependency
is attributed independently.

Example:

```text
producer A -> x5
producer B -> x9
consumer uses x5 and x9
```

may generate:

```text
(d2, x5)
(d1, x9)
```

provided the executed-program-order distances satisfy those values.

---

## 13. Latest-Writer Requirement

A consumer dependency is attributed to the nearest preceding valid
writer of the consumed register.

Example:

```text
I0: writes x5
I1: writes x5
I2: reads  x5
```

The dependency is:

`I1 -> I2`

The older:

`I0 -> I2`

relationship is shadowed and must not be counted as an independent RAW
dependency.

This rule is necessary for both correct distance classification and
constructive reachability.

---

## 14. Explicit Exclusions

The following cases are excluded from positive L2 coverage.

### 14.1 x0 producer

`rd == x0`

does not create an architectural producer dependency.

### 14.2 Consumer x0 source

Reading architectural `x0` does not depend on a prior writer.

### 14.3 Off-diagonal register pair

A tuple satisfying:

`rd_producer != rs_dependent`

is not a RAW dependency.

Such tuples are the reason the rejected 1,922-bin Cartesian product is
not used.

### 14.4 Unused encoded source field

A raw instruction bit-field match does not establish dependency if the
instruction does not architecturally use that source operand.

### 14.5 Shadowed older producer

An older writer superseded by a nearer writer is not attributed as the
consumer's active dependency.

### 14.6 Non-executed instruction

Flushed, redirected-away, invalid, or otherwise non-executed
instructions do not form architectural producer-consumer events unless
a frozen L1 scenario explicitly requires observation of such behavior.

### 14.7 Distances beyond d2

Distances beyond d2 do not form separate L2 bins.

`d3` behavior is handled at L1 where Register-File visibility and
write-through behavior are explicitly represented.

Distances greater than d3 are outside the forwarding-sensitive
coverage scope.

### 14.8 Operand-position dimension

`rs1` versus `rs2` is not an additional L2 coverage dimension.

Behavioral operand-selection correctness remains represented by L1.

---

## 15. Relationship Between Stimulus Dependency and Realized Hazard

Three concepts must remain distinct.

### Stimulus dependency

The generated instruction sequence contains an architectural
producer-consumer dependency.

### Realized microarchitectural hazard

The dependency reaches a pipeline configuration requiring forwarding,
stalling, Register-File visibility, or other relevant handling.

### Correct DUT response

The observed DUT control/data behavior satisfies the expected semantics.

The existence of a stimulus dependency does not itself prove correct
hazard handling.

Coverage and checker evidence must therefore remain separately
observable.

---

## 16. Completeness Claim Boundary

The following claim is permitted:

> The verification campaign provides complete coverage within the
> declared L1/L2 hazard verification scope when all required validated
> bins and directed-test obligations are satisfied.

The following claim is not permitted:

> complete verification of RV32I.

The declared model intentionally excludes ISA behavior and
microarchitectural properties outside the frozen verification scope.

---

## 17. What Completeness Does Not Prove

Even 100% validated L1 and L2 coverage does not by itself prove:

* absence of all RTL defects;
* complete RV32I compliance;
* correctness for arbitrary instruction sequences;
* correctness outside the frozen DUT configuration;
* absence of temporal bugs not represented by the model;
* absence of memory-system bugs outside the declared contract;
* correctness under scenarios explicitly excluded by the vPlan.

Coverage is evidence relative to a declared model, not a universal
correctness proof.

---

## 18. Implementation Complexity

L1 contains:

`20`

fixed bins.

L2 contains:

`62`

fixed bins.

Direct indexed L2 update is:

`O(1)`

per classified dependency event.

Evaluating all frozen L1 predicates is:

`O(20) = O(1)`

for the frozen configuration.

A complete static enumeration of the L2 reachability set requires:

`O(62)`

operations, which is constant for the frozen vPlan.

The expected experimental bottleneck remains RTL simulation and
checker/monitor execution rather than completeness bookkeeping.

---

## 19. Required Evidence

Before Gate T5 closes, the following evidence must exist.

### L1

* 20 truth-table rows;
* 20 L1 bin definitions;
* T01-T20 canonical directed targets;
* no unmapped truth-table row;
* no orphan L1 bin.

### L2

* exactly 62 defined bins;
* deterministic bin indexing;
* constructive d1 sequence for arbitrary eligible register;
* constructive d2 sequence for arbitrary eligible register;
* x0 exclusion;
* latest-writer rule;
* operand attribution rule;
* simultaneous dependency rule.

---

## 20. Consistency Checks

The following invariants must hold:

```text
L1_truth_table_rows == 20
L1_bins             == 20
L1_directed_targets == 20

L2_distances        == 2
L2_registers        == 31
L2_bins             == 62

L2_reachable_bins   == L2_bins
```

Any future modification violating one of these invariants requires
reopening the affected frozen artifact before comparative campaign
execution.

---

## 21. Freeze Conditions

This artifact may be marked PASS / FROZEN only when:

* all 20 L1 rows have exactly one L1 bin;
* all 20 L1 bins have a canonical directed-test target;
* all 62 L2 bins are constructively reachable;
* all exclusions are explicit;
* latest-writer attribution is preserved;
* operand attribution is unambiguous;
* stimulus dependency and DUT realization remain distinct;
* the completeness claim is restricted to the declared verification
  scope.

---

## 22. Freeze Status

Current status:

`READY FOR REVIEW`

After consistency review:

`PASS / FROZEN`

Next artifact:

`research/week5/vplan/SATURATION_PROTOCOL.md`
