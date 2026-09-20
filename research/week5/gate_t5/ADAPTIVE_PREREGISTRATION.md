# Adaptive CGS Pre-registration

## 1. Purpose

This document freezes the Adaptive Coverage-Guided Stimulus (CGS)
configuration before any Adaptive-CGS pilot coverage result is observed.

The objective is to prevent post-hoc tuning based on comparative
campaign outcomes.

This document is additive to the frozen Week-5 vPlan and MUST NOT
redefine:

- L1 H01-H20 semantics;
- L2 = 62 bins;
- Intent / Validated Coverage contract;
- statistical protocol;
- canonical directed tests T01-T20.

---

## 2. Adaptive-CGS Principle

The Adaptive CGS flow is:

`Coverage State -> Reward History -> Adaptive Policy -> Template Family -> Stimulus`

The policy allocates the available stimulus budget among a fixed set of
template-family arms.

No arm may be added, removed, or semantically redefined after the pilot
campaign begins.

---

## 3. Arm Taxonomy

The Adaptive-CGS arm taxonomy is frozen to exactly 10 arms.

| Arm | Frozen template family | L2 distance role |
|---|---|---|
| A0 | `ALU_D1` | d1 |
| A1 | `ALU_D2` | d2 |
| A2 | `LOAD_D1` | d1 |
| A3 | `LOAD_D2` | d2 |
| A4 | `DUAL_D1_D2` | d1 and d2 |
| A5 | `SPECIAL_WB_D1` | d1 |
| A6 | `SPECIAL_WB_D2` | d2 |
| A7 | `LINK_D1` | d1 |
| A8 | `STORE_DATA_D1` | d1 |
| A9 | `PRIORITY_D1` | d1 |

Normative arm semantics remain defined by:

`research/week5/vplan/ADAPTIVE_CGS_SPEC.md`

specifically its frozen arm-taxonomy and template-selection sections.

The preregistration document does not redefine those semantics; it
records and freezes the repository-backed taxonomy used by the
experiment.

No arm may be:

- added;
- removed;
- renamed;
- split;
- merged;
- or semantically redefined

after pilot coverage results are observed.

Special negative/control scenarios H05, H18, H19, and H20 remain handled
according to the frozen Week-5 protocol and MUST NOT be silently inserted
as additional adaptive arms.

---

## 4. Reward Definition

Adaptive reward is based on:

`L2 Intent Coverage`

and NOT on Validated Coverage.

For epoch `t`:

`R_t = 1000 * DeltaNewL2IntentBins / DeltaExecutedInstructions`

Unit:

`new L2 Intent bins / 1000 executed instructions`

where:

- `DeltaNewL2IntentBins` is the number of previously unseen L2 Intent
  bins discovered during the current epoch;
- `DeltaExecutedInstructions` is the number of executed instructions
  consumed during the epoch.

The reward MUST NOT depend on DUT correctness.

Therefore:

- DUT realization failure does not reduce or invalidate Intent reward;
- Validated Coverage remains the primary verification-closure metric;
- L2 Intent reward is used only for generator-policy adaptation.

This separation prevents the stimulus policy from becoming a function
of DUT defects.

---

## 5. Non-Stationary Reward Estimation

Cumulative sample-average estimation is NOT used as the primary arm
utility estimator.

The adaptive policy uses an exponential recency-weighted update:

`Q_(t+1)(a) = Q_t(a) + alpha * (R_t - Q_t(a))`

for the selected arm `a`.

Reason:

coverage reward is non-stationary because an arm's remaining uncovered
space decreases as the campaign progresses.

A recency-weighted update allows the policy to reduce the estimated
utility of saturated arms more rapidly than a lifetime sample average.

---

## 6. Primary Policy

The primary adaptive policy is:

`epsilon-greedy`

No UCB1, Thompson Sampling, Deep RL, or other adaptive policy is part of
the main comparative experiment.

### Exploration

With probability:

`epsilon`

select uniformly at random from all eligible arms.

### Exploitation

With probability:

`1 - epsilon`

select the arm having the largest current utility estimate `Q[a]`.

---

## 7. Tie-Breaking Rule

If multiple arms have equal maximum utility within normal floating-point
comparison tolerance:

select uniformly at random among the tied arms using the RNG associated
with the current experimental seed.

Implementation MUST NOT use deterministic first-index `argmax`
tie-breaking.

This prevents systematic bias toward low-index arms.

---

## 8. Zero-Utility / Saturation Fallback

The frozen threshold is:

`Q_floor = 0.05 new L2 Intent bins / 1000 executed instructions`

If:

`max_a Q[a] <= Q_floor`

the following epoch switches to:

`Uniform Exploration over all eligible arms`

The fallback MUST NOT use Weighted Random because Weighted Random is a
separate comparative method.

---

## 9. Hyperparameter Candidate Space

The candidate epsilon values are frozen as:

`epsilon in {0.05, 0.10, 0.20}`

The candidate recency-weight values are frozen as:

`alpha in {0.1, 0.3, 0.5}`

The candidate batch sizes are frozen as:

`b in {500, 1000, 2000} executed instructions`

No new epsilon, alpha, or batch-size value may be introduced after
Adaptive-CGS pilot coverage results are observed.

---

## 10. Template / Filler Ratio

The stimulus composition ratio is frozen as:

`80% targeted-template instructions / 20% filler instructions`

This ratio is NOT tuned during the pilot.

Filler generation must remain semantically valid for the declared ISA
scope and must not intentionally introduce a hidden adaptive policy.

---

## 11. Adaptive State

Each arm stores at least:

- `Q[a]`
- `pull_count[a]`
- most recent reward
- last selected epoch

For every independent experimental seed:

- coverage state is reset;
- `Q[a]` values are reset;
- pull counts are reset;
- recent-reward state is reset;
- last-selected state is reset;
- RNG state is reset from the seed.

No adaptive state may be warm-started from a previous seed.

---

## 12. Pilot Seeds

Pilot-only seeds are frozen as:

`13001`

`13002`

`13003`

These seeds are used only for hyperparameter selection.

Pilot observations MUST NOT be included in the final M3 comparative
dataset or inferential statistical tests.

---

## 13. Pilot Budget

Per configuration, per seed:

`10,000 executed instructions`

The full Cartesian candidate space contains:

`3 epsilon x 3 alpha x 3 batch-size = 27 configurations`

Therefore the maximum full-grid pilot budget is:

`27 x 3 x 10,000 = 810,000 executed instructions`

---

## 14. Throughput-Based Search-Schedule Decision

The search-schedule decision MUST be made from engineering-throughput
measurements before any Adaptive-CGS pilot coverage result is observed.

Measured Week-5 Cocotb throughput baseline:

Minimal Cocotb loop median:

`17,862.941 cycles/s`

Simple-monitor median:

`13,923.913 cycles/s`

Measured monitor slowdown:

`22.05%`

Pre-registered engineering threshold:

`8 hours maximum projected pilot wall time`

The measured monitor throughput indicates that the full Cartesian pilot
is comfortably below this threshold for realistic campaign CPI and
Python-side overhead.

Therefore the frozen pilot schedule is:

`FULL_GRID`

The fallback L9 subset is NOT used.

---

## 15. Frozen Pilot Search Schedule

All 27 configurations are evaluated.

Cartesian product:

`epsilon in {0.05, 0.10, 0.20}`

`alpha in {0.1, 0.3, 0.5}`

`batch size in {500, 1000, 2000}`

Each configuration is evaluated with exactly:

`3 pilot seeds`

Each configuration/seed pair receives exactly:

`10,000 executed instructions`

Maximum pilot budget:

`810,000 executed instructions`

No configuration may be added or removed after pilot coverage results
are observed.

---

## 16. Hyperparameter Selection Criterion

The pilot selects the final Adaptive-CGS configuration using generator
efficiency rather than DUT correctness.

### Primary metric

Normalized area under the L2 Intent Coverage curve:

`AUC_L2_Intent`

over:

`0 ... 10,000 executed instructions`

Coverage is sampled at the frozen checkpoint interval:

`1,000 executed instructions`

The aggregate value for one configuration is:

`median AUC across the three pilot seeds`

### Secondary metric

`median L2 Intent bins@10^4`

across the three pilot seeds.

### Tertiary metric

`median wall-clock time`

across the three pilot seeds.

### Practical-tie rule

Two configurations are treated as practically tied if:

`normalized AUC difference < 1%`

and:

`bins@10^4 difference <= 1 bin`

### Deterministic tie-resolution order

If configurations remain practically tied:

1. lower median wall-clock time;
2. larger batch size;
3. smaller epsilon;
4. smaller alpha.

The selection rule MUST NOT be changed after viewing pilot coverage
results.

---

## 17. Relationship to Validated Coverage

Adaptive policy optimization uses:

`L2 Intent Coverage`

Final verification reporting uses:

`Validated Coverage`

These two quantities MUST remain separate.

A DUT defect must not reduce the generator's reward merely because the
DUT failed to realize an otherwise correctly generated dependency.

Conversely, an Intent hit MUST NOT be reported as a Validated hit unless
the frozen realization-validation contract is satisfied.

---

## 18. Relationship to Comparative Methods

The four frozen methods remain:

`M0 = Directed`

`M1 = Pure Random`

`M2 = Weighted Random`

`M3 = Adaptive CGS`

Weighted Random is an independent comparison method and is not used as
an Adaptive-CGS fallback.

Pilot data is used only for selecting the final M3 configuration.

Final M1/M2/M3 runs use the frozen final protocol:

`n = 15 independent seeds / method`

with:

`Nmax = 100,000 executed instructions / run`

---

## 19. Reproducibility Rules

After this preregistration is frozen:

- candidate epsilon values MUST NOT change;
- candidate alpha values MUST NOT change;
- candidate batch sizes MUST NOT change;
- `Q_floor` MUST NOT change;
- template/filler ratio MUST NOT change;
- pilot seeds MUST NOT change;
- pilot budget MUST NOT change;
- reward definition MUST NOT change;
- tie-breaking MUST NOT change;
- saturation fallback MUST NOT change;
- hyperparameter selection criterion MUST NOT change;
- search schedule MUST NOT change based on pilot coverage results.

Any later change required because of an implementation defect must be
documented explicitly, applied consistently, and must invalidate any
pilot observations collected under the defective configuration.

---

## 20. Gate Status

The following items are frozen:

- [x] Reward definition
- [x] Exponential recency-weighted update
- [x] epsilon candidate space
- [x] alpha candidate space
- [x] batch-size candidate space
- [x] Q_floor
- [x] exploration rule
- [x] exploitation rule
- [x] tie-breaking rule
- [x] zero-utility fallback
- [x] template/filler ratio
- [x] adaptive-state reset rule
- [x] pilot seeds
- [x] pilot budget
- [x] throughput-based search-schedule rule
- [x] FULL_GRID pilot schedule
- [x] hyperparameter selection criterion
- [x] exact A0-A9 arm taxonomy

Adaptive-CGS preregistration is CLOSED.

The exact A0-A9 taxonomy has been cross-checked against the frozen
Week-5 repository specification before any Adaptive-CGS pilot coverage
result was observed.
