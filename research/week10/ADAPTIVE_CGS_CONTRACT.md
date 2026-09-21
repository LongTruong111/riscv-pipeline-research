# Week 10 — Adaptive CGS Implementation Contract

## 1. Baseline

Authoritative development baseline:

```text
gate-t9
e873955 docs(week9): close gate t9
```

Week5–Week8 remain frozen.

Existing Week10 L2 realization infrastructure is preserved and reused.

---

## 2. Protocol Authority and Legacy Reconciliation

For Adaptive-CGS fields explicitly redefined by the later closed Gate-T5 preregistration, `research/week5/gate_t5/ADAPTIVE_PREREGISTRATION.md` is authoritative over the earlier VPlan.

The earlier VPlan remains authoritative for compatible implementation semantics not superseded by the later preregistration.

Resolved legacy conflicts:

```text
template:filler:
    obsolete VPlan: 100:0 discretionary
    authoritative: 80:20

pilot seeds:
    obsolete VPlan: {101, 202, 303}
    authoritative: {13001, 13002, 13003}

pilot budget:
    obsolete VPlan: 100000 instructions/config/seed
    authoritative: 10000 instructions/config/seed

mandatory initial sweep:
    obsolete legacy rule
    no mandatory one-pull-per-arm sweep is used
```

Final M3 evaluation remains:

```text
15 independent seeds
100000 executed instructions / seed
```

---

## 3. Algorithm Classification

Adaptive CGS is an:

```text
epsilon-greedy multi-armed bandit
```

using recency-weighted action-value estimates.

It shall not be described as classical Q-learning.

For selected arm \(a_t\):

$$
Q_{t+1}(a_t)
=
Q_t(a_t)
+
\alpha
\left[
R_t-Q_t(a_t)
\right].
$$

Unselected arms retain their current values.

---

## 4. Adaptive Objective

The adaptive optimization objective is exclusively:

```text
L2 Intent Coverage
```

L2 is:

$$
\{d1,d2\}\times\{x1,\ldots,x31\}
$$

with exactly 62 bins.

Validated Coverage is collected independently and shall never drive:

```text
reward
Q update
arm selection utility
adaptive register targeting
```

---

## 5. Reward and Attribution

Let \(S_t\) be the L2 Intent bins already covered at the beginning of epoch \(t\).

Let:

$$
\Delta B_{\mathrm{new,attrib}}(t)
$$

be the unique bins that:

1. were not in \(S_t\);
2. were exercised during epoch \(t\);
3. are semantically attributable to the arm selected for epoch \(t\).

Reward is:

$$
R_t
=
1000
\frac{
\Delta B_{\mathrm{new,attrib}}(t)
}{
\Delta N_{\mathrm{executed,actual}}(t)
}.
$$

Incidental dependencies may update global L2 Intent Coverage if they satisfy the frozen L2 collector contract.

Incidental coverage does not reward the selected arm unless the event satisfies that arm's attribution contract.

Validated Coverage never changes Intent reward.

---

## 6. Feedback Epoch

Each feedback epoch selects exactly one arm.

For candidate nominal batch threshold:

```text
b in {500, 1000, 2000}
```

the selected arm generates complete template instances until the actual executed-instruction count first reaches or exceeds `b`.

A template instance shall not be split merely to hit the nominal boundary.

Therefore:

```text
DeltaN_actual may differ from b
```

and reward normalization must always use actual executed instructions.

---

## 7. Frozen Arms

Exactly ten arms exist:

```text
A0 ALU_D1
A1 ALU_D2
A2 LOAD_D1
A3 LOAD_D2
A4 DUAL_D1_D2
A5 SPECIAL_WB_D1
A6 SPECIAL_WB_D2
A7 LINK_D1
A8 STORE_DATA_D1
A9 PRIORITY_D1
```

No arm may be added, removed, split, merged, or semantically redefined.

---

## 8. Initial State

At the start of each seed:

```text
Q[a]             = 0.0
pull_count[a]    = 0
recent_reward[a] = 0.0
epoch_index      = 0
```

Coverage and RNG state also reset.

No adaptive state is inherited between seeds.

No mandatory initial one-pull-per-arm sweep is performed.

---

## 9. Arm Selection

Candidate epsilon values:

```text
{0.05, 0.10, 0.20}
```

Exploration:

```text
probability epsilon
uniform random over A0..A9
```

Exploitation:

```text
probability 1-epsilon
select maximum-Q arm
```

Exact maximum ties use seeded uniform random selection.

First-index deterministic argmax is forbidden.

No arm is removed solely because it has low utility.

No untried-arm bonus or optimistic initialization is used.

---

## 10. Q-floor Fallback

Frozen threshold:

```text
Q_floor = 0.05
```

Unit:

```text
new attributable L2 Intent bins /
1000 executed instructions
```

After learning has begun, when:

$$
\max_a Q[a]\le Q_{\mathrm{floor}}
$$

the following epoch uses uniform selection over all ten arms.

This fallback does not terminate the run.

Weighted Random is not used as fallback.

---

## 11. Register Targeting

Positive target registers:

```text
x1 ... x31
```

`x0` is excluded.

For distance \(d\):

$$
U_d=
\{
r\in x1..x31:
IntentSeen(d,r)=0
\}.
$$

If \(U_d\neq\varnothing\), target uniformly from \(U_d\).

If the distance is saturated, target uniformly from all `x1..x31`.

A4 requires distinct d1 and d2 target registers.

A9 attributes only the newest writer.

### A4 Dual-Target Resolution

A4 must satisfy:

```text
R_d1 != R_d2
```

Let:

```text
U_d1 = uncovered positive registers for d1
U_d2 = uncovered positive registers for d2
```

A4 selects an ordered register pair:

```text
(R_d1, R_d2)
```

subject to:

```text
R_d1 != R_d2
```

For every valid pair, define:

```text
opportunity_score =
    1[R_d1 in U_d1] +
    1[R_d2 in U_d2]
```

The targeting policy selects uniformly, using the experiment RNG,
among valid pairs having the maximum `opportunity_score`.

This rule maximizes the number of currently uncovered L2 Intent
opportunities realized by A4 while preserving the frozen
distinct-register constraint.

If both distances have the same single uncovered register, both bins
cannot be targeted simultaneously because A4 requires distinct
registers. In that case, the maximum opportunity score is one, and the
seeded tie-break determines which distance receives the uncovered
register.

If a distance is saturated, it contributes no uncovered-opportunity
score. Its register is selected from the remaining legal positive
registers subject to the A4 distinctness constraint.

This rule affects only register targeting. It does not modify reward,
coverage attribution, or arm-selection policy.

All candidate register collections must be placed into a canonical
deterministic order before seeded random selection. Python set/hash
iteration order must not affect the generated trace.

---

## 12. Template and Filler Policy

Authoritative campaign composition:

```text
80% targeted-template instructions
20% filler instructions
```

Campaign filler is distinct from structural instructions required inside a template to realize d2, control flow, or other template semantics.

Filler must:

* be ISA-legal;
* remain seed-deterministic;
* not implement a hidden adaptive policy;
* not intentionally target coverage based on current uncovered bins;
* preserve protected producer/consumer dependencies where required.

---

## 13. Invalid Template Handling

Templates should be valid by construction.

Constraints such as distinct registers shall be enforced constructively rather than using unbounded rejection loops.

If a valid template cannot be constructed:

```text
TemplateConstructionError
```

is raised.

Such a failure:

```text
is not an arm pull
does not consume executed-instruction budget
does not create a reward observation
does not update Q
```

---

## 14. Experimental Parameters

Frozen pilot search space:

```text
epsilon = {0.05, 0.10, 0.20}
alpha   = {0.1, 0.3, 0.5}
batch   = {500, 1000, 2000}
```

Pilot seeds:

```text
13001
13002
13003
```

Pilot budget:

```text
10000 executed instructions / configuration / seed
27 configurations
81 total runs
810000 maximum executed instructions
```

Final M3 configuration is selected only by the frozen preregistered pilot criterion.

---

## 15. Gate-T10 Engineering Configuration

The engineering Gate configuration is not a selected or claimed optimal M3 configuration.

Freeze before the first Gate-T10 execution:

```text
epsilon    = 0.10
alpha      = 0.30
batch      = 500 executed instructions
gate seed  = 20260921
dry-run    = 5000 executed instructions
```

These values exist only to test implementation behavior.

---

## 16. Gate-T10 Verification

### Bandit conformance

Deterministically verify:

```text
exploration
exploitation
maximum-Q ties
zero reward
recency-weighted Q update
Q-floor fallback
pull counts
recent reward
```

### Adaptive coverage-path witness

For a controlled compatible arm and uncovered target:

```text
arm
→ uncovered-first target
→ template
→ RTL
→ attributable L2 Intent hit
→ reward
→ Q update
```

The target must be hit within the adaptation epoch generated for that controlled arm.

### Reproducibility

Identical:

```text
seed
configuration
initial Q
initial coverage
```

must generate identical:

```text
arm selections
register choices
template variants
filler choices
rewards
Q trajectory
```

### Dry-run

```text
5000 executed instructions
no crash
no infinite loop
bounded retained state
```

---

## 17. Complexity Requirements

With ten arms and 31 positive registers:

```text
Q update            O(1)
arm selection       O(10) = O(1) wrt campaign length
register targeting  O(31) = O(1) wrt campaign length
retained state      O(1) wrt campaign length
full campaign       O(N)
```

No campaign-length Python event history may be retained in production execution.
