# L2 COVERAGE MODEL

## 1. Purpose

This document freezes the Level-2 register-index coverage model for
architectural RAW dependencies within the declared verification scope.

L2 complements L1.

L1 covers behavioral hazard classes such as:

* producer type;
* consumer role;
* forwarding path;
* load interlock;
* forwarding priority;
* special writeback sources;
* negative semantic cases.

L2 covers register-index reachability for forwarding-sensitive RAW
dependencies without duplicating the L1 behavioral dimensions.

---

## 2. Normative Inputs

This model is derived from the frozen:

* `HAZARD_SPACE.md`
* `HAZARD_TRUTH_TABLE.md`
* `L1_COVERAGE_MODEL.md`
* `TIMING_CONTRACT.md`

No L2 rule may redefine the architectural dependency semantics frozen
by those artifacts.

---

## 3. RAW Register Identity Invariant

For an architectural RAW dependency:

`rd_producer == rs_dependent`

must hold.

`rs_dependent` means the architectural source register of the consumer
whose value is produced by the relevant prior instruction.

Therefore `rd_producer` and `rs_dependent` are not independent coverage
dimensions.

They are two roles referring to the same architectural register
identity for a valid RAW event.

---

## 4. Rejected 1,922-Bin Cartesian Product

A previously proposed formulation was:

`DependencyDistance × rd_producer × rs_dependent`

with:

`DependencyDistance in {d1, d2}`

and:

`rd_producer, rs_dependent in {x1, ..., x31}`

which would nominally produce:

`2 × 31 × 31 = 1,922`

tuples.

This Cartesian product is not a valid positive-RAW coverage model.

For a true dependency:

`rd_producer == rs_dependent`

so only 31 of the 961 register-pair combinations at each distance are
architecturally reachable as RAW dependencies.

Therefore:

`31 × 2 = 62`

positive dependency tuples are reachable.

The remaining:

`1,922 - 62 = 1,860`

off-diagonal tuples represent:

`rd_producer != rs_dependent`

and are not architectural RAW dependencies.

They shall not be included as positive L2 dependency bins.

---

## 5. Frozen L2 Definition

L2 is defined as:

`DependencyDistance × DependentRegister`

where:

`DependencyDistance in {d1, d2}`

and:

`DependentRegister in {x1, ..., x31}`

Therefore:

`2 × 31 = 62 bins`

The L2 cardinality is frozen at:

`62`

subject to final Gate T5 consistency review.

---

## 6. Bin Identity

Each L2 bin is uniquely represented by:

`(distance, register)`

where the register simultaneously identifies:

* `rd_producer`;
* the architecturally dependent consumer source.

Examples:

```text
(d1, x1)
(d1, x2)
...
(d1, x31)

(d2, x1)
(d2, x2)
...
(d2, x31)
```

There are exactly 62 such bins.

---

## 7. x0 Exclusion

`x0` is excluded from L2.

A write to `x0` does not create an architectural producer value.

Therefore:

`rd_producer == x0`

cannot create a positive architectural RAW dependency.

Similarly, a consumer reading `x0` does not depend on an earlier writer.

Thus the eligible register domain is strictly:

`{x1, ..., x31}`

The separately documented DUT behavior involving `x0` remains covered
through the relevant L1 negative/corner scenarios.

---

## 8. Operand Attribution

Consumer source operands must be evaluated using architectural source
semantics.

`rs1` and `rs2` are checked independently where both are architecturally
used.

If:

`rd_producer == rs1_consumer`

then an eligible dependency event may be attributed through `rs1`.

If:

`rd_producer == rs2_consumer`

then an eligible dependency event may be attributed through `rs2`.

Operand position is not an L2 coverage dimension.

Therefore both cases map to the same L2 register bin when their
dependency distance and architectural register identity are equal.

---

## 9. Duplicate Operand Case

If one consumer uses the same dependent register on both architectural
source operands, for example:

`rs1 == rs2 == rd_producer`

and both references correspond to the same producer-consumer dependency,
the L2 event maps to one bin:

`(distance, register)`

The unique coverage state receives one hit.

The collector shall not create two distinct L2 bins merely because the
dependency appears on both operand positions.

Diagnostic operand-level information may still be retained separately.

---

## 10. Simultaneous Independent Dependencies

A consumer may have two architecturally used source operands whose
values originate from different producers.

Example:

```text
producer A -> x5
producer B -> x9
consumer   -> uses x5 and x9
```

If the dependencies have distances `d2` and `d1` respectively, the
consumer event produces two independent L2 dependency attributions:

```text
(d2, x5)
(d1, x9)
```

Each dependency is classified separately.

This does not introduce `rs1` or `rs2` as an additional L2 dimension.

---

## 11. Latest-Writer Attribution

For each architecturally used consumer source, the dependency must be
attributed to the nearest preceding valid architectural writer of that
register in executed program order.

An older writer to the same register is shadowed by a newer writer.

Example:

```text
I0: writes x5
I1: writes x5
I2: reads  x5
```

`I2` depends on `I1`, not on `I0`.

Therefore the collector must not simultaneously count both:

```text
(d1, x5)
(d2, x5)
```

for the same source reference when the nearer writer supersedes the
older writer.

This rule prevents false dependency attribution.

---

## 12. Dependency Distance

Only:

`d1`

and:

`d2`

participate in L2.

Distance is defined in executed program order according to
`HAZARD_SPACE.md`.

It must not be inferred solely from raw cycle difference.

Stalls, bubbles, redirects, and other pipeline timing effects shall not
silently alter dependency distance.

`d3` behavior remains represented by L1 where Register-File visibility
and write-through behavior are explicitly verified.

---

## 13. Intent Hit

An L2 Intent Hit requires:

1. a valid architectural producer;
2. `rd != x0`;
3. a valid architectural consumer;
4. an architecturally used source equal to the producer destination;
5. nearest-writer attribution;
6. dependency distance equal to `d1` or `d2`.

The corresponding bin is:

`(distance, rd_producer)`

which is equivalent to:

`(distance, rs_dependent)`

for a valid RAW dependency.

---

## 14. Validated Hit

As in L1, L2 distinguishes stimulus reachability from DUT correctness.

A Validated Hit requires:

`ValidatedHit = IntentHit AND RealizationValid`

A DUT failure therefore produces:

```text
IntentHit    = 1
ValidatedHit = 0
```

and must also generate the appropriate checker mismatch.

The primary verification-closure metric uses validated bins.

Intent bins are retained separately for diagnostic analysis.

---

## 15. Coverage State

The collector shall maintain at least:

```text
intent_seen[62]
validated_seen[62]

intent_hit_count[62]
validated_hit_count[62]
```

Repeated occurrence of a bin does not increase unique coverage.

Hit counts remain useful for diagnostics and distribution analysis.

---

## 16. Deterministic Bin Indexing

Define:

```text
distance_index(d1) = 0
distance_index(d2) = 1

register_index(xN) = N - 1
```

for:

`1 <= N <= 31`

Then:

`bin_index = distance_index × 31 + register_index`

Hence:

```text
(d1, x1)  -> 0
(d1, x31) -> 30
(d2, x1)  -> 31
(d2, x31) -> 61
```

The valid array index range is:

`0 ... 61`

This permits constant-time L2 coverage updates.

---

## 17. A-Priori Reachability

Every one of the 62 L2 bins must be constructively reachable.

For any register:

`xR in {x1, ..., x31}`

a `d1` dependency can be constructed using a valid producer immediately
followed by a consumer that architecturally reads `xR`.

Conceptually:

```text
producer writes xR
consumer reads xR
```

A `d2` dependency can be constructed using one independent executed
instruction between producer and consumer:

```text
producer writes xR
independent filler
consumer reads xR
```

A semantically inert instruction such as:

`addi x0, x0, 0`

may be used as the filler where supported by the frozen ISA subset.

Because this construction applies to all 31 eligible registers and both
distances, all:

`31 × 2 = 62`

L2 bins are reachable a priori.

---

## 18. L1 / L2 Separation

L2 shall not create additional dimensions for:

* producer type;
* consumer instruction class;
* forwarding path;
* RS1 versus RS2 position;
* stall behavior;
* special writeback source.

Those behavioral distinctions belong to L1.

L2 answers a narrower question:

> Has each eligible architectural register been exercised as a real RAW
> dependency at each forwarding-sensitive dependency distance?

---

## 19. Coverage Metrics

Define:

`IntentBins_L2 = sum(intent_seen)`

and:

`ValidatedBins_L2 = sum(validated_seen)`

Then:

`C_L2_intent = IntentBins_L2 / 62`

and:

`C_L2_validated = ValidatedBins_L2 / 62`

The primary L2 closure metric is:

`C_L2_validated`

Intent coverage is reported separately.

---

## 20. Complexity

Dependency classification requires checking the architecturally used
source operands of the consumer.

Because the number of source operands is bounded by the ISA:

`T_classify = O(1)`

Bin lookup uses direct indexing:

`T_update = O(1)`

Coverage-state memory is:

`O(62) = O(1)`

for the frozen model.

The practical bottleneck remains simulation, checker execution, event
synchronization, and logging rather than L2 coverage bookkeeping.

---

## 21. Required Edge Cases

The implementation must explicitly handle:

* `rd == x0`;
* consumer source equal to `x0`;
* unused encoded source fields;
* `rs1 == rs2 == rd`;
* two independent dependencies in one consumer;
* newer writer shadowing an older writer to the same register;
* stalls and bubbles without corrupting executed-program-order distance;
* redirects and non-executed instructions;
* repeated hits of already covered bins;
* DUT failure after a valid Intent Hit.

---

## 22. Implication for Experimental Protocol

The corrected L2 cardinality changes the scale of the coverage-search
problem relative to the rejected 1,922-bin proposal.

Therefore any saturation threshold, Adaptive CGS reward expectation, or
pilot configuration that was motivated specifically by a 1,922-bin
space must be reviewed before Gate T5 is frozen.

No threshold shall be changed after observing comparative campaign
results.

Any correction must be made during pre-registration.

---

## 23. Freeze Conditions

This artifact may be marked PASS / FROZEN only when:

* RAW equality semantics are accepted;
* the rejected 1,922-bin Cartesian product is documented;
* L2 cardinality is 62;
* all 62 bins have an a-priori constructive reachability argument;
* `x0` is excluded;
* operand attribution is explicit;
* simultaneous dependency handling is explicit;
* latest-writer attribution is explicit;
* Intent and Validated Coverage remain separated;
* L1 behavioral dimensions are not duplicated.

---

## 24. Freeze Status

Current status:

`PASS / FROZEN`

Next artifact:

`research/week5/vplan/COMPLETENESS_MAPPING.md`
