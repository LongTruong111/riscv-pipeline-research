# EXPERIMENTAL PROTOCOL

## 1. Purpose

This document freezes the comparative experimental design for evaluating
four verification-stimulus methods:

1. Directed;
2. Pure Random;
3. Weighted Random;
4. Adaptive CGS.

The protocol is defined before the comparative campaign begins.

No method definition, seed count, budget, metric definition, or
comparison rule may be modified after comparative results have been
inspected.

---

## 2. Normative Inputs

The experiment depends on the frozen:

* `ISA_SUBSET.md`;
* `TIMING_CONTRACT.md`;
* `HAZARD_SPACE.md`;
* `HAZARD_TRUTH_TABLE.md`;
* `L1_COVERAGE_MODEL.md`;
* `L2_COVERAGE_MODEL.md`;
* `COMPLETENESS_MAPPING.md`;
* `SATURATION_PROTOCOL.md`;
* `ADAPTIVE_CGS_SPEC.md`;
* `PERFORMANCE_BASELINE.md`.

All methods use the same DUT revision, scoreboard, coverage collector,
timing contract, environment, and closure definitions.

---

## 3. Experimental Questions

The experiment evaluates:

1. how efficiently each stochastic generation method discovers the
   frozen L2 coverage space;
2. whether static coverage-oriented weighting improves over unguided
   random generation;
3. whether Adaptive CGS improves coverage discovery efficiency over
   non-adaptive methods;
4. what runtime overhead is introduced by adaptive generation and
   verification instrumentation;
5. whether functional correctness and performance/timing correctness
   expose different classes of DUT failure.

---

## 4. Four-Method Protocol

The frozen methods are:

```text
M0  Directed
M1  Pure Random
M2  Weighted Random
M3  Adaptive CGS
```

No additional generation method shall be introduced into the primary
comparative campaign after results are observed.

UCB1, Thompson Sampling, Deep RL, and other adaptive policies are
outside the main experiment.

---

## 5. M0 — Directed

Directed verification consists of the canonical:

`T01 ... T20`

targets frozen in:

`HAZARD_TRUTH_TABLE.md`.

Each directed target is designed to demonstrate explicit reachability
and to evaluate functional realization of its corresponding L1 bin.

A reached Intent condition demonstrates scenario reachability.
Functional realization is established only when the corresponding
Validated Coverage and checker requirements pass.

The required mapping remains:

`H01 <-> T01`

through:

`H20 <-> T20`.

Directed testing is not treated as a stochastic random-family method.

Therefore Directed does not receive:

`n = 15`

independent random seeds.

Its results are reported separately as deterministic verification
evidence.

Incidental coverage obtained during a directed test may be recorded but
does not replace another target's canonical directed obligation.

---

## 6. M1 — Pure Random

Pure Random uses no coverage feedback.

It shall not:

* inspect covered or uncovered L1/L2 bins;
* select template families based on coverage state;
* use adaptive utility estimates;
* intentionally select dependency targets from uncovered registers.

Instruction generation is sampled from the common frozen legal
generator domain derived from the DUT ISA subset.

Register and operand choices are stochastic and shall not use
coverage-guided uncovered-register targeting.

Pure Random represents the unguided stochastic baseline.

Any generator legality constraints apply equally before and after
coverage observation and must not depend on campaign progress.

---

## 7. M2 — Weighted Random

Weighted Random uses the same positive dependency template families as
Adaptive CGS but has:

* no adaptive utility;
* no reward history;
* no epsilon-greedy policy;
* no uncovered-register feedback.

Template-family probabilities remain fixed throughout the run.

The static weights are derived from the number of positive L1
truth-table scenarios represented by each Adaptive CGS arm.

The frozen probabilities are:

| Arm                | Frozen weight |
| ------------------ | ------------: |
| A0 `ALU_D1`        |          2/16 |
| A1 `ALU_D2`        |          2/16 |
| A2 `LOAD_D1`       |          2/16 |
| A3 `LOAD_D2`       |          2/16 |
| A4 `DUAL_D1_D2`    |          1/16 |
| A5 `SPECIAL_WB_D1` |          2/16 |
| A6 `SPECIAL_WB_D2` |          2/16 |
| A7 `LINK_D1`       |          1/16 |
| A8 `STORE_DATA_D1` |          1/16 |
| A9 `PRIORITY_D1`   |          1/16 |

The weights sum to:

`16/16 = 1`.

These probabilities are not pilot-tuned.

They shall not change during a run.

---

## 8. Weighted-Random Register Selection

Weighted Random selects dependency target registers uniformly over:

`{x1, ..., x31}`

subject only to semantic constraints of the selected template.

It shall not prefer uncovered bins.

Thus:

`P(xR) = 1 / 31`

for an otherwise eligible target register.

For A4, two distinct target registers are selected uniformly without
replacement.

This preserves a clear distinction from Adaptive CGS uncovered-first
register targeting.

---

## 9. M3 — Adaptive CGS

Adaptive CGS is exactly the algorithm frozen in:

`ADAPTIVE_CGS_SPEC.md`.

The comparative campaign uses only the single final hyperparameter
configuration selected by the pre-registered pilot procedure.

The comparative experiment shall not use pilot outcomes to change:

* arm taxonomy;
* reward definition;
* candidate space;
* register-target semantics;
* `Q_floor`;
* stopping rule;
* final evaluation metrics.

---

## 10. Pilot / Evaluation Separation

Pilot data is used exclusively to select the final Adaptive CGS
hyperparameter configuration.

Pilot seeds are:

```text
101
202
303
```

Pilot results shall not be merged with the final comparative dataset.

The comparative evaluation seeds are disjoint from all pilot seeds.

This prevents pilot observations from increasing the effective sample
size of Adaptive CGS relative to the other stochastic methods.

---

## 11. Random-Family Sample Size

The random-family methods are:

* Pure Random;
* Weighted Random;
* Adaptive CGS.

Each uses exactly:

`n = 15 independent seeds`.

No method may receive additional seeds after preliminary results are
observed.

No valid seed may be dropped because its result appears unusually good
or bad.

Runs classified as technically invalid follow the invalid-run protocol
defined later in this document.

---

## 12. Frozen Evaluation Seeds

The seed sets are disjoint.

### Pure Random

```text
1001
1002
1003
1004
1005
1006
1007
1008
1009
1010
1011
1012
1013
1014
1015
```

### Weighted Random

```text
2001
2002
2003
2004
2005
2006
2007
2008
2009
2010
2011
2012
2013
2014
2015
```

### Adaptive CGS

```text
3001
3002
3003
3004
3005
3006
3007
3008
3009
3010
3011
3012
3013
3014
3015
```

These sets are disjoint from pilot seeds:

`{101, 202, 303}`.

---

## 13. RNG Independence

Every stochastic run receives exactly one top-level experiment seed.

All stochastic choices for that run must derive reproducibly from that
seed.

No run may use:

* wall-clock time;
* OS entropy;
* an unseeded secondary RNG;

as an experimental random source.

Different methods use disjoint seed sets so that observations are
treated as independent samples in the planned between-method
statistical analysis.

---

## 14. Common Instruction Budget

All random-family methods use:

`N_max = 100,000 executed instructions`

per seed.

The executed-instruction definition is inherited from:

`SATURATION_PROTOCOL.md`.

A cycle is not automatically equivalent to one executed instruction.

Stalls, flushes, and bubbles therefore do not receive artificial
instruction-budget credit.

---

## 15. Common Coverage Checkpoints

All random-family methods use the same checkpoint interval:

`1,000 executed instructions`.

At each checkpoint record at least:

* L1 Intent bins;
* L1 Validated bins;
* L2 Intent bins;
* L2 Validated bins;
* newly discovered L2 Intent bins;
* newly discovered L2 Validated bins;
* checker mismatch count;
* wall-clock elapsed time.

Method-specific telemetry may be added but shall not replace these
common fields.

---

## 16. Common DUT and Verification Stack

Every comparative run shall use the same:

* frozen RTL revision;
* simulator version;
* Cocotb version;
* scoreboard implementation;
* functional coverage collector;
* performance monitor;
* reset protocol;
* memory adapter;
* timing/sampling contract;
* logging policy.

A method may alter stimulus generation only.

It may not use a more permissive checker or different coverage
semantics.

---

## 17. Filesystem and Runtime Environment

Comparative runs shall execute from the Linux-native project workspace.

The frozen workspace class is:

`ext4`

under:

`/home/...`.

Main comparative runs shall not execute directly from Windows-mounted
paths such as:

`/mnt/c/...`.

Waveform dumping and verbose per-cycle console logging remain disabled
for primary performance measurements.

Diagnostic reruns using waveforms are outside the primary performance
dataset.

---

## 18. Intent and Validated Metrics

Two coverage views are reported.

### Intent Coverage

Measures whether generated stimulus reaches the declared architectural
dependency/scenario.

Intent Coverage primarily measures stimulus-generation effectiveness.

### Validated Coverage

Requires the scenario plus correct observed DUT realization according
to the frozen checker/oracle contract.

Validated Coverage primarily measures verification closure.

The two shall not be merged into one ambiguous coverage metric.

---

## 19. Primary Comparative Metrics

For every stochastic run report at least:

```text
n@95%_intent
n@95%_validated

bins@100k_intent
bins@100k_validated

AUC_intent
AUC_validated

full_intent_closure
full_validated_closure

tail_rate_intent
tail_rate_validated

wall_clock_total
instructions_per_second
cycles_per_second

checker_mismatch_count
```

For L2:

`near closure = 59 / 62`

and:

`full closure = 62 / 62`.

---

## 20. n@95% Semantics

`n@95%_intent`

is the first executed-instruction index at which:

`59/62`

L2 Intent bins are reached.

`n@95%_validated`

is the first executed-instruction index at which:

`59/62`

L2 Validated bins are reached.

A run that never reaches the corresponding threshold within:

`N_max`

does not receive an invented time-to-threshold value.

Its result is recorded as:

`not reached within budget`.

Such observations are right-censored for time-to-threshold analysis.

They shall not be replaced by an artificial value of:

`100,000`.

---

## 21. Fixed-Budget Metrics

At:

`N = 100,000 executed instructions`

report:

`bins@100k_intent`

and:

`bins@100k_validated`.

These metrics permit comparison when one or more runs fail to reach the
95% threshold.

Final-window discovery rate is retained according to the frozen
saturation protocol.

Intent and Validated tail rates must remain explicitly distinguished.

### Intent Tail-Rate Definition

For descriptive comparison, define the Intent tail rate over the same
final window:

`W = 20,000 executed instructions`.

Let:

`DeltaB_intent_tail`

be the number of previously unseen L2 Intent bins first discovered in
the final 20,000 executed instructions.

Then:

`tail_rate_intent =
    DeltaB_intent_tail / (W / 1000)`

with units:

`new Intent bins / 1,000 executed instructions`.

This metric is descriptive only.

The frozen saturation threshold:

`theta_tail = 0.05`

applies only to:

`tail_rate_validated`

as defined in `SATURATION_PROTOCOL.md`.

No Intent-based saturation decision is introduced.

---

## 22. Coverage AUC

Coverage discovery over the complete budget is summarized using
normalized coverage AUC.

For a coverage type `X`:

`C_X(N) = covered L2 bins of type X at instruction count N / 62`.

Then:

`AUC_X = (1 / N_max) × integral_0^Nmax C_X(N) dN`.

The implementation may approximate the integral using trapezoidal
integration over the frozen 1,000-instruction checkpoints.

Report independently:

* `AUC_intent`;
* `AUC_validated`.

Both lie in:

`[0,1]`.

Higher AUC means coverage was achieved earlier within the fixed budget.

---

## 23. Adaptive Overhead Metric

Adaptive CGS may reduce instruction cost while increasing host
computation time.

Therefore report separately:

* instruction efficiency;
* wall-clock efficiency.

At minimum:

`T_wall`

shall include the complete simulation and verification workload for the
run.

Method-specific policy-processing time should additionally be
instrumented where practical.

The experiment shall not equate fewer executed instructions with lower
wall-clock cost without measurement.

---

## 24. Campaign Ordering

Run order may interact with:

* host load;
* thermal state;
* filesystem cache;
* other time-varying host effects.

Therefore stochastic runs shall not be executed as three large
method-contiguous blocks.

Before campaign execution, construct one deterministic randomized
schedule containing all:

`45 stochastic evaluation runs`.

The frozen schedule RNG seed is:

`20260919`.

The generated schedule shall be committed before comparative results
are inspected.

---

## 25. Run Identity

Every stochastic run shall have a unique identity containing at least:

```text
method
seed
DUT revision
generator revision
configuration revision
simulator version
timestamp
```

Adaptive runs shall additionally identify the selected frozen
hyperparameter configuration.

Pilot and final evaluation runs must be clearly distinguishable.

---

## 26. Invalid-Run Definition

A run is technically invalid only when measurement is compromised by an
infrastructure or execution failure, such as:

* simulator crash;
* corrupted or missing stimulus artifact;
* required telemetry loss;
* incorrect DUT revision;
* incorrect generator/configuration revision;
* host termination before the prescribed stopping condition.

A DUT functional mismatch does not make a run invalid.

A checker-detected DUT failure is experimental data.

Low coverage does not make a run invalid.

---

## 27. Invalid-Run Replacement

A technically invalid run may be repeated using exactly the same:

`method + seed + frozen configuration`

after the infrastructure problem is corrected.

The failed attempt must remain in the audit record.

A replacement run does not receive a new seed.

Thus replacement restores the intended experimental observation rather
than increasing sample size.

---

## 28. Directed Failure Semantics

If a directed target reaches its Intent condition but the DUT fails its
corresponding realization/checker requirement:

* the target remains demonstrated as reachable;
* Intent Coverage may record the scenario;
* Validated Coverage does not record a validated hit;
* the checker failure remains experimental evidence.

A directed sequence shall not be changed merely to make a DUT failure
disappear.

---

## 29. Mutation Independence Rule

Mutation-based checker validation, if used, is methodologically
separate from the four-method comparative campaign.

Any mutation set shall be frozen before its results are used for
validation.

The same mutation definitions shall apply independently of the
stimulus-generation method.

A mutation shall not be introduced specifically because one
comparative method exposed or failed to expose a particular behavior.

Mutation results shall not be used to tune:

* Adaptive CGS hyperparameters;
* Weighted Random probabilities;
* Pure Random probabilities;
* stopping thresholds.

Mutation results shall be reported separately from main-DUT
coverage-efficiency results.

---

## 30. Pre-Registered Hypotheses

### H1

Pure Random exhibits a stronger long-tail effect than the
coverage-oriented generators.

Operational evidence includes:

* tail-rate behavior;
* threshold-reach frequency;
* residual uncovered bins at fixed budget.

### H2

Weighted Random reduces instruction cost relative to Pure Random for L2
coverage discovery.

The comparison uses frozen instruction-based metrics.

### H3

Adaptive CGS improves coverage discovery efficiency relative to the
non-adaptive stochastic methods.

Evidence is evaluated using:

* threshold-reaching behavior;
* fixed-budget coverage;
* coverage AUC.

No claim is made when statistical evidence is insufficient.

### H4

Any Adaptive CGS instruction-efficiency advantage may be reduced by
adaptive-policy and instrumentation overhead.

Therefore both instruction-based and wall-clock metrics are required.

### H5

The performance/timing monitor can detect excess-stall or timing
behavior that an architectural functional scoreboard alone may not
identify.

Functional and performance correctness are therefore reported as
distinct verification observations.

---

## 31. Claim Boundary

The experiment evaluates the declared pipeline-hazard verification
scope.

It shall not claim:

`complete verification of RV32I`.

The permitted completeness statement remains:

`complete within the declared verification scope`

when all frozen closure obligations are satisfied.

---

## 32. Experimental Data Immutability

After comparative execution begins:

* raw run logs are immutable;
* original checkpoint files are immutable;
* failed-run evidence is retained;
* corrections are made through derived artifacts rather than silently
  editing raw measurements.

Any excluded run must have an explicit technical reason satisfying the
invalid-run definition.

---

## 33. Complexity and Bottlenecks

For a run containing:

`N`

executed instructions, simulation workload is at least:

`O(N)`.

Coverage and scoreboard processing are also expected to scale
approximately linearly with execution events.

The principal expected bottlenecks are:

* RTL simulation;
* Cocotb synchronization;
* scoreboard/checker work;
* coverage-event classification;
* file/log I/O.

Adaptive arm selection operates over only 10 arms and is not expected
to dominate runtime.

---

## 34. Freeze Conditions

This protocol may be marked PASS / FROZEN only when:

* all four methods are explicitly defined;
* Directed is separated from stochastic sample-size analysis;
* Pure Random uses no coverage feedback;
* Weighted Random probabilities are fixed;
* Weighted Random does not use uncovered-register targeting;
* Adaptive CGS references only the frozen final configuration;
* stochastic sample size is exactly 15 seeds per method;
* evaluation seeds are frozen and disjoint;
* pilot/evaluation separation is explicit;
* all stochastic methods use the same instruction budget;
* common coverage/checker semantics are explicit;
* Intent and Validated metrics remain separate;
* right-censored `n@95%` runs are not assigned artificial threshold
  times;
* invalid-run rules are frozen;
* mutation independence is explicit;
* hypotheses H1-H5 are frozen;
* the claim boundary is explicit.

---

## 35. Freeze Status

Current status:

`PASS / FROZEN`

Next artifact:

`research/week5/vplan/STATISTICAL_PROTOCOL.md`
