# STATISTICAL PROTOCOL

## 1. Purpose

This document freezes the statistical analysis protocol for the
comparative evaluation of:

* Pure Random;
* Weighted Random;
* Adaptive CGS.

Directed verification is reported separately as deterministic
verification evidence and is not included in the stochastic
between-method inferential analysis.

The statistical protocol is frozen before comparative results are
inspected.

---

## 2. Normative Inputs

This protocol depends on the frozen:

* `L1_COVERAGE_MODEL.md`;
* `L2_COVERAGE_MODEL.md`;
* `SATURATION_PROTOCOL.md`;
* `ADAPTIVE_CGS_SPEC.md`;
* `EXPERIMENTAL_PROTOCOL.md`.

The stochastic sample size is:

`n = 15 independent seeds per method`.

The three stochastic methods therefore contribute:

`45 primary evaluation runs`.

Pilot runs are excluded from comparative inference.

---

## 3. Analysis Unit

The experimental unit is:

`one complete method × seed run`.

Individual instructions, coverage events, bins, epochs, or checkpoints
within one run are not treated as statistically independent samples.

Therefore the effective sample size for a method is:

`n = 15`

not the number of instructions, epochs, or checkpoints.

This prevents pseudoreplication.

---

## 4. Analysis Populations

Three datasets shall remain distinct:

1. Adaptive CGS pilot dataset;
2. final stochastic comparative dataset;
3. Directed verification dataset.

Pilot observations shall not be merged with final Adaptive CGS
evaluation runs.

Directed observations shall not be treated as additional stochastic
seeds.

---

## 5. Metric Classes

The metrics are divided according to whether they are always observed or
may be censored.

### Always-observed metrics

At the fixed instruction budget:

* `bins@100k_intent`;
* `bins@100k_validated`;
* `AUC_intent`;
* `AUC_validated`;
* `tail_rate_intent`;
* `tail_rate_validated`;
* `wall_clock_total`;
* `instructions_per_second`;
* `cycles_per_second`;
* `checker_mismatch_count`.

### Threshold metrics

The following may be right-censored:

- `n@95%_intent`;
- `n@95%_validated`.

A seed that does not reach a threshold within `N_max` is not assigned an
artificial threshold time.

---

## 6. Descriptive Statistics

For each always-observed numeric metric and each stochastic method,
report:

* sample size `n`;
* arithmetic mean;
* sample standard deviation;
* median;
* minimum;
* maximum.

The primary compact summary remains:

`mean ± SD`.

Median and range are retained because several verification metrics may
be bounded, discrete, or skewed.

---

## 7. Bootstrap Confidence Intervals

For each stochastic method and primary always-observed metric, compute a
nonparametric bootstrap:

`95% confidence interval`

using:

`B = 10,000 bootstrap resamples`.

Resampling occurs at the run/seed level.

Each bootstrap replicate samples:

`n = 15`

complete run observations with replacement from the corresponding
method.

Instructions, checkpoints, or coverage events within a run shall not be
resampled as independent observations.

The default bootstrap interval is the percentile interval:

`[2.5th percentile, 97.5th percentile]`.

The RNG seed used for statistical resampling shall be fixed and recorded
in the analysis artifact.

Frozen bootstrap RNG seed:

`20260920`.

---

## 8. Pairwise Comparison Set

The stochastic methods are:

```text
PR = Pure Random
WR = Weighted Random
AC = Adaptive CGS
```

The complete pairwise comparison family is:

```text
PR vs WR
PR vs AC
WR vs AC
```

Thus there are:

`3 pairwise comparisons`

per analyzed metric family.

Directed verification is not included in these pairwise stochastic
tests.

---

## 9. Welch's t-Test

For always-observed numeric outcomes, pairwise mean comparisons use:

`Welch's two-sample t-test`.

Equal population variances are not assumed.

For samples:

`X_1 ... X_nx`

and:

`Y_1 ... Y_ny`

the test statistic is:

`t = (mean(X) - mean(Y)) /
     sqrt(s_X^2/n_X + s_Y^2/n_Y)`.

Degrees of freedom use the Welch-Satterthwaite approximation.

All tests are:

`two-sided`.

The nominal family-level significance threshold is:

`alpha_family = 0.05`.

Welch testing shall not be applied directly to right-censored
time-to-threshold observations.

---

## 10. Welch-Test Metric Scope

Welch's t-test is pre-registered for:

* `bins@100k_intent`;
* `bins@100k_validated`;
* `AUC_intent`;
* `AUC_validated`;
* `wall_clock_total`;
* `instructions_per_second`.

Additional always-observed metrics may be summarized descriptively but
shall not be promoted post hoc to primary hypothesis tests merely
because they produce favorable results.

Coverage-bin counts are bounded discrete outcomes; therefore their
bootstrap intervals, raw distributions, and effect sizes shall be
reported alongside Welch results rather than relying on p-values alone.

---

## 11. Multiple-Comparison Control

For the three pairwise stochastic comparisons within each primary
metric, adjust Welch-test p-values using:

`Holm's step-down procedure`.

The family-wise significance level is:

`0.05`.

For three raw p-values:

`p_(1) <= p_(2) <= p_(3)`

the Holm procedure compares them sequentially against:

```text
0.05 / 3
0.05 / 2
0.05 / 1
```

with the standard step-down stopping rule.

Both:

* raw p-value;
* Holm-adjusted p-value;

shall be reported.

No uncorrected pairwise p-value shall be described as statistically
significant when the corresponding Holm-adjusted result is not.

---

## 12. Effect Size

Each Welch pairwise comparison shall be accompanied by a standardized
effect size.

The frozen standardized effect size is:

`Hedges' g`.

Hedges' g is preferred over uncorrected Cohen's d because each method
contains only:

`n = 15`

runs.

Report:

* signed Hedges' g;
* absolute magnitude;
* bootstrap 95% CI where practical.

The sign shall follow:

`first named method - second named method`.

Effect size interpretation shall not replace the raw metric difference.

For engineering relevance, the report shall also include the
unstandardized mean difference in the metric's original units.

---

## 13. Bootstrap Mean-Difference Interval

For each primary pairwise comparison, compute a run-level bootstrap
95% confidence interval for:

`Delta_mean = mean(method_A) - mean(method_B)`.

Use:

`10,000`

resamples independently within each method.

This interval provides the estimated effect directly in engineering
units, for example:

* L2 bins;
* normalized AUC;
* seconds;
* instructions/second.

The bootstrap difference interval is reported alongside, not instead of,
the pre-registered Welch test.

---

## 14. Direction of Better Performance

Metric direction must be declared before interpretation.

Higher is better for:

```text
bins@100k_intent
bins@100k_validated
AUC_intent
AUC_validated
instructions_per_second
cycles_per_second
```

Lower is better for:

```text
wall_clock_total
n@95%
```

For checker mismatch count, lower numerical count is not automatically
interpreted as a better stimulus generator because mismatch count also
depends on defect exposure.

Mismatch count is therefore primarily diagnostic rather than a direct
generator-quality ranking metric.

---

## 15. Right-Censoring Contract

A threshold observation is right-censored if the corresponding coverage
threshold is not reached before:

`N_max = 100,000 executed instructions`.

For example, if a run reaches only:

`57 / 62`

Validated L2 bins at the end of the budget, then:

`n@95%_validated`

is right-censored at:

`100,000`.

This means:

`true threshold time > 100,000`

not:

`threshold time = 100,000`.

The numerical censoring bound may be stored as 100,000 together with an
explicit event indicator:

```text
time  = 100000
event = 0
```

It must not be analyzed as an ordinary observed threshold time.

---

## 16. Forbidden Threshold Substitutions

The following practices are prohibited:

* replacing a non-reached `n@95%` by `100000` and treating it as an
  observed value;
* calculating an ordinary mean threshold time over censored and
  uncensored values as if all were observed;
* discarding non-reaching seeds and computing a success-only mean while
  presenting it as the unconditional method performance;
* applying Welch's t-test directly to such substituted threshold data.

These procedures bias time-to-coverage conclusions.

---

## 17. Threshold-Reach Proportion

For every method and threshold report:

```text
number reaching threshold / 15
```

and the corresponding proportion.

Required thresholds include:

* `59/62 Intent`;
* `59/62 Validated`;
* `62/62 Intent`;
* `62/62 Validated`.

This is an always-observable outcome even when time-to-threshold is
censored.

---

## 18. Pairwise Reach-Probability Comparison

For pairwise comparison of threshold-reaching proportions, use:

`Fisher's exact test`

on the corresponding:

`2 × 2`

table.

Example structure:

```text
                 reached   not reached
method A            a          15-a
method B            b          15-b
```

The test is two-sided.

For each threshold family, pairwise p-values shall use the same Holm
correction across:

* PR vs WR;
* PR vs AC;
* WR vs AC.

Because `n = 15` per method, Fisher's exact test is preferred to
large-sample proportion approximations.

---

## 19. Time-to-Threshold Analysis

Right-censored `n@95%` outcomes shall be represented using
time-to-event methodology.

The event is:

`coverage threshold reached`.

The time variable is:

`executed instruction count`.

The censoring boundary is:

`100,000 executed instructions`.

Kaplan-Meier-style threshold-survival curves may be reported, where the
survival quantity represents:

`probability that the threshold has not yet been reached by instruction N`.

Because instruction count is discrete and sample size is small,
time-to-threshold inference shall be interpreted conservatively.

---

## 20. Restricted Mean Instruction-to-Threshold

For a threshold with substantial censoring, summarize the time-to-event
distribution using the restricted mean instruction count up to:

`tau = 100,000`.

This is equivalent to the area under the threshold-not-yet-reached curve
over the common instruction horizon.

Unlike a success-only mean, this retains information from both:

* seeds reaching the threshold;
* censored seeds.

Lower restricted mean instruction count indicates earlier threshold
achievement over the common finite budget.

This metric shall be labeled explicitly as restricted rather than as an
ordinary mean `n@95%`.

---

## 21. Successful-Run Threshold Descriptives

For transparency, uncensored successful runs may additionally report:

* median successful `n@95%`;
* minimum successful `n@95%`;
* maximum successful `n@95%`.

These values must be labeled:

`conditional on reaching the threshold`.

They are not substitutes for the reach proportion or censored analysis.

---

## 22. Coverage AUC Role

`AUC_intent`

and:

`AUC_validated`

are always observed over the fixed budget.

Therefore they are particularly important when threshold metrics are
heavily censored.

AUC combines both:

* amount of coverage achieved;
* how early that coverage was achieved.

It does not replace reporting final:

`bins@100k`.

Both metrics are required because two methods can have similar final
coverage but different discovery trajectories.

---

## 23. Primary Evidence Hierarchy

For generator-efficiency hypotheses, the evidence hierarchy is:

1. fixed-budget L2 coverage;
2. normalized coverage AUC;
3. threshold-reach proportion;
4. censored time-to-threshold analysis;
5. wall-clock/runtime overhead.

No conclusion shall rely exclusively on one favorable metric while
ignoring contradictory primary metrics.

Intent results characterize stimulus-generation efficiency.

Validated results characterize verification closure under observed DUT
behavior.

Both shall be reported.

---

## 24. H1 Analysis Mapping

H1 states that Pure Random exhibits a stronger long-tail effect than
coverage-oriented generators.

Evidence includes:

* `tail_rate_intent`;
* `tail_rate_validated`;
* residual uncovered bins at 100,000 instructions;
* threshold-reach proportions.

H1 is evaluated using direct reported metrics and pairwise comparisons.

The interpretation must distinguish:

`low tail discovery because closure is nearly complete`

from:

`low tail discovery because the method has stagnated far from closure`.

Therefore tail rate is never interpreted without the corresponding
final coverage level.

---

## 25. H2 Analysis Mapping

H2 compares Weighted Random with Pure Random.

Primary quantities are:

* `bins@100k_intent`;
* `bins@100k_validated`;
* `AUC_intent`;
* `AUC_validated`;
* threshold-reaching behavior.

Welch tests, Holm-adjusted p-values, Hedges' g, and bootstrap mean
difference intervals shall be reported where applicable.

---

## 26. H3 Analysis Mapping

H3 compares Adaptive CGS with the non-adaptive stochastic methods.

Required pairwise comparisons are:

* Adaptive CGS vs Pure Random;
* Adaptive CGS vs Weighted Random.

Primary coverage evidence is:

* fixed-budget L2 coverage;
* AUC;
* threshold-reaching behavior.

The final report must also expose the Adaptive CGS hyperparameters chosen
by the independent pilot.

---

## 27. H4 Analysis Mapping

H4 concerns the trade-off between instruction efficiency and runtime
overhead.

Report at minimum:

* executed instructions required for coverage outcomes;
* total wall-clock time;
* instructions/second;
* adaptive-policy processing time, if instrumented.

A method may improve instruction efficiency while being slower in wall
time.

These outcomes are not contradictory.

Both dimensions must be reported.

---

## 28. H5 Analysis Mapping

H5 compares evidence visible to:

* architectural functional checking;
* performance/timing monitoring.

The analysis shall report concrete cases where timing/performance
monitoring detects behavior not represented by architectural state
mismatch alone.

H5 is primarily verification-evidence analysis rather than a
three-method mean-comparison hypothesis.

No artificial p-value is required if the outcome is represented by
specific reproducible failure classes.

---

## 29. Statistical Significance and Engineering Significance

Statistical significance and engineering relevance must be reported
separately.

A small Holm-adjusted p-value does not by itself establish practical
importance.

For each important comparison report:

* raw metric difference;
* relative difference where meaningful;
* bootstrap confidence interval;
* standardized effect size;
* adjusted p-value.

Interpretation shall consider verification cost and coverage impact.

---

## 30. Relative Improvement

When denominator values are non-zero, relative improvement may be
reported as:

`100 × (new - baseline) / baseline`.

The direction of improvement must respect the metric semantics.

For a cost metric where lower is better, an instruction reduction may
instead be reported as:

`100 × (baseline - new) / baseline`.

The exact numerator/denominator shall be stated with the result.

Relative improvement shall not replace absolute values.

---

## 31. Zero-Variance Edge Case

Some bounded metrics may have zero sample variance, for example if all
15 runs achieve:

`62/62`.

If both compared samples have zero variance, Welch's t-test is
undefined.

In that case:

* report the identical raw distributions;
* report mean difference;
* report bootstrap result where meaningful;
* mark the Welch test as `not applicable: zero variance`.

No artificial variance shall be injected.

If only one sample has zero variance, the statistical implementation
shall follow the mathematically defined Welch calculation if supported
and shall flag the condition in the analysis output.

---

## 32. All-Censored Edge Case

If no seed in one or more methods reaches a threshold:

* reach proportion remains reportable;
* ordinary successful-run threshold statistics may be absent;
* Welch testing is prohibited;
* censored analysis retains the 100,000-instruction censor boundary.

The result shall be stated directly as:

`0/15 reached within budget`

rather than fabricating a threshold time.

---

## 33. Complete-Closure Edge Case

If all methods achieve full closure in all seeds, fixed-budget bin count
may lose discriminatory power.

The experiment shall still report:

* AUC;
* threshold times;
* wall-clock cost;
* tail behavior before closure.

No metric shall be changed after observing this condition.

---

## 34. Missing Data

Missing data due to technical invalidity is not statistically imputed.

The invalid-run protocol in `EXPERIMENTAL_PROTOCOL.md` applies.

A technically invalid run is repeated with the same:

`method + seed + configuration`.

DUT failures, low coverage, or extreme valid outcomes are not missing
data and shall not be removed.

---

## 35. Outlier Policy

There is no automatic statistical outlier removal.

A valid run remains in the primary dataset regardless of its numerical
distance from other seeds.

A run may be excluded only if it meets the frozen technical
invalid-run definition.

Any diagnostic robust summary may be reported additionally, but it
shall not replace the pre-registered primary dataset.

---

## 36. Precision and Reporting

Raw machine-readable data shall retain full available precision.

Human-readable tables may round:

* percentages to two decimal places;
* normalized AUC to four decimal places;
* p-values to four significant digits where practical;
* wall-clock time according to measurement precision.

A p-value smaller than the display resolution shall be reported as a
bound, for example:

`p < 0.0001`

rather than as zero.

---

## 37. Required Pairwise Result Table

For every primary always-observed metric, produce a table containing:

```text
metric
method_A
method_B
mean_A
SD_A
mean_B
SD_B
mean_difference
bootstrap_CI_low
bootstrap_CI_high
Hedges_g
Welch_t
Welch_df
p_raw
p_Holm
```

The table is generated from immutable run-level data.

---

## 38. Required Method Summary Table

For every stochastic method report:

```text
n
mean ± SD
bootstrap 95% CI
median
min
max
```

for each primary always-observed metric.

For threshold metrics additionally report:

```text
reached_count
reached_fraction
censored_count
conditional_median_if_reached
```

---

## 39. Reproducibility

The statistical analysis implementation shall record:

* Python version;
* package versions;
* bootstrap RNG seed;
* source CSV hashes or immutable identifiers;
* analysis script revision;
* timestamp.

A rerun from identical immutable data and software revision shall
produce identical bootstrap results.

---

## 40. Computational Complexity

For:

`M = 3 methods`

`n = 15 runs/method`

and:

`B = 10,000 bootstrap replicates`,

bootstrap computation is approximately:

`O(M × B × n)`

per metric for single-method intervals.

Pairwise difference bootstrapping has the same order because both sample
sizes are fixed at 15.

At this experiment scale, statistical computation is negligible
relative to RTL simulation.

---

## 41. Frozen Statistical Constants

```text
stochastic methods       = 3
n per method             = 15
pairwise comparisons     = 3

bootstrap replicates     = 10,000
bootstrap CI             = 95%
bootstrap RNG seed       = 20260920

Welch test               = two-sided
family alpha             = 0.05
multiple comparison      = Holm

effect size              = Hedges' g

threshold censor limit   = 100,000 executed instructions
L2 near closure          = 59 / 62
L2 full closure          = 62 / 62
```

---

## 42. Prohibited Post-Hoc Changes

After comparative results have been inspected, the following are
prohibited without explicitly reopening the experimental protocol:

* changing the primary metrics;
* changing the significance threshold;
* replacing Welch's test with another test because of significance
  outcome;
* changing the bootstrap replicate count;
* changing multiple-comparison correction;
* dropping valid seeds;
* changing effect-size definition;
* converting censored threshold values into ordinary observations;
* introducing a new primary hypothesis.

Exploratory analyses may be performed only when clearly labeled:

`post-hoc / exploratory`.

They shall not be presented as pre-registered confirmatory evidence.

---

## 43. Freeze Conditions

This statistical protocol may be marked PASS / FROZEN only when:

* the run is the statistical analysis unit;
* pilot and evaluation data are separated;
* `n = 15` per stochastic method is explicit;
* mean and SD reporting is explicit;
* bootstrap 95% CI with 10,000 resamples is explicit;
* Welch's t-test scope is explicit;
* Holm correction is explicit;
* Hedges' g is explicit;
* right-censoring is explicitly handled;
* artificial `n@95%=100000` substitution is prohibited;
* threshold reach proportions are reported;
* invalid-run and outlier policies are explicit;
* hypotheses H1-H5 map to analysis outputs;
* reproducibility metadata is defined.

---

## 44. Freeze Status

Current status:

`PASS / FROZEN`

Next step:

`Gate T5 full consistency audit`
