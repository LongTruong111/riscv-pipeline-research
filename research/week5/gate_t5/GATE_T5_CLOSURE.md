# Gate T5 Final Closure

Baseline executable-verification checkpoint:

- Branch: `research/week5-vplan`
- Baseline commit: `1185e89`
- Pure-Python regression: 142 PASS
- Canonical L1 Intent: 20/20
- Canonical L1 Validated: 15/20

This document is additive. It does not redefine the frozen Week-5 vPlan.

---

## Superseded checklist values

The older checklist contains two obsolete definitions that MUST NOT be
restored.

### L2

Obsolete:

`DependencyDistance × rd_producer × rs_dependent = 1,922 bins`

Frozen definition:

`DependencyDistance × ArchitecturalDependentRegister`

where:

- `DependencyDistance ∈ {d1, d2}`
- register `∈ {x1, ..., x31}`

Therefore:

`L2 = 2 × 31 = 62 bins`

For a true RAW dependency:

`rd_producer == rs_dependent`

so `rd_producer` and `rs_dependent` are not independent coverage
dimensions.

`rs1` and `rs2` are attribution roles, not additional L2 dimensions.

### Saturation

Obsolete tail threshold:

`0.5 new bins / 1000 instructions`

Frozen protocol:

- checkpoint: 1,000 executed instructions
- L2 near closure: 59/62
- L2 full closure: 62/62
- tail window: 20,000 executed instructions
- `theta_tail = 0.05 new validated bins / 1000 instructions`
- `Nmax = 100,000`
- `n@95 = first point reaching 59/62`
- non-reaching runs are right-censored

---

## Coverage Model — CLOSED

- [x] Hazard Space Definition frozen.
- [x] L1 = H01-H20 = exactly 20 bins.
- [x] L2 = exactly 62 bins.
- [x] Operand attribution semantics frozen.
- [x] Simultaneous dependency semantics frozen.
- [x] x0 eligibility rule frozen.
- [x] `rd != 0` forwarding gate inspected.
- [x] d3 / RF-visibility boundary inspected.
- [x] Excluded scenarios documented within declared scope.
- [x] No claim of complete RV32I verification.
- [x] Claim limited to completeness within declared verification scope.

### Operand attribution

For one producer-consumer RAW relation:

`rd_producer == rs_dependent`

The dependent role may be RS1 or RS2.

If both RS1 and RS2 refer to the same producer/register, only one L2
`(distance, register)` bin is credited.

If a consumer depends on two different producers, each dependency is
attributed independently according to its producer distance/register.

### x0

x0 is ineligible for positive L2 RAW coverage because architectural x0
does not carry producer state.

x0-related negative/control scenarios remain explicitly represented by
L1 H18/H19.

### d3

L2 is restricted to d1/d2.

d3 is retained in L1 as the RF visibility boundary and is not silently
added as a third L2 distance.

---

## Completeness Mapping — CLOSED

- [x] Each H01-H20 row has one canonical directed target T01-T20.
- [x] L2 reachability is defined over 62 in-scope bins.
- [x] Stimulus dependency is distinct from realized microarchitectural
      hazard.
- [x] Realized hazard is distinct from forwarding/stall correctness.
- [x] Intent Coverage is distinct from Validated Coverage.

Canonical executable evidence:

- Intent: 20/20
- Validated: 15/20
- rejected canonical bins: H11, H13, H18, H19, H20

---

## Pre-registered hypotheses

These hypotheses are frozen before comparative campaign data is
observed.

### H1

Pure Random exhibits a stronger coverage long tail than directed or
coverage-oriented generators.

Operational evidence:

- later `n@95`;
- lower late-window new-bin rate;
- lower coverage AUC at equal instruction budget.

### H2

Weighted Random reduces instruction cost for coverage acquisition
relative to Pure Random.

Primary comparison:

- `n@95`

Secondary:

- `bins@10^5`

### H3

Adaptive CGS improves stimulus efficiency relative to static random
methods.

Evidence:

- lower `n@95`, and/or
- higher `bins@10^5`.

### H4

Adaptive CGS instruction-efficiency gains may be partly offset by
adaptive-control wall-clock overhead.

Compare both:

- instructions required for coverage;
- total wall-clock time.

Instruction efficiency and wall-clock efficiency MUST be reported
separately.

### H5

Performance/timing monitoring detects excess-stall defects that a purely
architectural functional scoreboard may not detect.

Known baseline examples H19/H20 already establish the defect class;
they are not comparative-campaign results.

---

## Mutation independence rule

- [x] Mutation results are excluded from M0-M3 comparative datasets.
- [x] Mutants are not used to tune generator probabilities,
      hyperparameters, coverage definitions, or stopping rules.
- [x] Mutation operators and expected detection criteria are frozen before
      mutation experiments.
- [x] Mutation runs use independent seeds/logs.
- [x] Mutation observations do not contribute Adaptive-CGS reward.
- [x] Pilot or final statistical analysis does not mix mutant data with
      baseline-DUT data.
- [x] If mutation testing exposes an infrastructure defect, affected
      comparative runs are invalidated and rerun consistently for all
      affected methods; results are not selectively patched.

---

## Performance Engineering Contract

### Filesystem

- [x] Main repository is located on Linux-native filesystem.
- [x] Python environment/build artifacts/temp/logs/campaign outputs shall
      remain Linux-native.
- [x] Main comparative campaign shall not run from `/mnt/c/...`.
- [x] Filesystem class shall remain unchanged across M1/M2/M3 runs.
- [x] Environment manifest is captured before performance measurements.

### Logging / I/O

- [x] No per-cycle CSV logging in performance campaigns.
- [x] Event logging is allowed only when required by verification.
- [x] Coverage checkpoints occur every 1,000 executed instructions.
- [x] Telemetry shall be buffered/batched before disk flush where possible.
- [x] Verbose debug logging is disabled for performance runs.
- [x] Waveform dumping is disabled for normal performance runs.
- [x] Diagnostic waveform runs are separate and excluded from wall-clock
      comparison datasets.
- [x] Identical logging policy is used across comparative methods.
