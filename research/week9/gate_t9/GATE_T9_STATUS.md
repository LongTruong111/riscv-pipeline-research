# Week 9 — Gate T9 Status

## Status

**OPEN / BLOCKED**

Gate T9 is not closed because the frozen verification plan does not define a sufficiently explicit per-hit `L2 RealizationValid` contract.

No `gate-t9` tag shall be created while this blocker remains open.

## Verified Week-9 Results

### Deterministic coverage infrastructure

PASS.

The Week-9 coverage infrastructure provides deterministic L1/L2 state tracking, first-hit metadata, fixed-size bin state, checkpoint support, and streamed telemetry.

L1 contains exactly 20 frozen bins.

L2 contains exactly 62 frozen bins:

`DependencyDistance x DependentRegister`

with:

* distance in `{d1, d2}`;
* dependent register in `{x1, ..., x31}`.

### Authoritative L1 Validated attribution

PASS.

Week-9 L1 promotion preserves the frozen Week-5 validation semantics:

`ValidatedHit = IntentHit AND ControlPass AND ArchitecturalPass`

Week-7 hazard attribution and Week-8 performance results remain independent diagnostic evidence and do not redefine frozen L1 Validated coverage.

The canonical directed result remains:

* L1 Intent: `20 / 20`;
* L1 Validated: `15 / 20`;
* unvalidated bins: `H11 H13 H18 H19 H20`.

### Live integration

PASS.

The live Week-9 verification path was integrated with:

* frozen Week-5 execution events;
* L1 and L2 Intent classification;
* frozen L1 control realization;
* frozen architectural validation;
* Week-7 retire/hazard diagnostics;
* Week-8 performance diagnostics;
* Week-9 bounded live coverage coordination.

Transient attribution state is removed after resolution rather than retained for the complete campaign.

### Streaming functional equivalence

PASS.

The bounded Week-9 functional checker was compared against the frozen Week-8 FunctionalScoreboard semantics across all canonical directed cases.

No semantic difference was observed in the equivalence regression.

### Streaming timing/performance equivalence

PASS.

The streaming Timing Oracle v1 implementation reproduces the frozen Week-7 timing expectations without materializing a campaign-length timing schedule.

The bounded performance monitor reproduces frozen Week-8 performance results.

The combined streaming functional/timing equivalence regression passed:

`62 / 62`

### Week-9 unit regression

PASS.

`200 / 200`

Week-9 unit tests pass.

### Full frozen regression

PASS.

Final regression counts:

| Verification stage |    Result |
| ------------------ | --------: |
| Week 5             | 142 / 142 |
| Week 6             |   64 / 64 |
| Week 7             |   40 / 40 |
| Week 8             |   36 / 36 |
| Week 9             | 200 / 200 |
| Total              | 482 / 482 |

### Frozen-tree integrity

PASS.

The final comparison against `gate-t8` reports:

`frozen_diff=0`

No files under the frozen trees were modified:

* `design`;
* `research/week5`;
* `research/week6`;
* `research/week7`;
* `research/week8`.

## Benchmark v2

PASS for the implemented streaming verification path.

Configuration:

* 5 repetitions;
* 100,000 cycles per repetition;
* Verilator 5.034;
* Cocotb 1.9.2;
* bounded loop workload;
* fixed Golden-model data-memory address footprint.

Each run executed:

`66,668 executed instructions`

per:

`100,000 cycles`.

Median results:

| Metric                           |   Median |
| -------------------------------- | -------: |
| cycles/s                         | 5212.243 |
| instructions/s                   | 3474.898 |
| first-to-second-half degradation |  -0.869% |
| RSS start-to-mid delta           |  264 KiB |
| RSS start-to-end delta           |  284 KiB |
| slowdown vs T5 minimal           |  70.821% |
| slowdown vs T5 monitor           |  62.566% |

Across all five runs:

* functional failures: `0`;
* performance failures: `0`;
* maximum retained performance expectations: `3`;
* maximum retained functional expectations: `3`.

## Bounded-memory assessment

PASS for the implemented streaming path.

The retained functional and performance structures remained bounded by the number of in-flight instructions rather than campaign length.

Observed maxima were:

`max_retained_performance <= 3`

and:

`max_functional_pending <= 3`.

Median RSS increased by approximately:

`264 KiB`

during the first half of the 100k-cycle run and only approximately:

`20 KiB`

additional RSS from midpoint to end.

No near-linear retained-state growth with executed-instruction count was observed.

The benchmark workload also uses a fixed Golden-model data-memory address footprint, preventing sparse architectural memory from growing with campaign length.

## Throughput assessment

PASS for stability; substantial instrumentation overhead remains.

Median first-to-second-half throughput degradation was:

`-0.869%`

so progressive degradation with campaign length was not observed.

Absolute verification overhead remains significant:

* `70.821%` slowdown versus the T5 minimal baseline;
* `62.566%` slowdown versus the T5 monitor baseline.

This overhead is retained as a verification-economics result and is not treated as a correctness failure.

At median measured throughput, the estimated runtime for 100,000 executed instructions is approximately:

`28.78 s`

for the benchmark workload and environment.

## L2 Validated Coverage Blocker

BLOCKED.

The frozen L2 specification states:

`ValidatedHit = IntentHit AND RealizationValid`

but does not define a complete per-`L2Hit` realization algorithm.

The frozen implementation provides:

* L2 Intent classification;
* L2 Validated state storage;
* `promote_validated()` as a state-promotion primitive.

However, no frozen Week-5 through Week-8 component defines the authoritative mapping:

`L2Hit -> required evidence -> RealizationValid`.

In particular, no frozen rule maps an arbitrary `(distance, register)` L2 hit to one L1 behavioral bin.

Such a mapping cannot be inferred because L2 explicitly excludes the following behavioral dimensions:

* producer type;
* consumer instruction class;
* forwarding path;
* RS1 versus RS2;
* stall behavior;
* special writeback source.

Those distinctions are assigned to L1.

Therefore Week 9 intentionally records L2 Intent only and does not invent L2 Validated promotion.

See:

`research/week9/gate_t9/L2_VALIDATION_SPEC_GAP.md`

## Gate T9 Decision

### PASS

* deterministic coverage infrastructure;
* L1 authoritative validated attribution;
* live L1 verification integration;
* streaming functional equivalence;
* streaming timing/performance equivalence;
* bounded retained verification state;
* 5 x 100k-cycle benchmark;
* RSS stability;
* throughput/runtime measurement;
* checkpoint/telemetry infrastructure;
* complete Week5–Week9 regression;
* frozen Week5–Week8 tree integrity.

### BLOCKED

* authoritative L2 `RealizationValid` evaluation;
* live L2 Validated promotion;
* L2 validated near-closure metrics;
* L2 validated full-closure metrics;
* final Gate T9 closure.

## Resolution Required

Gate T9 may be closed only after a new explicit L2 realization contract is frozen.

That contract must define, for each concrete `L2Hit`:

1. authoritative control evidence;
2. authoritative architectural evidence;
3. producer/consumer attribution requirements;
4. forwarding correctness requirements;
5. handling of simultaneous L2 hits;
6. repeated-hit promotion semantics after an earlier failed realization;
7. the exact relationship, if any, between L1 validation and L2 validation;
8. behavior when authoritative and diagnostic evidence disagree.

Until then:

**Gate T9 remains OPEN / BLOCKED.**
