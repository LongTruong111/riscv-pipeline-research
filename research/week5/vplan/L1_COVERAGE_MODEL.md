# L1 COVERAGE MODEL

## 1. Purpose

This document freezes the Level-1 functional coverage model for the
declared pipeline hazard verification scope.

L1 is a behavioral coverage layer derived directly from:

* `HAZARD_SPACE.md`
* `HAZARD_TRUTH_TABLE.md`
* `TIMING_CONTRACT.md`
* `HAZARD_SIGNAL_MAP.md`

The L1 model contains exactly:

`20 bins`

with the required traceability:

`20 truth-table rows <-> 20 L1 bins <-> 20 directed-test targets`

This document does not redefine the hazard taxonomy or introduce new
behavioral classes.

---

## 2. Normative Precedence

If this document appears to conflict with an already frozen definition,
the following precedence applies:

1. architectural dependency semantics: `HAZARD_SPACE.md`;
2. behavioral scenario definition: `HAZARD_TRUTH_TABLE.md`;
3. observation timing: `TIMING_CONTRACT.md`;
4. observable RTL signal mapping: `HAZARD_SIGNAL_MAP.md`;
5. this document defines only coverage representation and hit accounting.

No new hazard class may be introduced through the collector.

---

## 3. L1 Bin Set

The frozen bin set is:

| Bin | Directed Target |
| --- | --------------- |
| H01 | T01             |
| H02 | T02             |
| H03 | T03             |
| H04 | T04             |
| H05 | T05             |
| H06 | T06             |
| H07 | T07             |
| H08 | T08             |
| H09 | T09             |
| H10 | T10             |
| H11 | T11             |
| H12 | T12             |
| H13 | T13             |
| H14 | T14             |
| H15 | T15             |
| H16 | T16             |
| H17 | T17             |
| H18 | T18             |
| H19 | T19             |
| H20 | T20             |

The semantic definition of each bin is the corresponding frozen row in
`HAZARD_TRUTH_TABLE.md`.

The collector shall not duplicate or independently reinterpret those
definitions.

---

## 4. Two-Level Coverage Accounting

Two distinct hit concepts are required.

### 4.1 Intent Hit

An `IntentHit(Hxx)` records that the stimulus and architectural
dependency conditions corresponding to bin `Hxx` occurred.

Intent coverage answers:

> Did the verification campaign exercise the scenario?

A DUT functional or timing failure does not erase an already identified
Intent Hit.

This preserves the frozen rule from `HAZARD_TRUTH_TABLE.md` that
scenario occurrence and DUT correctness are separate observations.

---

### 4.2 Validated Hit

A `ValidatedHit(Hxx)` requires:

1. the corresponding Intent Hit occurred;
2. the relevant instruction/event reached a valid observable state;
3. architectural behavior was consistent with the bin semantics;
4. required timing/control behavior was not contradicted by observation.

Formally:

`ValidatedHit(Hxx) = IntentHit(Hxx) AND RealizationValid(Hxx)`

Validated coverage answers:

> Did the campaign exercise the scenario and did the DUT realize the
> expected architectural/microarchitectural behavior?

A mismatch shall therefore produce:

`IntentHit = 1`

and:

`ValidatedHit = 0`

for that observation.

The mismatch must also be reported by the corresponding checker.

---

## 5. Primary Coverage Metric

The primary L1 coverage metric used for verification closure is:

`C_L1_validated`

defined as:

`number of unique validated L1 bins / 20`

Intent coverage shall be reported separately as:

`C_L1_intent`

defined as:

`number of unique intent L1 bins / 20`

This prevents a DUT failure from hiding stimulus reachability while also
preventing an incorrect DUT execution from being counted as verified
behavior.

The two metrics must never be merged into a single ambiguous
`coverage` counter.

---

## 6. Positive RAW Intent Predicate

For a positive RAW L1 bin, an Intent Hit requires semantic
qualification according to the frozen hazard model:

`ValidProducer`

AND

`ValidConsumer`

AND

`rd != x0`

AND

`rd == architecturally-used source`

AND

`required dependency distance`

AND

`bin-specific producer/consumer condition`

Raw instruction fields alone are insufficient evidence of an
architectural dependency.

The collector must use architectural source-usage semantics rather than
blind equality against encoded `rs1` or `rs2` fields.

---

## 7. Negative Semantic Bins

Bins H18-H20 represent explicitly defined negative/corner scenarios.

Their Intent Hit is caused by occurrence of the frozen stimulus and
semantic condition.

The suspected incorrect DUT behavior is not required for an Intent Hit.

For validated accounting, however, the expected negative behavior must
also hold.

Therefore a negative-case DUT defect produces:

`IntentHit = 1`

`ValidatedHit = 0`

plus a checker mismatch.

This preserves both stimulus observability and correctness accounting.

---

## 8. RS1 / RS2 Semantics

Architectural source usage is determined by the frozen consumer class.

Where the instruction has two architecturally used source operands,
`rs1` and `rs2` must be evaluated independently.

L1 retains RS1-versus-RS2 behavioral distinctions where they are
explicitly represented by the frozen H01-H20 truth table.

This operand-position distinction shall not automatically become an
additional L2 coverage dimension.

---

## 9. Dependency Distance

Dependency distance follows executed program order as frozen in
`HAZARD_SPACE.md`.

The collector shall not infer dependency distance using only raw cycle
difference.

Pipeline stalls, redirects, bubbles, or implementation latency must not
silently redefine architectural producer-consumer distance.

Any L1 bin requiring a specific distance must use the frozen distance
definition associated with that truth-table row.

---

## 10. Sampling Contract

All observations shall follow `TIMING_CONTRACT.md`.

Pipeline state must be sampled at:

`RisingEdge(clk) -> ReadOnly()`

Pre-edge control intent, where required, must be sampled at:

`FallingEdge(clk) -> ReadOnly()`

No L1 hit may be inferred from unsettled same-edge values.

Collector implementation must therefore separate:

* event acquisition;
* stable signal sampling;
* semantic classification;
* checker result;
* coverage update.

---

## 11. Event Record

Each qualified L1 event should expose at least the following logical
fields:

```text
event_id
cycle
producer_pc
consumer_pc
producer_rd
consumer_rs1
consumer_rs2
producer_type
consumer_type
dependency_distance
matched_source
l1_bin
intent_hit
realization_valid
validated_hit
checker_status
```

Fields unavailable for a particular bin may be represented explicitly
as not applicable.

The event format must not require RTL implementation details that are
unnecessary for architectural classification.

---

## 12. Collector Processing Model

For each qualified event:

1. acquire stable observation;
2. determine architectural producer/consumer validity;
3. classify dependency and distance;
4. evaluate frozen L1 predicates;
5. record any matching Intent Hit;
6. obtain realization/checker result;
7. promote the event to Validated Hit only if realization is valid;
8. log mismatches separately.

Coverage shall be accumulated by unique bin identity.

Repeated hits increment diagnostic hit counts but do not increase the
number of covered bins.

---

## 13. Hit Multiplicity

For each L1 bin the collector should maintain:

```text
intent_hit_count[Hxx]
validated_hit_count[Hxx]
```

and unique-hit state:

```text
intent_seen[Hxx]
validated_seen[Hxx]
```

The coverage numerator uses `*_seen`, not total hit count.

Hit counts are retained for diagnostics and distribution analysis.

---

## 14. Closure Calculation

For `B = 20` frozen bins:

`IntentBins = sum(intent_seen[H01:H20])`

`ValidatedBins = sum(validated_seen[H01:H20])`

Therefore:

`C_L1_intent = IntentBins / 20`

and:

`C_L1_validated = ValidatedBins / 20`

The main closure metric is `C_L1_validated`.

Intent coverage is an auxiliary diagnostic metric.

---

## 15. Directed-Test Traceability

Each L1 bin must have exactly one canonical directed-test target:

`H01 <-> T01`

...

`H20 <-> T20`

A directed test may exercise additional bins incidentally.

Such incidental hits may be recorded if all corresponding semantic
predicates are satisfied.

However, incidental coverage does not replace the canonical directed
test required for traceability.

---

## 16. Scoreboard Independence

The collector and scoreboard must remain logically separable.

For Intent Coverage:

`coverage classification != scoreboard pass/fail`

For Validated Coverage:

`validated hit = intent classification + successful realization`

The scoreboard shall not alter stimulus history.

A failure shall therefore remain reproducible from the event log even
when the bin is not accepted into validated closure.

---

## 17. Forwarding Signals

Forwarding-select signals may be used as hardware cross-checks where
available.

They are not universally required for coverage attribution if the
corresponding behavior can be established from architectural retirement,
timing, stall/flush observations, and the frozen oracle contract.

Coverage must not become dependent on optional internal probes unless
the corresponding truth-table row explicitly requires them.

---

## 18. Complexity

Let `B` be the number of L1 predicates evaluated per qualified event.

Generic collector complexity is:

`T_event = O(B)`

For this frozen verification plan:

`B = 20`

Therefore:

`T_event = O(20) = O(1)`

with respect to campaign length.

Coverage state memory is:

`O(B) = O(20) = O(1)`

for the frozen model.

The expected practical bottleneck remains RTL simulation, event
synchronization, checker execution, and trace/log I/O rather than the
L1 predicate scan.

---

## 19. Logging Constraint

Coverage logging must be event-based or checkpoint-based.

The collector shall not write CSV data every cycle.

At minimum, persistent output should include:

* newly discovered Intent bins;
* newly discovered Validated bins;
* checker mismatches;
* configured coverage checkpoints;
* final per-bin hit counts.

Buffered or batched output should be used where practical.

This prevents logging overhead from contaminating later wall-clock
performance measurements.

---

## 20. Edge Cases

The implementation must preserve the following conditions:

* `rd == x0` is not a positive architectural RAW dependency;
* unused encoded source fields must not create positive dependencies;
* repeated observation of the same bin does not increase unique
  coverage;
* a DUT mismatch does not erase Intent Coverage;
* a DUT mismatch does prevent promotion to Validated Coverage;
* redirected or non-executed instructions must not be treated as valid
  architectural consumers unless explicitly required by the frozen bin
  definition;
* same-edge unstable signal values must not be used for classification.

---

## 21. Required Implementation Metrics

When the L1 collector is implemented, record at least:

```text
C_L1_intent
C_L1_validated
unique_intent_bins
unique_validated_bins
intent_hit_count per bin
validated_hit_count per bin
checker_mismatch_count
instructions_observed
cycles_observed
collector wall-clock overhead
```

These metrics are required to distinguish verification effectiveness
from instrumentation cost.

---

## 22. Freeze Conditions

This artifact may be marked PASS / FROZEN only when:

* the bin cardinality remains exactly 20;
* every H01-H20 maps to the corresponding frozen truth-table row;
* every H01-H20 maps to T01-T20;
* Intent and Validated Coverage are explicitly separated;
* positive RAW qualification uses architectural source semantics;
* negative cases H18-H20 preserve scenario-versus-correctness
  separation;
* the frozen timing contract is referenced;
* no new hazard class is introduced;
* no scoreboard result is allowed to modify Intent Coverage.

---

## 23. Freeze Status

Current candidate status:

`READY FOR REVIEW`

After consistency review against the four frozen input artifacts:

`PASS / FROZEN`

Next artifact after freeze:

`research/week5/vplan/L2_COVERAGE_MODEL.md`
