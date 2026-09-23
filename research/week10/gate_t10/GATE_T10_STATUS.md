# Week 10 — Gate T10 Status

## Status

**CLOSED / PASS**

Gate T10 is complete.

Week 10 establishes the bounded, deterministic Adaptive Coverage-Guided
Stimulus campaign infrastructure required for controlled RTL experiments.

The engineering gate demonstrates:

- deterministic adaptive decision behavior;
- exact campaign instruction-budget enforcement;
- bounded physical IMEM residency;
- continuous multi-epoch RTL execution without DUT reset;
- post-instruction checkpoint semantics;
- bounded telemetry state;
- deterministic replay of the accepted RTL instruction trajectory.

Gate T10 is an engineering-readiness gate.

It does not constitute the final M1/M2/M3 stochastic comparative
experiment or the preregistered multi-seed campaign dataset.

---

## Frozen adaptive configuration

Engineering-gate configuration:

| Parameter | Frozen value |
|---|---:|
| Root seed | `20260921` |
| Epsilon | `0.10` |
| Alpha | `0.30` |
| Q floor | `0.05` |
| Nominal batch | `500` |
| Exact instruction budget | `5000` |
| Checkpoint interval | `1000` |

The Adaptive-CGS policy is epsilon-greedy with recency-weighted
action-value updating:

`Q_(t+1)(a) = Q_t(a) + alpha * (R_t - Q_t(a))`

Reward is normalized by the actual number of architecturally executed
instructions in the epoch:

`R_t = 1000 * DeltaNewAttributedL2IntentBins / DeltaActualExecutedInstructions`

This is a multi-armed bandit policy.

It is not Q-learning.

---

## Deterministic RNG partition

PASS.

A single root seed is deterministically partitioned into independent
domain-separated RNG streams for:

- adaptive decision policy;
- target selection;
- concrete template realization.

Frozen engineering seed vector:

- root: `20260921`
- decision: `16680843080276206783`
- target: `1163466188706097826`
- realization: `7717841318315519387`

Filler insertion and epoch-boundary delimiters do not consume adaptive
RNG state.

This prevents unrelated implementation choices from perturbing the
adaptive decision trajectory.

---

## Exact instruction-budget semantics

PASS.

The production campaign terminates at exactly:

`Nmax = 5000 architecturally accepted instructions`

The final accepted instruction completes the normal verification cut:

- timing observation;
- architectural validation;
- L2 observation;
- coverage post-instruction processing;
- checkpoint processing when applicable.

No instruction beyond `Nmax` is architecturally accepted.

The final planned template may extend beyond the exact architectural
budget.

The unexecuted suffix is explicitly discarded rather than being treated
as executed.

No epoch-boundary delimiter is planned beyond the exact architectural
budget.

The final partial epoch receives exactly one epoch completion and one
adaptive Q-value update.

---

## Epoch-boundary delimiter semantics

PASS.

Each ordinary adaptive epoch begins with one deterministic
epoch-boundary delimiter:

`EBD = bne x0, x0, +4`

The delimiter:

- is architecturally executed;
- does not redirect control;
- does not write architectural GPR or memory state;
- has no positive dependency source;
- consumes no adaptive RNG state;
- is excluded from arm attribution;
- counts toward the architectural instruction denominator.

For ordinary non-final epochs, `EBD_(t+1)` may be preseeded while epoch
`t` is still executing.

For the final budget-crossing epoch, no EBD is created when its
architectural instruction index would exceed `Nmax`.

---

## Bounded physical IMEM streaming

PASS.

The DUT instruction memory contains:

`128 words = 512 bytes`

Adaptive campaign images may be much longer than the physical IMEM.

The bounded runtime stream therefore:

- admits complete stream entries only;
- releases completed FIFO entries;
- reclaims timing ownership for released physical slots;
- patches new logical instructions into reusable physical slots;
- preserves monotonic logical instruction ordering;
- supports physical PC wrap and multiple physical-slot generations;
- maintains continuous architectural and adaptive state.

The production engineering campaign observed:

`max_resident_words = 125`

Therefore:

`125 <= 128`

Physical IMEM residency remained bounded throughout the complete
5000-instruction campaign.

The asymptotic retained streaming state is:

`O(1)` with respect to campaign instruction count `N`.

---

## Continuous multi-epoch RTL execution

PASS.

The production engineering campaign completed:

- accepted instructions: `5000`
- adaptive epochs: `10`
- DUT resets during campaign execution: `0`

Adaptive state remains continuous across epoch boundaries:

- Q-values;
- arm pull counts;
- coverage state;
- target policy state;
- architectural state;
- timing state;
- logical instruction numbering.

Clock ownership remains singular.

Runtime IMEM patching occurs only while the sole clock owner is stopped
HIGH, without asserting DUT reset.

---

## Checkpoint semantics

PASS.

Frozen checkpoint interval:

`1000 accepted instructions`

Observed checkpoints:

- `1000`
- `2000`
- `3000`
- `4000`
- `5000`

Checkpoint state is recorded only after completion of the full
post-instruction cut.

Therefore checkpoint `N` observes coverage and verification state
through architectural instruction `N`.

Observed checkpoint count:

`5`

---

## Telemetry and bounded retained state

PASS.

Production telemetry records:

- per-epoch adaptive state;
- reward and Q-value updates;
- campaign checkpoints;
- final campaign summary.

Streaming sinks are used with retained in-memory records disabled.

Therefore telemetry retained state remains:

`O(1)` with respect to campaign length.

The production manifest recorded:

- executed instructions: `5000`
- hashed accepted events: `5000`
- completed epochs: `10`
- checkpoint count: `5`
- maximum resident words: `125`
- refill count: `1004`

The equality

`instruction_budget = executed_instructions = hashed_accepted_event_count = 5000`

demonstrates completeness of the exact-budget execution and trajectory
hash input.

---

## Accepted-trajectory reproducibility

PASS.

The accepted RTL trajectory is streamed into SHA-256 without retaining
the complete instruction trace in memory.

The trajectory digest includes deterministic per-accepted-instruction
information including:

- architectural instruction index;
- logical instruction owner;
- physical PC;
- instruction word;
- stall count;
- forwarding selections.

Frozen engineering trajectory digest:

`4498b8485971c358f6aa48b9a19092afac7e1f830bc590f1940327d0bb91e962`

Two clean executions from the same committed implementation and frozen
configuration produced the same digest.

Run A:

- executed instructions: `5000`
- epochs: `10`
- checkpoints: `5`
- trajectory SHA-256:
  `4498b8485971c358f6aa48b9a19092afac7e1f830bc590f1940327d0bb91e962`

Run B:

- executed instructions: `5000`
- epochs: `10`
- checkpoints: `5`
- trajectory SHA-256:
  `4498b8485971c358f6aa48b9a19092afac7e1f830bc590f1940327d0bb91e962`

Byte-for-byte artifact comparison:

| Artifact | Comparison |
|---|---:|
| `manifest.json` | identical |
| `summary.json` | identical |
| `checkpoints.jsonl` | identical |
| `epochs.jsonl` | identical |

All `cmp` exit codes were:

`0`

Therefore the engineering campaign demonstrated deterministic replay of
both the accepted instruction trajectory and exported campaign
telemetry.

---

## Adaptive RTL integration regression

PASS.

Final adaptive RTL regression:

| Test | Result |
|---|---:|
| one-epoch Adaptive-CGS RTL end-to-end | PASS |
| continuous multi-epoch adaptive RTL | PASS |
| bounded intra-epoch streaming, b=500 | PASS |
| exact-N hard-cap termination | PASS |
| production engineering campaign | PASS |
| **Total** | **5 / 5** |

The production campaign itself completed:

- exact accepted instructions: `5000`
- epochs: `10`
- checkpoints: `5`
- maximum resident words: `125`
- trajectory SHA-256:
  `4498b8485971c358f6aa48b9a19092afac7e1f830bc590f1940327d0bb91e962`

---

## Week-10 Python regression

PASS.

Final Week-10 Python regression:

`363 / 363`

This includes focused tests for:

- adaptive decision semantics;
- target selection;
- deterministic template realization;
- attribution;
- epoch coordination;
- telemetry;
- deterministic RNG partition;
- bounded stream admission;
- exact-budget suffix discard;
- campaign planner termination;
- production campaign construction;
- hard-budget EBD admission control.

The budget-aware feeder specifically verifies:

- EBD beyond `Nmax` is rejected without planner mutation;
- EBD exactly at `Nmax` remains legal;
- invalid hard-budget values fail fast.

---

## Frozen-tree integrity

PASS.

Comparison against `gate-t8`:

`frozen_diff = 0`

No modifications were made under:

- `design`
- `research/week5`
- `research/week6`
- `research/week7`
- `research/week8`

The Week-10 campaign infrastructure therefore preserves the previously
frozen RTL and verification baselines.

---

## Scope boundary

Gate T10 establishes engineering readiness for adaptive campaign
experimentation.

The gate does not claim completion of the final stochastic comparative
study.

The following remain separate experimental activities:

- preregistered pilot campaigns;
- M1/M2/M3 comparative runs;
- 15-seed final campaigns;
- statistical comparison of coverage efficiency;
- final research conclusions.

Those experiments must use the frozen campaign semantics established by
Gate T10.

---

## Evidence chain

Relevant commits:

- `81ec364` — add adaptive campaign telemetry recorder
- `f6afdac` — integrate adaptive telemetry into RTL campaign
- `efa8a63` — add bounded intra-epoch capacity feeder
- `c8b6499` — add reusable bounded RTL stream patching
- `4c05754` — prove bounded intra-epoch RTL streaming at b500
- `5f9da8c` — freeze adaptive campaign execution semantics
- `7808c00` — freeze deterministic campaign RNG partition
- `026ce85` — add exact-budget suffix termination
- `9a4053a` — prove exact-budget RTL termination
- `8a560d4` — add terminal campaign planner cleanup
- `260e7cc` — add production adaptive campaign stack
- `d1e4a25` — integrate exact-budget production RTL campaign

---

## Gate T10 Decision

All required Gate-T10 engineering obligations have been satisfied:

- frozen adaptive policy: PASS
- deterministic RNG partition: PASS
- exact architectural instruction budget: PASS
- complete final-instruction verification cut: PASS
- no accepted instruction beyond `Nmax`: PASS
- no EBD beyond `Nmax`: PASS
- explicit unexecuted-suffix discard: PASS
- exactly one final partial-epoch update: PASS
- deterministic epoch-boundary semantics: PASS
- bounded physical IMEM streaming: PASS
- physical-PC wrap support: PASS
- continuous multi-epoch execution: PASS
- no inter-epoch DUT reset: PASS
- bounded retained runtime state: PASS
- bounded telemetry state: PASS
- exact post-instruction checkpoints: PASS
- complete accepted-event trajectory hashing: PASS
- deterministic A/B trajectory replay: PASS
- deterministic A/B telemetry replay: PASS
- Week-10 Python regression: PASS
- adaptive RTL regression: PASS
- frozen-tree integrity: PASS

**Gate T10: CLOSED / PASS**
