# Week10 Adaptive-CGS Campaign Execution Semantics Amendment

## 1. Status and Scope

This amendment freezes two implementation semantics that were referenced
but not fully specified by the closed Gate-T5 preregistration and the
Week10 Adaptive-CGS contract:

1. deterministic partitioning of one experimental seed into independent
   stochastic subsystems;
2. exact campaign termination at an executed-instruction budget.

This amendment is frozen before the first Gate-T10 engineering dry-run,
before the preregistered pilot, and before final M1/M2/M3 execution.

It does not modify:

- the A0-A9 arm taxonomy;
- epsilon-greedy policy;
- Q-floor fallback;
- reward definition;
- recency-weighted Q update;
- register-targeting semantics;
- template semantics;
- the deterministic 80:20 payload filler policy;
- EBD semantics;
- checkpoint semantics.

---

## 2. Root Experimental Seed

Each campaign run has one authoritative root experimental seed:

```text
S
```

Examples include:

```text
Gate-T10 engineering:
    S = 20260921

Adaptive-CGS pilot:
    S in {13001, 13002, 13003}

Final Adaptive-CGS (M3) campaigns:
    the frozen M3 seed protocol
```

This RNG-domain-separation rule applies to Adaptive-CGS stochastic
subsystems. It does not redefine the stochastic protocol of M1 or M2.

All stochastic state is reset at the beginning of each run.

No RNG state is inherited between campaign runs.

---

## 3. Deterministic RNG Domain Separation

The root seed is deterministically partitioned into three independent
subsystem seeds.

For subsystem tag `k`:

```text
message =
    "week10-adaptive-cgs-v1|" + decimal(S) + "|" + k
```

where:

```text
k in {
    "decision",
    "target",
    "realization"
}
```

Compute:

```text
digest = SHA256(UTF8(message))
```

and define:

```text
subseed =
    unsigned big-endian integer represented by digest[0:8]
```

Thus:

```text
decision_seed    = derive(S, "decision")
target_seed      = derive(S, "target")
realization_seed = derive(S, "realization")
```

For the frozen Gate-T10 root seed, the derivation test vector is:

```text
S = 20260921

decision_seed =
    16680843080276206783

target_seed =
    1163466188706097826

realization_seed =
    7717841318315519387
```

An implementation producing different values for this test vector is
non-conformant.

The corresponding Python RNGs are initialized exactly once per campaign:

```text
decision_rng    = Random(decision_seed)
target_rng      = Random(target_seed)
realization_rng = Random(realization_seed)
```

No Python `hash()` value may participate in seed derivation.

No process-dependent or platform-dependent entropy may participate in
seed derivation.

The deterministic campaign filler scheduler consumes no RNG state.

The EBD mechanism consumes no RNG state.

---

## 4. RNG Ownership

The RNG streams have fixed ownership:

```text
decision_rng
    epsilon exploration draw
    uniform exploratory arm selection
    maximum-Q tie breaking
    Q-floor uniform fallback

target_rng
    uncovered-first register-target tie breaking
    saturated-register fallback selection
    A4 maximum-opportunity ordered-pair tie breaking

realization_rng
    stochastic template variants explicitly defined by the frozen
    template realizer
```

A subsystem MUST NOT draw from another subsystem's RNG.

This separation ensures that a change in one subsystem's number of RNG
draws cannot silently perturb stochastic decisions made by another
subsystem.

---

## 5. Reproducibility Requirement

For identical:

```text
root seed
configuration
initial Q state
initial coverage state
```

the campaign MUST reproduce identical:

```text
derived subsystem seeds
arm selections
register targets
template variants
filler sequence
epoch rewards
Q trajectory
checkpoint sequence
termination instruction index
```

Implementation changes MUST preserve this reproducibility requirement unless
a later explicitly frozen amendment changes the stochastic semantics before
affected experimental observations are collected.

---

## 6. Executed-Instruction Budget

For any campaign instruction budget:

```text
Nmax
```

`Nmax` is a hard cap on architecturally accepted instructions.

The count includes every accepted EBD.

The count excludes:

- flushed wrong-path instructions;
- instructions that were planned or patched but never accepted;
- any unexecuted suffix present when the campaign terminates.

The final architecturally accepted instruction MUST have:

```text
instruction_index == Nmax
```

No instruction having:

```text
instruction_index > Nmax
```

may be architecturally accepted.

Therefore:

```text
engineering dry-run:
    exactly 5000 accepted executed instructions

pilot:
    exactly 10000 accepted executed instructions

final campaign:
    exactly Nmax accepted executed instructions
```

unless the run terminates earlier because of an explicit fail-fast
condition.

---

## 7. Normal Epoch Planning

For ordinary non-final campaign execution, the frozen batch rule remains:

```text
1 EBD + planned adaptive payload executed >= b
```

Complete template instances are not split merely to meet nominal batch
threshold `b`.

Normal complete-template overshoot at the batch boundary remains legal.

The selected arm remains fixed for the complete adaptive epoch.

No Q update occurs inside an epoch.

---

## 8. Final Campaign Truncation

The hard `Nmax` limit has priority only at final campaign termination.

This is the only campaign-level exception to the normal complete-template
execution rule.

Planning and patching still operate on complete stream entries. However,
the architecturally executed campaign is the exact prefix ending at
`Nmax`; therefore the final executed prefix may terminate inside an
already-planned template instance.

Such terminal truncation does not redefine the template, filler, or
batch policy. An intended dependency whose required consumer is not
executed before `Nmax` produces no attributable hit and no reward.

If `Nmax` is reached before all already-planned stream entries have
executed:

1. the event having `instruction_index == Nmax` is processed normally;
2. timing evidence is processed normally;
3. architectural evidence is processed normally;
4. L2 observation and attribution are processed normally;
5. the post-instruction coverage cut is completed normally;
6. the runtime accepted count becomes exactly `Nmax`;
7. the sole DUT clock is stopped while HIGH;
8. no additional architectural edge is permitted;
9. the unexecuted resident stream suffix is discarded explicitly;
10. unexecuted attribution witnesses are discarded without being counted
    as hits, misses, coverage, or reward;
11. timing ownership corresponding only to the unexecuted suffix is
    released;
12. the active adaptive epoch is finalized using the actual number of
    instructions executed in that epoch;
13. reward uses only attributable L2 Intent bins actually observed during
    executed instructions of that epoch;
14. the selected arm receives exactly one final Q update;
15. campaign telemetry is finalized with
    `executed_instructions == Nmax`.

Final campaign truncation MUST NOT fabricate execution of the discarded
suffix.

---

## 9. EBD at Final Termination

An EBD that has already executed counts normally.

An EBD that is only planned or patched but has not executed when `Nmax`
is reached does not count.

A new epoch MUST NOT be started when the global accepted count is already:

```text
Nmax
```

No lookahead EBD for a nonexistent post-termination epoch may be executed.

---

## 10. Coverage and Checkpoints

The instruction at `Nmax` receives the same post-instruction consistent
coverage cut as every other executed instruction.

If `Nmax` is also a checkpoint boundary, that checkpoint reflects state
after all coverage observers for instruction `Nmax` complete.

No checkpoint beyond `Nmax` is generated.

---

## 11. Telemetry

Production campaign execution uses:

```text
retain_records = False
```

with streaming sinks.

The final summary records:

```text
root seed
epsilon
alpha
Q_floor
nominal batch
instruction budget
executed instructions
completed epochs
termination reason
final coverage
final Q values
pull counts
recent rewards
```

For normal budget completion:

```text
termination_reason = "instruction_budget_reached"
```

and:

```text
executed_instructions == instruction_budget
```

must hold.

---

## 12. Complexity

Seed derivation is:

```text
O(1) time
O(1) memory
```

with respect to campaign length.

Final-suffix termination cleanup is bounded by the physical resident
window:

```text
<= 128 IMEM words
```

and is therefore:

```text
O(1)
```

with respect to total campaign instruction count `N`.

The full campaign remains:

```text
O(N) time
O(1) retained runtime state
```

with respect to campaign length.

---

## 13. Fail-Fast Requirements

The campaign MUST fail rather than silently compensate if:

- a derived subsystem seed differs from the frozen derivation;
- more than one subsystem uses the same mutable RNG object;
- accepted instruction count exceeds `Nmax`;
- an architectural edge occurs after acceptance of instruction `Nmax`;
- final discarded instructions affect coverage or reward;
- final telemetry does not report exactly `Nmax` executed instructions
  for normal budget termination;
- a normal epoch boundary uses final-run truncation semantics;
- the final Q update is omitted or duplicated.

No hidden instruction-count correction is permitted.

---

## 14. Gate Requirement

Before the Gate-T10 engineering run, tests MUST prove:

1. deterministic seed derivation;
2. independent RNG stream ownership;
3. exact reproducibility for the same root seed;
4. exactly-N termination inside a partially executed resident stream
   entry;
5. no instruction is accepted after `Nmax`;
6. final post-instruction checkpoint semantics remain correct;
7. discarded suffix instructions do not affect coverage or reward;
8. final partial epoch receives exactly one Q update;
9. runtime/timing resident state is safely reclaimed;
10. Week5-Week8 frozen sources remain unchanged.
