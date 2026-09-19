# SATURATION AND COVERAGE-CLOSURE PROTOCOL

## 1. Purpose

This document freezes the stopping, plateau, long-tail, and
fixed-budget measurement protocol for the Week-5 verification plan.

The protocol applies to the frozen coverage models:

* L1: 20 behavioral bins;
* L2: 62 register-distance bins.

It is defined before comparative campaign execution and shall not be
changed after observing comparative results.

---

## 2. Normative Inputs

This protocol is derived from:

* `HAZARD_SPACE.md`
* `HAZARD_TRUTH_TABLE.md`
* `L1_COVERAGE_MODEL.md`
* `L2_COVERAGE_MODEL.md`
* `COMPLETENESS_MAPPING.md`

The former 1,922-bin L2 proposal is not used.

All saturation thresholds in this document therefore refer to the
corrected frozen L2 cardinality:

`62 bins`

---

## 3. Coverage Domain

### L1

Frozen cardinality:

`B_L1 = 20`

### L2

Frozen cardinality:

`B_L2 = 62`

The primary closure metrics use Validated Coverage.

Intent Coverage is retained separately for diagnosis but does not
constitute verification closure.

---

## 4. Instruction Budget

The maximum stimulus budget per campaign run is:

`N_max = 100,000 executed instructions`

Only executed instructions count toward this budget.

Flushed or otherwise non-executed instructions do not increment the
architectural instruction budget.

All compared generation methods shall use the same definition.

---

## 5. Coverage Checkpoints

Periodic coverage checkpoints occur every:

`Delta = 1,000 executed instructions`

Hence checkpoint indices are:

`1,000, 2,000, ..., 100,000`

for a run reaching the full budget.

Checkpoint logging is used for campaign curves and long-tail analysis.

Exact first-hit instruction indices should also be retained
event-by-event so that threshold-crossing measurements are not limited
to 1,000-instruction resolution.

---

## 6. Monotonicity

Unique coverage is monotonic within a run.

Therefore:

`B_validated(N + Delta) >= B_validated(N)`

and:

`B_intent(N + Delta) >= B_intent(N)`

for increasing executed-instruction budget N.

A decrease in unique-bin count indicates an instrumentation or state
management defect.

Per-seed coverage state is reset before each independent run.

---

## 7. L1 Coverage Thresholds

L1 full validated closure is:

`20 / 20`

or:

`C_L1_validated = 100%`

The previously specified 95% threshold corresponds, for 20 discrete
bins, to:

`19 / 20 = 95%`

Therefore 95% is retained only as a near-closure / plateau-entry
threshold.

It is not sufficient for final L1 closure.

---

## 8. L1 Plateau Rule

An L1 run is considered to have entered a plateau candidate state when:

`C_L1_validated >= 95%`

that is:

`validated_L1_bins >= 19`

Plateau evidence additionally requires no new validated L1 bin during:

`3`

consecutive windows of:

`W = 20,000 executed instructions`

Thus the total no-progress observation span is:

`60,000 executed instructions`

subject to the global:

`N_max = 100,000`

cap.

L1 plateau classification does not convert 19/20 coverage into full
closure.

The missing bin remains an explicit residual obligation.

---

## 9. L2 Near-Closure Threshold

For:

`B_L2 = 62`

a 95% threshold requires:

`ceil(0.95 × 62) = 59 bins`

because:

`58 / 62 < 95%`

and:

`59 / 62 > 95%`

Therefore:

`L2 near-closure = validated_L2_bins >= 59`

This is a long-tail analysis threshold.

It is not the full closure condition.

---

## 10. L2 Full Closure

L2 full validated closure requires:

`62 / 62`

validated bins.

Since all 62 bins have been established as a-priori reachable, an
uncovered bin is not automatically waived as unreachable.

Any proposed exclusion requires reopening the frozen reachability model
with explicit evidence before comparative campaign execution.

---

## 11. Tail Observation Window

L2 tail behavior is measured over a window:

`W = 20,000 executed instructions`

At a checkpoint N, define:

`DeltaB_L2_new(W)`

as the number of previously unseen validated L2 bins first discovered
within:

`(N - W, N]`

for:

`N >= W`

The tail discovery rate is:

`r_tail(N) = DeltaB_L2_new(W) / (W / 1000)`

with unit:

`new validated bins / 1,000 executed instructions`

For:

`W = 20,000`

this becomes:

`r_tail(N) = DeltaB_L2_new(W) / 20`

---

## 12. Tail-Rate Resolution

Because bin discovery is discrete, over a 20,000-instruction window the
smallest non-zero observable discovery rate is:

`1 / 20 = 0.05 new bins / 1,000 instructions`

For this experiment, the long-tail criterion is pre-registered as:

`DeltaB_L2_new(W) <= 1`

over:

`W = 20,000 executed instructions`

This operational definition corresponds to:

`theta_tail = 1 / 20`

or:

`theta_tail = 0.05 new validated bins / 1,000 executed instructions`

The value `0.05` is therefore a pre-registered operational threshold,
not a mathematically unique consequence of the coverage-space size.

The older proposed threshold:

`0.5 bins / 1,000 instructions`

would correspond to as many as 10 new bins per 20,000 instructions and
is therefore not retained for the corrected 62-bin L2 model.

---

## 13. L2 Long-Tail State

A run is classified as being in the L2 long-tail state when:

1. `validated_L2_bins >= 59`;
2. `validated_L2_bins < 62`;
3. `r_tail <= theta_tail`.

Thus the run is near closure but is discovering at most one new
validated bin per 20,000 executed instructions.

Long-tail classification is descriptive.

It is not equivalent to successful closure.

---

## 14. L2 Zero-Progress Plateau

A stronger zero-progress plateau is declared when:

1. `validated_L2_bins < 62`; and
2. no new validated L2 bin is discovered in the trailing
   20,000-instruction window.

Equivalently:

`DeltaB_L2_new(W) = 0`

and therefore:

`r_tail = 0`

The run shall still respect the pre-registered global budget unless a
separate valid stopping condition applies.

---

## 15. Run Stopping Conditions

A coverage-search run terminates under one of the following conditions.

### 15.1 Full closure

Both required validated coverage obligations for that run have been
satisfied.

Where both levels are required:

`L1 = 20 / 20`

and:

`L2 = 62 / 62`

The exact executed-instruction index of closure must be recorded.

### 15.2 Maximum budget

The run reaches:

`N_max = 100,000 executed instructions`

without full closure.

The run terminates at the cap and residual uncovered bins are recorded.

### 15.3 Fatal execution failure

A simulator, testbench, DUT, or infrastructure failure makes continued
execution invalid.

Such a run is classified as failed/invalid according to the
experimental protocol.

It must not be mislabeled as coverage saturation.

---

## 16. Plateau Is Not an Early-Stop Rule

Neither:

* L1 plateau;
* L2 long-tail;
* L2 zero-progress plateau;

shall independently terminate a run before the pre-registered stopping
condition.

This prevents generation methods from receiving unequal instruction
budgets merely because their discovery trajectories differ.

Plateau states are observations used for analysis.

They are not ad-hoc budget reductions.

---

## 17. Primary Efficiency Metric

The primary L2 near-closure efficiency metric is:

`n@95%`

defined as the executed-instruction index at which the run first reaches:

`59 / 62`

validated L2 bins.

If exact first-hit instruction indices are logged, use the exact
instruction index.

Otherwise the checkpoint resolution must be reported explicitly.

---

## 18. Full-Closure Metric

When full closure is reached, report:

`n@100%`

defined as the executed-instruction index at which:

`62 / 62`

validated L2 bins are first reached.

Runs failing to reach full closure by:

`N_max`

must not be assigned a fabricated `n@100%`.

They shall be reported as not reaching full closure within the fixed
budget.

---

## 19. Fixed-Budget Fallback

For runs that do not reach the target threshold or full closure, report:

`bins@100k`

defined as:

`validated L2 bins at N = 100,000 executed instructions`

Also report:

`tail_rate_last20k`

defined as the L2 validated-bin discovery rate over the final
20,000 executed instructions.

These metrics are reported separately.

They shall not be combined through an undefined expression such as:

`bins@10^5 + lambda`

unless lambda is separately defined with compatible units and a
pre-registered statistical interpretation.

For the frozen protocol, no such scalar combination is used.

---

## 20. Comparison Rule for Non-Closure Runs

When methods do not consistently reach the same closure threshold,
analysis shall report at least:

* `bins@100k`;
* `tail_rate_last20k`;
* proportion of seeds reaching 59/62;
* proportion of seeds reaching 62/62.

No run shall receive an artificial time-to-closure value merely because
it reached the instruction cap.

Statistical treatment of censored time-to-threshold results, if used,
must be declared separately before comparative analysis.

---

## 21. Discovery Event Timestamp

When a bin is validated after delayed checker processing, the coverage
discovery timestamp shall refer to the executed instruction/event that
established the corresponding realization.

It shall not use the later software-processing time at which the
checker happened to update the coverage data structure.

This preserves instruction-budget comparability.

---

## 22. Checkpoint Record

At each 1,000-instruction checkpoint, record at least:

```text
seed
method
executed_instructions
L1_intent_bins
L1_validated_bins
L2_intent_bins
L2_validated_bins
new_L1_validated_bins
new_L2_validated_bins
L2_tail_rate
checker_mismatch_count
wall_clock_elapsed
```

Additional telemetry may be retained if it does not materially alter
campaign performance.

---

## 23. Logging Constraint

Coverage checkpoint data shall be written no more frequently than the
configured checkpoint interval unless event-level logging is required
for newly discovered bins or failures.

Per-cycle CSV writes are prohibited for comparative performance runs.

Event records should be buffered where practical.

---

## 24. Per-Seed Reset

Before each independent seed:

* L1 intent state resets;
* L1 validated state resets;
* L2 intent state resets;
* L2 validated state resets;
* adaptive generator state resets;
* RNG resets to the configured seed;
* checkpoint history resets.

No seed may inherit coverage or utility state from another seed.

---

## 25. Edge Cases

### Threshold crossing between checkpoints

Use the exact discovery instruction index if available.

Do not automatically round an exact threshold crossing to the next
1,000-instruction checkpoint.

### Multiple new bins at one instruction

All independently valid newly covered bins are recorded.

The instruction index is identical for those first-hit events.

### DUT mismatch

Intent Coverage may increase.

Validated Coverage does not increase for the failed realization.

### Coverage already complete

Once all required bins are validated, unique coverage cannot increase
further.

The closure instruction index is frozen at the first complete state.

### Run failure before N_max

Do not interpret infrastructure failure as saturation or zero tail
rate.

---

## 26. Complexity

Checkpoint processing operates over fixed-size L1 and L2 state:

`20 + 62 = 82 bins`

Therefore checkpoint bookkeeping is:

`O(82) = O(1)`

for the frozen model.

Event-level direct L2 indexing is:

`O(1)`

The expected runtime bottleneck remains RTL simulation, checker
execution, synchronization, and logging rather than coverage arithmetic.

---

## 27. Frozen Constants

The pre-registered constants are:

```text
B_L1               = 20
B_L2               = 62

checkpoint Delta   = 1,000 executed instructions
window W           = 20,000 executed instructions
N_max              = 100,000 executed instructions

L1 near-closure    = 19 / 20
L1 full closure    = 20 / 20

L2 near-closure    = 59 / 62
L2 full closure    = 62 / 62

theta_tail         = 0.05 new validated bins / 1,000 instructions
```

These constants shall not be changed in response to comparative
campaign results.

---

## 28. Freeze Conditions

This protocol may be marked PASS / FROZEN only when:

* checkpoint unit is explicitly executed instructions;
* L1 full closure is distinguished from the 95% plateau threshold;
* L2 95% is mapped to exactly 59/62;
* L2 full closure is exactly 62/62;
* the 20,000-instruction tail window is explicit;
* tail-rate units are explicit;
* the corrected tail threshold is justified by observable resolution;
* plateau does not silently terminate campaign budget;
* N_max is identical across comparison methods;
* non-closure fallback metrics are dimensionally well-defined;
* exact threshold-crossing behavior is specified;
* failed runs cannot be mislabeled as saturation.

---

## 29. Freeze Status

Current status:

`PASS / FROZEN`

Next artifact:

`research/week5/vplan/ADAPTIVE_CGS_SPEC.md`
