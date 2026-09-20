# ADAPTIVE CGS SPECIFICATION

## 1. Purpose

This document freezes the Adaptive Coverage-Guided Stimulus (Adaptive
CGS) policy and its hyperparameter pilot protocol before comparative
campaign execution.

Adaptive CGS operates on the frozen L2 dependency coverage space:

`62 bins`

defined by:

`DependencyDistance × DependentRegister`

with:

`DependencyDistance in {d1, d2}`

and:

`DependentRegister in {x1, ..., x31}`.

The adaptive policy selects among pre-registered template families.

No arm, reward definition, hyperparameter value, or selection criterion
may be added after pilot coverage results have been observed.

---

## 2. Normative Inputs

This specification depends on the frozen:

* `HAZARD_SPACE.md`
* `HAZARD_TRUTH_TABLE.md`
* `L1_COVERAGE_MODEL.md`
* `L2_COVERAGE_MODEL.md`
* `COMPLETENESS_MAPPING.md`
* `SATURATION_PROTOCOL.md`
* `PERFORMANCE_BASELINE.md`

The full-DUT performance preflight established that the complete
hyperparameter Cartesian grid is computationally feasible.

---

## 3. Adaptive Objective

Adaptive CGS optimizes stimulus-generation efficiency for L2 Intent
Coverage.

Its primary objective is:

> discover previously unseen reachable L2 dependency bins using fewer
> executed instructions.

The adaptive policy itself shall not use DUT correctness as reward.

This separates:

* stimulus-generation quality;
* coverage reachability;
* DUT realization correctness.

Validated Coverage remains an experimental outcome and closure metric,
but it shall not influence arm utility estimation.

---

## 4. Reward Coverage Domain

The reward numerator uses:

`new L2 Intent bins`

not:

`new L2 Validated bins`.

This choice prevents DUT failures from feeding back into the stimulus
policy.

For example, if a valid LUI d1 dependency reaches a previously unseen
L2 register-distance bin but the DUT forwards an incorrect value:

* L2 Intent Coverage records the bin;
* the adaptive arm receives the corresponding discovery reward;
* L2 Validated Coverage does not record a validated hit;
* the checker reports the mismatch.

Thus defect-revealing regions are not suppressed by the adaptive
policy.

---

## 5. Bandit Scope

Adaptive CGS is responsible for L2 d1/d2 dependency exploration.

It is not responsible for complete L1 closure.

The canonical L1 directed tests remain separate verification
obligations.

The following frozen L1 scenarios are therefore outside the adaptive
bandit arm set:

* H05: d3 Register-File visibility;
* H18: x0 forwarding exclusion;
* H19: LOAD-to-x0 negative stall case;
* H20: unused-rs2 negative stall case.

These scenarios do not provide positive d1/d2 L2 dependency reward.

They shall not be inserted as zero-reward adaptive arms.

---

## 6. Frozen Arm Taxonomy

The adaptive policy contains exactly:

`10 arms`

### A0 — ALU_D1

Covers the template family corresponding to:

* H01;
* H02.

Properties:

* ALU-result producer;
* dependency distance d1;
* RS1 and RS2 consumer variants.

Within-arm variant selection:

`RS1 variant : RS2 variant = 1 : 1`

subject to deterministic seeded RNG.

---

### A1 — ALU_D2

Corresponds to:

* H03;
* H04.

Properties:

* ALU-result producer;
* dependency distance d2;
* one structurally independent instruction between producer and
  consumer;
* RS1 and RS2 consumer variants.

Within-arm variant selection is uniform between the two operand-role
variants.

---

### A2 — LOAD_D1

Corresponds to:

* H06;
* H07.

Properties:

* load producer;
* architectural d1 dependency;
* expected load-use interlock;
* RS1 and RS2 variants.

The dependency is classified according to executed program order.

The stall does not change the architectural dependency distance.

---

### A3 — LOAD_D2

Corresponds to:

* H08;
* H09.

Properties:

* load producer;
* architectural d2 dependency;
* independent structural filler;
* RS1 and RS2 variants.

Within-arm variant selection is uniform.

---

### A4 — DUAL_D1_D2

Corresponds to:

* H10.

The template creates two independent dependencies for one consumer:

* one d1 dependency;
* one d2 dependency.

The producer registers must be distinct.

Both newly discovered L2 bins may contribute to the same epoch reward.

---

### A5 — SPECIAL_WB_D1

Corresponds to:

* H11;
* H13.

Producer variants:

* LUI;
* AUIPC.

Dependency distance:

`d1`

Within-arm producer selection:

`LUI : AUIPC = 1 : 1`

using the seeded template RNG.

This arm remains reward-eligible even if the DUT realization fails,
because reward uses Intent Coverage.

---

### A6 — SPECIAL_WB_D2

Corresponds to:

* H12;
* H14.

Producer variants:

* LUI;
* AUIPC.

Dependency distance:

`d2`

Producer selection is uniform.

---

### A7 — LINK_D1

Corresponds to:

* H15.

Producer variants:

* JAL;
* JALR.

The dependency is defined in executed program order.

The flushed sequential fall-through instruction is not treated as a
consumer.

JAL and JALR variants are selected uniformly when both can be legally
constructed.

---

### A8 — STORE_DATA_D1

Corresponds to:

* H16.

The producer creates a d1 dependency on the STORE data source.

The dependent register is the architectural store-data `rs2`.

The forwarded store-data value is distinct from the ALU immediate
operand used for address generation.

---

### A9 — PRIORITY_D1

Corresponds to:

* H17.

Two producers write the same destination register before a consumer.

The newer writer is the active producer.

The older writer is shadowed according to the frozen latest-writer
rule.

Therefore the positive L2 attribution is:

`(d1, register)`

for the newest producer.

The shadowed older d2 writer does not create an additional L2 hit.

---

## 7. Arm Set Freeze

The final arm set is:

```text
A0  ALU_D1
A1  ALU_D2
A2  LOAD_D1
A3  LOAD_D2
A4  DUAL_D1_D2
A5  SPECIAL_WB_D1
A6  SPECIAL_WB_D2
A7  LINK_D1
A8  STORE_DATA_D1
A9  PRIORITY_D1
```

No arm may be added, removed, split, or merged after pilot coverage
results have been observed.

---

## 8. Register Target Selection

Register targeting is performed after an arm has been selected.

The selected arm determines the dependency-distance/template family.

Register targeting determines which architectural register identity is
used for the producer-consumer dependency.

The register-target policy operates exclusively on:

`L2 Intent Coverage`

and shall not inspect Validated Coverage or checker pass/fail state.

This prevents known or newly discovered DUT defects from influencing
stimulus selection.

---

### 8.1 Eligible Register Domain

The eligible L2 register domain is:

`R = {x1, x2, ..., x31}`

`x0` is never a positive L2 target because it cannot represent an
architectural producer dependency.

Therefore:

`|R| = 31`

No register may receive a permanently higher selection probability
merely because of its numerical index.

---

### 8.2 Arm-to-Distance Mapping

Each arm determines the L2 dependency distance that it can target.

| Arm                | L2 distance contribution |
| ------------------ | ------------------------ |
| A0 `ALU_D1`        | d1                       |
| A1 `ALU_D2`        | d2                       |
| A2 `LOAD_D1`       | d1                       |
| A3 `LOAD_D2`       | d2                       |
| A4 `DUAL_D1_D2`    | d1 and d2                |
| A5 `SPECIAL_WB_D1` | d1                       |
| A6 `SPECIAL_WB_D2` | d2                       |
| A7 `LINK_D1`       | d1                       |
| A8 `STORE_DATA_D1` | d1                       |
| A9 `PRIORITY_D1`   | d1                       |

The selected register and distance identify the intended L2 target:

`(distance, register)`

---

### 8.3 Uncovered-First Targeting

For a single-distance arm with distance `d`, define:

`U_d`

as the set of currently uncovered L2 Intent bins at distance `d`.

Formally:

`U_d = { R in x1..x31 | IntentSeen(d, R) == 0 }`

If:

`U_d != empty`

the target register shall be selected uniformly from `U_d`.

Thus:

`P(R | R in U_d) = 1 / |U_d|`

This avoids deterministic low-index bias while explicitly directing
stimulus toward uncovered L2 bins.

---

### 8.4 Saturated-Distance Fallback

If every L2 Intent bin at the arm's required distance has already been
covered:

`U_d = empty`

the register target is selected uniformly over all eligible registers:

`R = {x1, ..., x31}`

Therefore:

`P(R) = 1 / 31`

This fallback preserves legal stimulus generation after a distance
subspace has saturated.

The arm utility is still determined by observed reward and may decay
through the recency-weighted update.

Register targeting itself shall not disable the arm.

---

### 8.5 No Validated-Coverage Targeting

The target set must not be defined using:

`ValidatedSeen(d, R)`

because an uncovered validated bin may already have been intentionally
generated but failed DUT realization.

For example:

```text
IntentSeen(d1, x5)    = 1
ValidatedSeen(d1, x5) = 0
```

means the generator has already reached the requested dependency
scenario.

Repeatedly targeting `(d1, x5)` solely because DUT correctness prevents
Validated Coverage would bias the generator toward a DUT defect rather
than toward unexplored stimulus space.

Therefore adaptive register targeting uses only:

`IntentSeen`

while validated state remains available for verification reporting.

---

### 8.6 Single-Dependency Arms

For:

* A0;
* A1;
* A2;
* A3;
* A5;
* A6;
* A7;
* A8;
* A9;

one positive L2 dependency register is targeted per generated template
instance.

For an arm requiring distance `d`:

1. construct `U_d`;
2. if `U_d` is non-empty, select uniformly from `U_d`;
3. otherwise select uniformly from `{x1, ..., x31}`;
4. construct the producer with destination equal to the selected
   register;
5. construct the architectural consumer source using the same register.

Therefore the required invariant is:

`rd_producer == rs_dependent == target_register`

for the positive RAW dependency.

---

### 8.7 Dual-Dependency Arm A4

A4 may produce two L2 dependency events in one template:

* `(d1, R1)`;
* `(d2, R2)`.

The registers must satisfy:

`R1 != R2`

to preserve two independent producer-consumer dependencies.

Define:

`U_d1 = uncovered Intent registers at d1`

and:

`U_d2 = uncovered Intent registers at d2`.

A4 target selection uses the following priority.

#### Priority 1 — Two Uncovered Bins

If a pair exists such that:

`R1 in U_d1`

`R2 in U_d2`

and:

`R1 != R2`

select uniformly among legal pairs satisfying those conditions.

This permits one generated template to discover up to two new L2 bins.

#### Priority 2 — One Uncovered Bin

If no legal pair can target two uncovered bins simultaneously, prefer a
legal pair that targets one currently uncovered bin.

The second register is selected uniformly from eligible registers that
preserve:

`R1 != R2`.

#### Priority 3 — Both Distance Spaces Saturated

If both d1 and d2 spaces are fully covered, select two distinct
registers uniformly without replacement from:

`{x1, ..., x31}`.

---

### 8.8 A4 Reward Multiplicity

If A4 generates two previously unseen L2 Intent bins in the same
feedback epoch, both discoveries contribute to:

`DeltaB_L2,new`

Therefore a single template instance may contribute:

`0`

`1`

or:

`2`

new L2 Intent bins.

No artificial cap of one reward-producing bin per instruction template
is applied.

---

### 8.9 Priority Arm A9

A9 uses one architectural register identity:

`R`

for:

```text
older producer -> R
newer producer -> R
consumer       -> R
```

The newer producer is the active dependency according to the frozen
latest-writer rule.

Therefore only:

`(d1, R)`

is the positive L2 target.

The shadowed older producer shall not cause:

`(d2, R)`

to be counted as an additional L2 Intent Hit.

Register `R` is selected using the normal uncovered-first d1 rule.

---

### 8.10 Operand-Role Selection

Register-target selection is independent of physical operand position.

Where an arm supports both RS1 and RS2 variants, the selected target
register may be assigned to the appropriate architectural source
according to the arm's frozen within-family variant rule.

For example:

A0 may generate either:

```text
producer rd = x7
consumer rs1 = x7
```

or:

```text
producer rd = x7
consumer rs2 = x7
```

Both map to the same L2 bin:

`(d1, x7)`

Operand position does not create an additional L2 target.

---

### 8.11 Filler Register Constraints

Templates requiring independent filler instructions must ensure that
the filler does not accidentally change the intended dependency.

For a target register `R`, a filler must not:

* write `R`;
* create a nearer architectural writer to `R`;
* redirect execution away from the intended consumer;
* introduce an unintended dependency that invalidates the template
  semantics.

The generator may use a semantically inert legal instruction where
supported by the frozen ISA subset.

Filler register selection is not itself rewarded.

---

### 8.12 Auxiliary Register Selection

Templates may require registers that are not the target dependency
register, for example:

* load base address register;
* store base address register;
* second independent producer;
* JALR base register;
* temporary destination;
* filler destination.

Auxiliary registers shall be selected from legal architectural
registers subject to the template's semantic constraints.

They must not:

1. overwrite the active target register before its consumer;
2. accidentally become a nearer writer of a target source;
3. violate required distinct-register constraints;
4. use `x0` where a writable architectural register is required.

Auxiliary-register choices do not independently define L2 bins.

---

### 8.13 Uniform Tie Breaking

Whenever multiple register targets or legal register pairs have equal
priority, selection shall be:

`Uniform Random`

using the RNG associated with the current experimental seed.

The implementation shall not resolve ties using:

* lowest register number;
* first list element;
* dictionary iteration order;
* fixed array order.

This avoids deterministic register-index bias.

---

### 8.14 Seed Determinism

For a fixed:

* generator implementation;
* hyperparameter configuration;
* experiment seed;
* initial coverage state;

register-target choices must be reproducible.

All random register and variant selections shall use the experiment RNG
derived from the current seed.

No unseeded secondary RNG source may be used.

---

### 8.15 Coverage-State Timing

Register targeting for epoch `t` must use the frozen coverage state
available before stimulus generation for that epoch.

Formally:

`TargetSelection_t = f(IntentCoverage_{t-1}, RNG_t, Arm_t)`

Coverage discovered by the stimulus generated in epoch `t` updates the
state only after that epoch has completed.

The generator shall not use future information from within an
unfinished epoch to retroactively alter earlier selections.

---

### 8.16 Computational Complexity

For a single-distance arm, constructing the uncovered candidate set by
scanning all eligible registers costs:

`O(31)`

which is constant for the frozen architecture.

A4 pair selection may examine at most:

`31 × 31 = 961`

candidate pairs.

Thus for the frozen vPlan:

`T_target = O(1)`

with a small bounded state space.

An implementation may maintain explicit uncovered-register sets to
reduce repeated scanning, but this optimization must not alter
selection probabilities.

---

### 8.17 Register-Target Invariants

The implementation must preserve:

```text
eligible target registers = x1..x31

positive RAW:
rd_producer == rs_dependent

targeting state:
L2 Intent Coverage only

single-distance arm:
prefer uniformly among uncovered bins

saturated distance:
uniform over all eligible registers

A4:
R_d1 != R_d2

A9:
only newest producer contributes positive L2 attribution

operand position:
not an L2 dimension

tie breaking:
seeded Uniform Random
```

Any violation of these invariants changes the experimental policy and
requires reopening the Adaptive CGS specification before campaign
execution.

## 9. Feedback Epoch and Batch Semantics

Adaptive decisions occur at feedback-epoch boundaries.

A candidate batch-size value:

`b in {500, 1000, 2000}`

defines the nominal number of executed instructions between adaptive
policy updates.

Each epoch selects exactly one arm.

The selected arm then generates complete instances of its template
family until the executed-instruction count for the epoch first reaches
or exceeds the nominal batch threshold.

A template shall not be split merely to obtain an exact batch length.

Therefore the actual epoch instruction count:

`DeltaN_instr`

may differ slightly from `b`.

Reward normalization shall always use the actual:

`DeltaN_instr`

rather than the nominal batch-size parameter.

The final epoch of a run may be shorter when constrained by:

`N_max = 100,000 executed instructions`

or by successful full closure.

---

## 10. Template / Filler Contract

The frozen discretionary template-to-filler ratio is:

`100 : 0`

That is:

* no background random filler stream is inserted merely to consume
  stimulus budget;
* all generated instructions belong either to the selected template or
  to structural instructions required to realize that template.

Mandatory structural filler, such as the independent instruction
required to construct a d2 dependency, is considered part of the
template cost.

Its executed instructions are therefore included in:

`DeltaN_instr`.

This rule prevents an additional filler-ratio hyperparameter from
confounding the Adaptive CGS comparison.

---

## 11. Reward Definition

For epoch `t`, define:

`DeltaB_L2,new,attrib(t)`

as the number of unique L2 Intent bins that:

1. were uncovered at the start of epoch `t`; and
2. were exercised during epoch `t` by dependency events attributable
   to the arm selected for that epoch.

The reward is:

`R_t = 1000 × DeltaB_L2,new,attrib(t) / DeltaN_instr(t)`

with units:

`new attributable L2 Intent bins / 1,000 executed instructions`.

This normalization permits direct utility comparison across the
candidate batch sizes:

* 500;
* 1000;
* 2000 instructions.

---

## 12. Reward Attribution Contract

An arm receives reward only for a newly discovered L2 Intent bin when
the dependency event is semantically attributable to that arm's frozen
template family.

Incidental dependencies created by:

* auxiliary registers;
* structural fillers;
* unrelated architectural interactions;

may still update global Intent Coverage if they satisfy the frozen L2
collector rules.

However, they do not contribute to the selected arm's reward unless
they satisfy that arm's attribution contract.

Therefore:

`global coverage discovery`

and:

`arm reward attribution`

are related but not identical concepts.

This prevents an arm from receiving credit for unrelated accidental
coverage.

---

## 13. Epoch-Start Coverage Snapshot

Reward novelty is evaluated relative to the L2 Intent Coverage state at
the beginning of the epoch.

Let:

`S_t`

be the set of L2 Intent bins already covered before epoch `t`.

A bin contributes to reward only if:

`bin not in S_t`

and an attributable event for that bin occurs during epoch `t`.

Repeated occurrences of the same previously uncovered bin within the
same epoch contribute only once.

Thus:

`DeltaB_L2,new,attrib`

counts unique bins, not event frequency.

---

## 14. Reward Range

Reward is non-negative:

`R_t >= 0`

because coverage discovery cannot remove previously observed bins.

An epoch with no new attributable bin has:

`R_t = 0`.

For example:

* one new bin in 500 instructions gives `R_t = 2.0`;
* one new bin in 1000 instructions gives `R_t = 1.0`;
* one new bin in 2000 instructions gives `R_t = 0.5`.

A4 may discover two bins from one dual-dependency template, and both may
contribute if they satisfy the novelty and attribution rules.

---

## 15. Non-Stationary Utility Estimator

A cumulative sample-average estimator is not used.

Coverage reward is inherently non-stationary because the number of
remaining reachable bins decreases as the campaign progresses.

For the selected arm `a_t`, utility is updated using:

`Q_(t+1)(a_t) = Q_t(a_t) + alpha × [R_t - Q_t(a_t)]`

For every unselected arm:

`Q_(t+1)(a) = Q_t(a)`.

Candidate learning rates are:

`alpha in {0.1, 0.3, 0.5}`.

A larger alpha responds more strongly to recent reward.

A smaller alpha retains a longer effective reward history.

Because updates occur once per epoch, alpha and batch size jointly
determine the effective forgetting horizon in executed instructions.

This interaction is intentional and is evaluated by the pre-registered
Cartesian pilot.

---

## 16. Initial Adaptive State

At the beginning of every seed:

```text
Q[a]               = 0.0
pull_count[a]      = 0
recent_reward[a]   = 0.0
last_selected[a]   = NONE
epoch_index        = 0
```

for all 10 arms.

Coverage state also resets according to the frozen per-seed reset
contract.

No adaptive state may be inherited from another seed.

---

## 17. Initial Arm Sweep

Before ordinary epsilon-greedy operation, each of the 10 arms is pulled
exactly once.

The order of these initial pulls is a seeded uniform random permutation
of:

`A0 ... A9`.

This guarantees that every arm receives at least one observed reward
before exploitation begins.

The initial sweep is part of the Adaptive CGS algorithm and its
instruction cost is included in all reported efficiency metrics.

It is not treated as free warm-up stimulus.

For a batch-size configuration `b`, the initialization phase therefore
contains approximately:

`10 × b`

executed instructions, subject to template-boundary effects.

The randomized order prevents a fixed low-index arm from always seeing
the richest initial uncovered coverage state.

---

## 18. Epsilon-Greedy Policy

After the initial arm sweep, the policy uses epsilon-greedy selection.

Candidate values are:

`epsilon in {0.05, 0.10, 0.20}`.

For each ordinary adaptive epoch:

1. evaluate the zero-utility fallback condition;
2. if fallback is not active, draw a seeded random value `u` uniformly
   from `[0,1)`;
3. if `u < epsilon`, perform exploration;
4. otherwise perform exploitation.

### Exploration

Exploration selects:

`Uniform Random`

over all 10 frozen arms.

No arm is removed merely because its current utility is low.

### Exploitation

Exploitation selects an arm whose `Q[a]` equals the maximum current
estimated utility.

---

## 19. Exploitation Tie Breaking

Define:

`Q_max = max_a Q[a]`.

Any arm satisfying:

`abs(Q[a] - Q_max) <= 1e-12`

is considered tied for maximum utility.

If multiple arms are tied, select uniformly among the tied arms using
the experiment RNG.

The implementation shall not use a default first-index `argmax`.

Therefore arm index ordering cannot create deterministic exploitation
bias.

---

## 20. Q_floor and Zero-Utility Fallback

The fixed utility floor is:

`Q_floor = 0.05`

with units:

`new L2 Intent bins / 1,000 executed instructions`.

Q_floor uses the same numerical unit as the tail-rate metric:

new bins / 1,000 executed instructions.

However, the two quantities have different semantic domains:

- Q_floor applies to the recency-weighted L2 Intent reward;
- theta_tail in SATURATION_PROTOCOL.md applies to validated coverage
  discovery.

The shared numerical value 0.05 is a pre-registered experimental design
choice and does not imply that the two metrics are equivalent.

After the initial sweep, if:

`max_a Q[a] <= Q_floor`

the next epoch uses:

`Uniform Random over all 10 arms`

regardless of the ordinary epsilon-greedy exploitation decision.

This state is called:

`zero-utility / saturation fallback`.

The fallback prevents arbitrary exploitation when all arm utilities
have decayed to negligible discovery rates.

It does not terminate the run.

It also does not replace the independent saturation/stopping protocol.

Weighted Random is not used as this fallback because Weighted Random is
a separate experimental comparison method.

UCB1, Thompson Sampling, and reinforcement-learning policies are not
part of the main experiment.

---

## 21. Adaptive State Update

At the completion of epoch `t` for selected arm `a_t`:

```text
pull_count[a_t]    += 1
recent_reward[a_t]  = R_t
last_selected[a_t]  = t

Q[a_t] =
    Q[a_t] +
    alpha * (R_t - Q[a_t])
```

Other arm states remain unchanged except for global epoch metadata.

At minimum, persistent diagnostic telemetry shall expose:

```text
epoch
selected_arm
selection_mode
epsilon
alpha
batch_size
actual_epoch_instructions
new_global_L2_intent_bins
new_attributable_L2_intent_bins
reward
Q_before
Q_after
pull_count
```

`selection_mode` shall distinguish at least:

* `initial_sweep`;
* `epsilon_explore`;
* `exploit`;
* `qfloor_uniform`.

---

## 22. Seed and RNG Contract

All stochastic decisions within one experimental run shall derive from
the run's configured seed.

This includes:

* initial arm permutation;
* epsilon decision;
* exploration arm selection;
* exploitation tie breaking;
* register target tie breaking;
* within-arm variant selection;
* auxiliary-register randomization.

No unseeded secondary random-number generator is permitted.

For a fixed implementation, configuration, and seed, Adaptive CGS
stimulus generation must be reproducible.

---

## 23. Hyperparameter Pre-Registration

The complete candidate space is frozen as:

```text
epsilon:
    {0.05, 0.10, 0.20}

alpha:
    {0.1, 0.3, 0.5}

batch_size:
    {500, 1000, 2000}
```

`Q_floor` is fixed at:

`0.05`

and is not pilot-tuned.

The discretionary template/filler ratio is fixed at:

`100:0`

and is not pilot-tuned.

The complete pilot search is the Cartesian product:

`3 × 3 × 3 = 27 configurations`.

No candidate value may be:

* added;
* removed;
* split;
* replaced;

after pilot coverage results have been inspected.

---

## 24. Pilot Seed Protocol

The pilot uses exactly:

`3 seeds per configuration`.

The frozen pilot seeds are:

```text
101
202
303
```

Thus:

`27 configurations × 3 seeds = 81 pilot runs`.

The maximum budget per pilot run is:

`100,000 executed instructions`.

Therefore the maximum nominal pilot stimulus budget is:

`8,100,000 executed instructions`

before accounting for pipeline-cycle effects.

Pilot seeds are used only for hyperparameter selection.

They shall not be reused as comparative evaluation seeds.

The final comparative campaign uses a disjoint pre-registered seed set.

---

## 25. Pilot Execution Schedule

Every one of the 27 configurations shall be evaluated on the same three
pilot seeds.

No configuration may receive additional seeds because its preliminary
result appears uncertain or poor.

The 81-run schedule shall be fixed before pilot coverage results are
inspected.

If practical, run order should be randomized using a fixed schedule RNG
seed to reduce systematic association between configuration and
time-varying host conditions.

The frozen schedule RNG seed is:

`20260919`.

Run failure caused by infrastructure shall follow the experimental
invalid-run rule rather than being silently replaced with a favorable
new seed.

---

## 26. Pilot Selection Metrics

Hyperparameter selection uses L2 Intent Coverage because Adaptive CGS
optimizes stimulus discovery rather than DUT correctness.

For every pilot run record:

* whether `59/62` L2 Intent bins are reached;
* exact `n@95%_intent`, if reached;
* `bins@100k_intent`;
* normalized L2 Intent coverage AUC;
* full-closure status;
* Adaptive CGS policy wall-clock overhead.

Validated coverage and checker failures shall also be logged but shall
not participate in hyperparameter selection.

---

## 27. Normalized Intent-Coverage AUC

For pilot discrimination, define the normalized area under the L2
Intent Coverage curve:

`AUC_norm`.

Let:

`C(N) = covered L2 Intent bins at instruction count N / 62`.

Then:

`AUC_norm = (1 / N_max) × integral_0^Nmax C(N) dN`.

In implementation, the integral may be approximated from the frozen
1,000-instruction checkpoints using trapezoidal integration.

Therefore:

`0 <= AUC_norm <= 1`.

Higher AUC means coverage was discovered earlier over the fixed
instruction budget.

This metric is used only as a pilot selection discriminator and does
not replace the final comparative metrics.

---

## 28. Final Hyperparameter Selection Criterion

The final configuration is selected using the following pre-registered
lexicographic criterion.

### Criterion 1 — 95% Success Count

Maximize:

`S95`

where `S95` is the number of the three pilot seeds that reach:

`59/62 L2 Intent bins`

within `N_max`.

Possible values are:

`0, 1, 2, 3`.

### Criterion 2 — Fixed-Budget Coverage

Among configurations tied on `S95`, maximize:

`mean(bins@100k_intent)`

across all three pilot seeds.

### Criterion 3 — Coverage AUC

Among configurations still tied, maximize:

`mean(AUC_norm)`

across all three pilot seeds.

### Criterion 4 — Time to Near Closure

If configurations remain tied and have successful `n@95%_intent`
observations, minimize the median successful:

`n@95%_intent`.

No fabricated time-to-threshold value is assigned to a seed that did
not reach 59/62.

### Criterion 5 — Deterministic Final Tie Break

If configurations remain exactly tied on all preceding criteria, select
the lexicographically smallest tuple:

`(epsilon, alpha, batch_size)`

using ascending numeric order.

This final rule exists only to make the selection procedure fully
deterministic.

It is not interpreted as evidence that smaller hyperparameters are
intrinsically superior.

---

## 29. No Pilot Significance Claim

The three pilot seeds are intended for configuration selection, not
inferential statistical claims.

No p-value, confidence interval, or statement of statistical superiority
shall be derived from the 3-seed pilot.

Statistical comparison is reserved for the later fixed comparative
campaign.

---

## 30. Interaction with Validated Coverage

Adaptive policy decisions use:

* L2 Intent Coverage;
* arm reward history;
* seeded RNG.

They shall not use:

* scoreboard pass/fail;
* L2 Validated Coverage;
* checker mismatch count;
* knowledge of a known DUT defect.

These verification results remain visible to the experiment but are
causally separated from policy adaptation.

This protects the experiment from teaching the generator to avoid
defect-revealing stimulus.

---

## 31. Stopping Contract

Adaptive CGS does not define its own independent stopping rule.

All runs obey the frozen:

`SATURATION_PROTOCOL.md`.

In particular:

* `N_max = 100,000 executed instructions`;
* plateau classification does not create an ad-hoc early stop;
* full closure and fixed-budget outcomes are recorded according to the
  common protocol.

This ensures Adaptive CGS receives the same experimental budget
definition as the comparison methods.

---

## 32. Computational Complexity

There are:

`A = 10 arms`.

Arm exploitation requires scanning all utilities:

`O(A) = O(10) = O(1)`

for the frozen policy.

Register-target selection is bounded by the frozen 31-register domain.

Utility update for the selected arm is:

`O(1)`.

Adaptive state memory is:

`O(A) = O(10) = O(1)`.

The computational bottleneck is expected to remain RTL simulation and
verification instrumentation rather than epsilon-greedy policy
evaluation.

---

## 33. Experimental Edge Cases

The implementation must explicitly handle:

* an epoch discovering zero new bins;
* an epoch discovering multiple new bins;
* A4 discovering two attributable bins;
* incidental non-attributable coverage;
* all arms tied at initialization;
* all arms falling below `Q_floor`;
* a run ending during what would otherwise be the next batch;
* a DUT failure on a correctly generated dependency;
* duplicate discovery of an already-covered bin;
* exact exploitation ties;
* full L2 Intent Coverage before validated closure;
* full L2 Intent Coverage causing future reward to become zero.

Once all 62 L2 Intent bins are covered, the adaptive reward necessarily
becomes zero.

Any continued execution required by the common experimental protocol
shall therefore eventually enter uniform `Q_floor` fallback as arm
utilities decay.

---

## 34. Frozen Adaptive Constants

```text
arms                    = 10

reward coverage         = L2 Intent
reward units            = new bins / 1,000 executed instructions

epsilon candidates      = {0.05, 0.10, 0.20}
alpha candidates        = {0.1, 0.3, 0.5}
batch candidates        = {500, 1000, 2000}

Q_init                  = 0.0
Q_floor                 = 0.05

template:filler         = 100:0 discretionary
initial sweep           = one pull per arm
initial sweep order     = seeded random permutation

pilot configurations    = 27
pilot seeds             = {101, 202, 303}
pilot runs              = 81
pilot N_max             = 100,000 executed instructions
schedule seed           = 20260919
```

These values shall not be modified after pilot coverage results have
been inspected.

---

## 35. Freeze Conditions

This specification may be marked PASS / FROZEN only when:

* exactly 10 arms are defined;
* arm-to-L1 mapping is explicit;
* L1-only negative/d3 scenarios are excluded from the bandit;
* register targeting uses L2 Intent Coverage;
* reward uses newly discovered attributable L2 Intent bins;
* reward is normalized by actual executed instructions;
* the exponential recency-weighted update is explicit;
* candidate epsilon values are frozen;
* candidate alpha values are frozen;
* candidate batch sizes are frozen;
* `Q_floor` is frozen;
* tie breaking is seeded and uniform;
* zero-utility fallback is explicit;
* adaptive state resets per seed;
* all 27 configurations are retained;
* pilot seeds are fixed;
* pilot and evaluation seeds are disjoint;
* pilot selection criteria are frozen;
* DUT correctness cannot affect adaptive reward.

---

## 36. Freeze Status

Current status:

`PASS / FROZEN`

Next artifact:

`research/week5/vplan/EXPERIMENTAL_PROTOCOL.md`
