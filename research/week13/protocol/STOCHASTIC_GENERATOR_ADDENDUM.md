# WEEK 13 — STOCHASTIC GENERATOR ADDENDUM

**Project:** RISC-V 5-stage pipeline verification
**Artifact:** `research/week13/protocol/STOCHASTIC_GENERATOR_ADDENDUM.md`
**Version:** `w13.stochastic-generator.v1.1`
**Date:** `2026-09-26`
**Status:** PRE-PILOT FREEZE — effective when committed before the first Week-13 pilot observation.

---

## 1. Purpose

This addendum closes implementation degrees of freedom that were left underspecified by the frozen Week-5 experimental protocol before any Week-13 Pure-Random or Adaptive pilot result is inspected.

It does **not** redefine:

* H01–H20;
* L1 coverage semantics;
* L2 = `{d1,d2} × {x1,...,x31}` = 62 bins;
* Intent / Validated separation;
* accepted executed-instruction denominator;
* M2 Weighted-Random A0–A9 probabilities;
* M3 Adaptive-CGS reward, candidate space, or selection criterion;
* final stochastic sample size;
* final evaluation seeds;
* final `100,000 accepted executed instructions / seed` budget;
* statistical analysis protocol.

The addendum completes only implementation semantics required to instantiate the already-frozen stochastic methods reproducibly.

---

## 2. Authority and historical relationship

Week 5 defines M1 Pure Random as:

* having no coverage feedback;
* not targeting uncovered registers;
* sampling from the common frozen legal generator domain;
* using stochastic register and operand choices;
* keeping legality constraints independent of campaign progress.

Week 5 does not freeze the exact M1:

* instruction-family probability distribution;
* GPR destination envelope;
* control-flow realization policy;
* memory-address realization policy;
* RNG substream mapping;
* draw order;
* Pure-Random Week-13 pilot seeds.

This document freezes those implementation details **before pilot execution**.

It is therefore an implementation completion of an underspecified frozen method, not a post-hoc change to an observed experiment.

---

## 3. Method and mutation naming

The following names are normative:

```text
M0-DIR       Directed verification
M1-PR        Pure Random
M2-WR        Weighted Random
M3-ACGS      Adaptive CGS

MUT-M1       Week-12 forwarding-path mutation
MUT-M2-x0    Week-13 rd=x0 forwarding-exclusion mutation
```

The mutation namespace shall not be interpreted as additional stochastic comparative methods.

---

## 4. Frozen architectural instruction domain

M1-PR operates only on the frozen supported ISA subset:

```text
ADD
ADDI
LW
SW
LUI
AUIPC
JAL
JALR
BEQ
BNE
BLT
BGE
BLTU
BGEU
```

Unsupported RV32I instructions shall not be generated.

M1-PR is **not** uniform over arbitrary 32-bit encodings.

It is random over the explicitly frozen legal generation envelope defined below.

---

## 5. M1 structural-family distribution

The M1 payload-family universe is:

```text
F0  ADD
F1  ADDI
F2  LW
F3  SW
F4  BRANCH
F5  JAL
F6  JALR
F7  LUI
F8  AUIPC
```

At every stochastic payload-family draw:

$$
P(F_i)=\frac{1}{9}.
$$

The ordered family tuple is frozen exactly as:

```text
(
    ADD,
    ADDI,
    LW,
    SW,
    BRANCH,
    JAL,
    JALR,
    LUI,
    AUIPC,
)
```

For `BRANCH`, the subtype is selected uniformly from:

```text
BEQ
BNE
BLT
BGE
BLTU
BGEU
```

therefore:

$$
P(B_j\mid BRANCH)=\frac{1}{6}.
$$

No family or branch-subtype probability may depend on:

* Intent coverage;
* Validated coverage;
* uncovered bins;
* campaign age;
* checkpoint state;
* checker results;
* prior DUT behavior.

The uniformity claim applies to **stochastic payload-family draws**, not to verification-only structural words inserted to make bounded control-flow blocks executable.

---

## 6. Register-domain contract

For every stochastic payload instruction that architecturally writes a GPR:

$$
rd\in\{x1,\ldots,x31\}.
$$

For unconstrained architectural source operands:

$$
rs1,rs2\in\{x0,\ldots,x31\}.
$$

Selections are uniform over their declared eligible sets unless a state-dependent legality set is explicitly defined below.

The `rd != x0` restriction is a positive-campaign generation constraint.

It does not modify architectural semantics or checker semantics.

---

## 7. x0 defect containment

The baseline DUT register file permits a physical write to `x0`.

The harmful activation condition is:

$$
RegWrite \land rd=x0 \land WriteData\neq0.
$$

The positive stochastic payload envelope prevents this condition by construction because stochastic GPR-writing payloads use:

$$
rd\in\{x1,\ldots,x31\}.
$$

The canonical structural NOP is:

```text
addi x0, x0, 0
```

and may physically assert a write to `x0`, but its write value is zero and therefore does not corrupt the reset-zero `x0` state.

The architectural oracle and checker remain unrestricted:

$$
x0=0
$$

is still an invariant.

Generation is constrained; checking is not weakened.

Directed H18/H19 evidence and `MUT-M2-x0` remain separate verification obligations.

---

## 8. Initial architectural state

Every independent stochastic run starts from:

```text
x0..x31 = 0
DMEM     = all zero
PC       = 0
```

DMEM zero initialization matches the canonical RTL initialization and empty `data.hex` baseline.

Arithmetic state remains RV32 modulo:

$$
2^{32}.
$$

No state is inherited across independent seeds.

---

## 9. Shadow architectural semantics

Offline generation shall use the frozen architectural semantics implemented by:

```text
research/week5/impl/architectural_model.py
```

with DUT physical-fetch behavior supplied by:

```text
research/week10/adaptive/wrap_aware_architectural_model.py
```

The generator shall not contain an independent reimplementation of architectural instruction semantics.

A refactoring is permitted only if existing Golden-Model behavior remains unchanged and regression-tested.

The shadow state is legality machinery, not adaptive state.

It consumes only:

```text
root seed
frozen generator specification
previously emitted/planned architectural history
```

It shall consume no DUT-observed coverage feedback.

Therefore the generated program plan is a deterministic function:

$$
Plan=G(seed,spec).
$$

---

## 10. Physical instruction-memory contract

The DUT physical instruction-fetch PC width is:

```text
9 bits
```

therefore:

$$
PC_{phys}\in[0,511].
$$

The runtime IMEM contains:

```text
128 × 32-bit words
512 bytes
```

with mapping:

$$
physical\_word=logical\_word\bmod128
$$

and:

$$
physical\_pc=4\times physical\_word.
$$

Legal executable word addresses are:

$$
\{0,4,8,\ldots,508\}.
$$

Logical program order is unbounded while physical placement wraps through this 128-word ring.

---

## 11. Ordinary arithmetic realization

### ADD

Draw in fixed order:

```text
rd
rs1
rs2
```

with:

```text
rd  ~ Uniform(x1..x31)
rs1 ~ Uniform(x0..x31)
rs2 ~ Uniform(x0..x31)
```

### ADDI

Draw:

```text
rd
rs1
imm12
```

where:

$$
imm12\sim Uniform(\{-2048,\ldots,2047\}).
$$

No additional ADDI magnitude restriction is imposed.

### LUI / AUIPC

Draw:

```text
rd
imm20
```

where:

$$
imm20\sim Uniform(\{0,\ldots,2^{20}-1\}).
$$

Register magnitude generated by these instructions is not artificially bounded.

---

## 12. Canonical DMEM envelope

The DUT data-memory interface consumes:

```text
ALUResult[8:0]
```

as a byte address.

To prevent avoidable full-address versus truncated-address aliasing from becoming a comparative confound, M1-PR canonicalizes all word-memory effective addresses to:

$$
EA\in\{0,4,8,\ldots,508\}.
$$

Only aligned `LW` and `SW` accesses are generated.

Misaligned-memory verification is outside this stochastic envelope.

---

## 13. LW/SW target-first realization

Memory realization uses **legal construction**, not random-immediate rejection.

First draw:

$$
EA\sim Uniform(\{0,4,\ldots,508\}).
$$

For each candidate base register \(r\in\{0,\ldots,31\}\), with current shadow value \(R[r]\), define:

$$
\Delta_r =
signed32((EA-R[r])\bmod2^{32}).
$$

The viable base-register set is:

$$
V(EA)=
\{r\mid -2048\le\Delta_r\le2047\}.
$$

`x0` is always viable because:

$$
R[x0]=0
$$

and:

$$
0\le EA\le508.
$$

Therefore:

$$
V(EA)\neq\varnothing.
$$

Select:

$$
rs1\sim Uniform(V(EA)).
$$

Then derive:

$$
imm=\Delta_{rs1}.
$$

Thus:

$$
(R[rs1]+imm)\bmod2^{32}=EA.
$$

### LW draw order

```text
EA
rs1 from V(EA)
rd
```

with:

```text
rd ~ Uniform(x1..x31)
```

### SW draw order

```text
EA
rs1 from V(EA)
rs2
```

with:

```text
rs2 ~ Uniform(x0..x31)
```

This policy has no stochastic retry loop and preserves uniform selection of the canonical memory target `EA`.

The state-dependent conditioning of the base register is a legality mechanism only.

It shall not use coverage state.

---

## 14. Bounded control-flow block

M1 control-flow payloads use a fixed self-contained four-word block:

```text
offset 0 : control instruction
offset 1 : structural NOP
offset 2 : structural NOP
offset 3 : architectural redirect target NOP
```

where every structural NOP is:

```text
addi x0, x0, 0
```

The logical redirect displacement is fixed to:

```text
+12 bytes
```

or:

```text
+3 words
```

The physical target is:

$$
T=(PC_{start}+12)\ \&\ 0x1ff.
$$

This may wrap across the physical `508 → 0` boundary while remaining forward in logical program-image order.

Structural NOPs consume no stochastic family RNG or operand RNG.

If structurally accepted by the DUT, however, they are real accepted instructions and therefore count toward the canonical accepted-instruction denominator.

---

## 15. BRANCH realization

For a BRANCH payload:

1. select the branch subtype uniformly;
2. select `rs1` uniformly from `x0..x31`;
3. select `rs2` uniformly from `x0..x31`;
4. encode the branch with displacement `+12`.

The offline shadow model determines takenness from the architectural state.

If predicted taken:

```text
expected executed offsets = (0, 3)
```

If predicted not taken:

```text
expected executed offsets = (0, 1, 2, 3)
```

The generator does not condition operands to force a particular taken/not-taken ratio.

Taken rate is an emergent diagnostic quantity.

A DUT takenness error changes the accepted `(PC,instruction)` sequence and is therefore observable as stream-plan divergence.

---

## 16. JAL realization

For JAL:

```text
rd ~ Uniform(x1..x31)
offset = +12
```

Expected executed offsets are:

```text
(0, 3)
```

The link value remains the architectural:

$$
rd=PC+4
$$

using the DUT/Golden full-width link semantics derived from the zero-extended physical PC.

---

## 17. JALR realization

For JALR:

```text
rd  ~ Uniform(x1..x31)
rs1 ~ Uniform(x0..x31)
```

Let:

$$
T=(PC_{start}+12)\ \&\ 0x1ff.
$$

Let:

$$
v=R[rs1]\ \&\ 0x1ff.
$$

Compute:

$$
d=(T-v)\bmod512.
$$

Choose the canonical signed representative:

$$
imm=
\begin{cases}
d,&d<256\\
d-512,&d\ge256.
\end{cases}
$$

Therefore:

$$
-256\le imm\le255
$$

and the immediate always fits signed 12 bits.

It also guarantees:

$$
(R[rs1]+imm)\ \&\ 0x1ff=T.
$$

Because `T` is word-aligned and `512` is divisible by four, the raw JALR target is word-aligned by construction.

Expected executed offsets are:

```text
(0, 3)
```

---

## 18. Known canonical JALR LSB-clear defect

The baseline DUT does not implement the architectural JALR operation:

$$
target=(rs1+imm)\ \&\ \sim1.
$$

Static RTL inspection and the Week-13 dynamic witness demonstrate:

```text
raw target           = 0x00d
architectural target = 0x00c
observed DUT target  = 0x00d
link value           = 0x00000004
```

This is a known canonical DUT defect.

The comparative stochastic envelope therefore generates only word-aligned raw JALR targets.

This containment avoids intentionally forcing a known terminal stream divergence into the generator-efficiency campaign.

The Golden Model retains the correct architectural `& ~1` rule.

The directed JALR witness remains separate verification evidence.

Generation is constrained; checking is not weakened.

---

## 19. RNG contract

Each M1 run receives exactly one top-level root seed.

Two deterministic subsystem seeds are derived by SHA-256.

For subsystem label `L`:

```text
message =
    "week13.m1-pr.v1|" +
    decimal(root_seed) +
    "|" +
    L
```

encoded as UTF-8.

Then:

```text
digest = SHA256(message)
subsystem_seed =
    unsigned big-endian integer represented by digest[0:8]
```

The frozen labels are:

```text
family
operand
```

The corresponding RNGs are Python:

```text
random.Random(family_seed)
random.Random(operand_seed)
```

No other stochastic source is permitted.

In particular, the implementation shall not use:

* wall-clock time;
* OS entropy;
* Python `hash()`;
* an unseeded secondary RNG.

The exact Python version shall be recorded in run telemetry.

---

## 20. RNG-consumption separation

`family_rng` shall make only payload-family selections.

All operand, subtype, register, address, and immediate selections shall use only `operand_rng`.

Structural NOPs consume neither RNG.

State-dependent legality must not consume additional `family_rng` draws.

Therefore operand-conditioning behavior cannot perturb the future payload-family sequence.

---

## 21. Offline-generation preflight

Before a generated stream is admitted to RTL execution, it shall pass an offline preflight.

The preflight shall verify at minimum:

```text
supported instruction only
GPR-writing stochastic rd != x0
structural x0 writes have zero writeback value
LW/SW EA in {0,4,...,508}
LW/SW immediate fits signed 12 bits
BRANCH/JAL target matches +12 block rule
JALR immediate fits signed 12 bits
JALR raw target is word-aligned
planned executed PCs match shadow execution
planned executed words match shadow execution
control-flow expected offsets match shadow outcome
```

A stream failing generator preflight is an implementation error and shall not be run on the DUT.

This preflight uses no coverage feedback.

---

## 22. Exact accepted-instruction budget

The canonical budget variable is accepted executed-instruction count.

Week-13 Pure-Random pilot budget:

$$
N_{pilot}=10,000
$$

accepted executed instructions per seed.

Final comparative budget remains:

$$
N_{final}=100,000
$$

accepted executed instructions per seed.

Stalls, flush bubbles, unexecuted structural words, and resident future suffixes receive no instruction-budget credit.

The runtime terminates at the exact accepted-instruction prefix.

A partially consumed final stream block or future resident suffix may be discarded at terminal cleanup.

No execution event may be fabricated merely to close a block or checkpoint.

### 22.1 Campaign-wide exact-cut, lifecycle, and measurement contract

The following rules are normative for every Week-13 stochastic method
participating in pilot or comparative measurement:

```text
M1-PR
M2-WR
M3-ACGS
```

They refine the exact-budget, coverage, failure, telemetry, and
performance rules without changing the frozen accepted-instruction
denominator.

#### Common exact accepted-instruction cut

For a configured campaign budget \(N\), successful fixed-budget
termination requires:

$$
accepted = N.
$$

The budget shall not be rounded to:

```text
generator-block boundary
runtime-refill boundary
adaptive-epoch boundary
checkpoint boundary other than the exact accepted prefix
```

Cycles, stalls, flushes, and retired instructions are DUT-dependent
outcomes and shall not define the stimulus budget.

All stochastic methods shall therefore use the same:

```text
exact accepted-instruction cut at N
```

#### Exact kill rather than pipeline drain

The current verification path has free-running instruction fetch while
the DUT clock is active.

Draining the pipeline after accepted instruction \(N\) would therefore
permit additional accepted instructions unless a new fetch-stall
mechanism were introduced.

Introducing such a mechanism would change the frozen timing and
cycle-count semantics.

Week 13 therefore terminates by exact kill after completion of the
post-instruction cut for accepted instruction \(N\).

Operationally:

> after the post-instruction cut for accepted instruction \(N\), no
> further DUT clock transition capable of advancing pipeline state is
> permitted.

Any observation satisfying:

$$
accepted > N
$$

is an infrastructure failure, not experimental DUT data.

#### Authoritative cut-cycle ordering

One campaign-control process shall own all observations and termination
ordering for a cycle.

The logical order is:

```text
FallingEdge + settled observation
    -> C-stage/store observation
    -> retirement observation
    -> functional/performance architectural evidence
    -> pre-rising accepted-instruction snapshot

RisingEdge + settled observation
    -> finalize accepted ExecutionEvent, if any
    -> planned-stream identity check
    -> timing expectation
    -> architectural step
    -> predecessor successor-PC resolution
    -> L1/L2 Intent and realization observers
    -> complete_post_instruction_cut()
    -> checkpoint emission, if applicable
    -> exact-N kill, if accepted == N
    -> otherwise runtime release/refill may proceed
```

A checkpoint is the state produced by this same cut procedure.

The final checkpoint shall not use a separate code path.

For the Week-13 pilot:

$$
N = 10000
$$

with checkpoint interval \(1000\), so the legal checkpoint boundaries
are:

$$
1000,2000,\ldots,10000.
$$

#### Hard-cap infrastructure invariants

The campaign driver shall enforce:

$$
accepted \le N.
$$

When instruction \(N\) is accepted:

```text
kill_cycle == current_cycle
```

After termination:

```text
post_cut_clock_edges == 0
accepted == N
adapter_instruction_count == N
```

Violation of any hard-cap invariant shall be classified:

```text
INFRA_INVALID
```

and shall not be included in experimental inference.

#### Accepted/retired lifecycle conservation

At every stable lifecycle observation point and at every checkpoint:

$$
accepted
=
retired\_checked
+
in\_flight.
$$

The accepted-but-not-retired state shall agree with both streaming
checker queues:

$$
in\_flight
=
functional\_pending
=
performance\_pending.
$$

The retained tail shall remain bounded:

$$
0 \le in\_flight \le D,
$$

where \(D\) is the frozen bounded in-flight/retirement depth supplied
by the verification timing machinery.

These relations are runtime assertions, not reporting-only telemetry.

They test mechanically that an instruction admitted to the accepted
executed stream cannot disappear silently before retirement.

#### Coverage-hit lifecycle conservation

Every registered authoritative coverage hit shall belong to exactly one
of:

```text
validated
rejected
pending
```

and shall satisfy:

$$
registered\_hits
=
validated\_hits
+
rejected\_hits
+
pending\_hits.
$$

Removal of stale architectural-result cache entries is not considered
hit pruning.

For every non-terminal attributable execution prefix:

```text
hit_pruned_mid_run = 0
```

shall hold.

Every pending hit must still depend on evidence belonging to the
unresolved accepted tail:

$$
pending(hit)
\Rightarrow
\exists p \in participants(hit):
retired\_checked < p \le accepted.
$$

A pending hit whose participants have all already retired is an
infrastructure/lifecycle error.

#### Intent attribution boundary

Intent coverage is attributed only to accepted consumers.

Therefore:

$$
max\_intent\_consumer\_id
\le
accepted.
$$

No Intent observation may refer to an instruction outside the current
authoritative accepted prefix.

After a terminal PC/instruction divergence, no subsequent coverage
event may be fabricated.

#### Exact-cut tail

Exact accepted termination may leave a bounded in-flight tail.

A successful fixed-budget run is therefore not required to satisfy:

```text
retired_checked == accepted
functional_pending == 0
performance_pending == 0
```

at the final cut.

The tail shall instead be reported explicitly:

```text
accepted
retired_checked
in_flight_at_cut
functional_pending
performance_pending
L1 pending hits
L2 pending hits
```

Validated coverage contains only evidence that actually exists by the
cut.

No hypothetical pipeline drain shall be used to promote additional
Validated hits.

#### Metric denominators

Every reported rate shall expose its denominator explicitly.

The normative denominators are:

```text
budget denominator      = accepted
coverage denominator    = accepted
functional denominator  = retired_checked
performance denominator = retired_checked
```

Therefore:

$$
functional\ pass\ rate
=
\frac{functional\ passed}{retired\_checked}
$$

and similarly for performance results.

Cycles-to-\(N\), stalls-to-\(N\), flushes-to-\(N\), and wall time
to \(N\) are outcomes of the fixed accepted-instruction experiment.

#### Global final-state comparison

Week-13 pilot v1 shall not compare the complete final DUT RF/DMEM state
at exact accepted cut against a Golden state in which all \(N\)
accepted instructions have been retired.

Such a comparison would confound the bounded unretired tail with a DUT
functional mismatch.

Functional correctness in pilot v1 is evaluated per instruction using
only architectural evidence that exists by the exact cut.

A future global final-state comparison requires a separately specified
checked-prefix snapshot contract.

#### Failure taxonomy

Every run shall terminate in exactly one of:

```text
COMPLETED
VALID_DUT_FAILURE_NONTERMINAL
VALID_DUT_FAILURE_TERMINAL
INFRA_INVALID
```

`VALID_DUT_FAILURE_NONTERMINAL` denotes an attributable checker failure
for which the accepted PC/instruction stream remains attributable.

Its first failure is recorded and execution continues to the exact
accepted budget.

`VALID_DUT_FAILURE_TERMINAL` denotes the first accepted PC/instruction
divergence after which execution is no longer attributable.

The run stops at that prefix and no suffix is fabricated.

`INFRA_INVALID` includes, at minimum:

```text
accepted > N
post-cut clock edge
checkpoint-ordering violation
lifecycle-conservation violation
runtime/timing ownership corruption
deterministic-initialization failure
protocol/provenance mismatch
```

Infrastructure-invalid runs are not DUT experimental observations.

A terminal-DUT prefix remains diagnostic evidence but is excluded from
fixed-budget AUC, throughput, and ordinary fixed-\(N\) inference.

#### Common campaign cut driver

`M1-PR`, `M2-WR`, and `M3-ACGS` shall use one common implementation for:

```text
exact-N termination
checker lifecycle
coverage checkpointing
lifecycle invariants
failure classification
measurement cut
```

parameterized only by method, seed, accepted budget, and
method-specific stream policy.

Method-specific generators shall not define independent cut semantics.

This makes denominator equality and exact-cut fairness an implementation
property rather than a reporting convention.

---

## 23. Coverage attribution

Coverage authority remains the accepted DUT execution stream.

Emitted but unaccepted instructions receive no Intent or Validated credit.

For each accepted instruction:

* Intent attribution follows the frozen coverage semantics;
* Validated promotion requires the frozen realization/checker contract.

Structural NOPs count as accepted instructions if actually accepted, but they do not receive artificial positive RAW credit.

Coverage checkpoints remain every:

```text
1,000 accepted executed instructions
```

where applicable.

---

## 24. Non-terminal DUT checker failure

If a checker reports a DUT failure while accepted `(PC,instruction)` order remains attributable to the frozen plan:

* record the failure;
* retain first-failure evidence;
* continue the run;
* continue Intent accounting;
* apply normal Validated rejection semantics;
* continue to the exact fixed budget.

A DUT mismatch is not a technical-invalid run.

---

## 25. Terminal execution divergence

A terminal execution divergence occurs when accepted execution can no longer be deterministically attributed to the frozen generated plan, including at minimum:

```text
observed accepted PC != planned accepted PC
observed accepted instruction != planned accepted instruction
```

At the first such divergence:

```text
run_status = VALID_DUT_FAILURE_TERMINAL
```

The run shall:

* stop at the first un-attributable divergence;
* preserve all valid prefix evidence;
* preserve first-failure evidence;
* preserve generated-plan and telemetry artifacts;
* not fabricate any post-divergence instruction;
* not receive a replacement seed;
* not be reclassified as infrastructure-invalid.

The incomplete prefix shall **not** be reported as if it contained fixed-budget:

```text
bins@N
AUC@N
throughput@N
```

for the prescribed `N`.

Terminal DUT divergence is not ordinary `n@95` censoring.

---

## 26. Effect of terminal divergence on pilot and final inference

### Pilot

A terminal DUT divergence invalidates use of that run for pilot metric comparison but does not invalidate the DUT-failure evidence.

The affected pilot selection or benchmark gate shall stop for investigation.

No replacement seed or success-only selection is permitted.

### Final comparative campaign

If a required final run terminates by DUT execution divergence, the preregistered complete:

```text
n = 15 runs/method
```

fixed-budget confirmatory dataset cannot be claimed complete for that DUT revision.

The failure remains verification evidence.

Confirmatory comparison may resume only through an explicitly versioned protocol/DUT revision decision rather than silently replacing or deleting the failed observation.

---

## 27. M1 Pure-Random Week-13 pilot seeds

The Week-13 M1 performance-pilot roots are frozen as:

```text
11001
11002
11003
```

These seeds are:

* pilot-only;
* excluded from final comparative inference;
* disjoint from M1 final seeds `1001..1015`;
* disjoint from M2 final seeds `2001..2015`;
* disjoint from M3 final seeds `3001..3015`;
* disjoint from the authoritative Adaptive-CGS pilot seed namespace.

The three M1 pilot seeds shall not be replaced because of unfavorable performance, coverage, or DUT behavior.

---

## 28. Adaptive-CGS pilot independence

This addendum does not alter:

* Adaptive candidate space;
* Adaptive root-pilot seeds;
* epsilon/alpha/batch candidates;
* L2 Intent reward;
* normalized-AUC selection criterion;
* practical-tie rule;
* deterministic tie-resolution order.

Pure-Random pilot observations shall not be used to modify Adaptive-CGS hyperparameters.

Adaptive pilot observations shall not be used to modify M1-PR generator semantics.

---

## 29. Required M1 run telemetry

Every M1 run shall record at minimum:

```text
schema version
method = M1-PR
pilot/final phase
root seed
family subsystem seed
operand subsystem seed
DUT revision
generator revision
configuration/addendum revision
simulator version
Python version
timestamp

run status
accepted instruction count
retired-checked instruction count
in-flight instruction count at cut
cycle count
stall count
flush count
cut cycle
kill cycle
post-cut clock-edge count

functional checked count
functional passed count
functional failed count
functional pending count
performance checked count
performance passed count
performance failed count
performance pending count
performance total excess cycles

payload-family draw counts
branch-subtype counts
branch taken count
branch not-taken count
structural-NOP accepted count

LW EA histogram or equivalent summary
SW EA histogram or equivalent summary
memory viable-base-set size diagnostics
accepted base-register histogram

checker mismatch count
first failure
terminal-divergence status

L1 Intent
L1 Validated
L1 registered-hit count
L1 validated-hit count
L1 rejected-hit count
L1 pending-hit count
L2 Intent
L2 Validated
L2 registered-hit count
L2 validated-hit count
L2 rejected-hit count
L2 pending-hit count
maximum Intent consumer instruction ID
mid-run hit-prune count
checkpoint trajectory
checkpoint count

budget denominator = accepted
coverage denominator = accepted
functional denominator = retired_checked
performance denominator = retired_checked

wall-clock time
accepted instructions/second
cycles/second
peak RSS

generated-plan immutable hash
```

Diagnostic distributions are reportable but shall not be used as post-pilot tuning signals.

---

## 30. Performance-measurement scope

Full-system performance measurements include:

```text
generator
RTL simulation
architectural checker
FunctionalScoreboard
PerformanceMonitor
coverage
telemetry
```

Waveform tracing is disabled for performance measurements.

Waveforms are diagnostic-only unless a separate run explicitly records otherwise.

The authoritative full-system measurement window begins immediately
before stochastic campaign-plan generation for the measured seed and
ends only after:

```text
accepted instruction N
-> all same-cycle checker/coverage observers
-> complete_post_instruction_cut(N)
-> final checkpoint emission
-> exact clock kill
-> final measurement snapshot
```

have completed.

Compilation, RTL elaboration/build caching, shell startup, and
post-run report formatting are outside the measured window.

The same wall-clock denominator shall be used for the official:

```text
accepted instructions/second
cycles/second
```

metrics.

A simulator-only or RTL-loop-only wall time may be recorded as
diagnostic telemetry, but it shall not replace the full-system
Week-13 benchmark quantity.

Peak RSS shall cover the same measured campaign process and shall not
be inferred from a single end-of-run current-RSS sample.

Required Week-13 performance quantities include:

```text
wall-clock time
accepted instructions/second
cycles/second
peak RSS
accepted instructions
retired-checked instructions
in-flight instructions at cut
cycles
stalls
flushes
functional pass/fail counts over retired_checked
performance pass/fail counts over retired_checked
coverage bookkeeping over accepted
```

---

## 31. Allowed post-freeze implementation changes

After this addendum is frozen, a change is permitted without redefining the experiment only if it is demonstrably infrastructure-only and preserves:

$$
(seed,spec)\rightarrow generated\ plan.
$$

Examples may include:

* crash fixes;
* path-resolution fixes;
* telemetry-output fixes.

Such a change requires:

```text
diff review
affected-seed rerun
old failed attempt retained
generated-plan hash comparison where applicable
```

The following may not change after pilot observations without explicitly reopening and versioning this protocol:

```text
family universe
family probabilities
register domains
memory target domain
memory conditioning semantics
control-block structure
control displacement
JALR alignment containment
RNG algorithm
seed derivation
draw ownership/order
pilot seeds
accepted-instruction budget
coverage denominator
terminal-divergence semantics
```

If one of these must change, create a dated successor addendum and rerun all affected pilot data.

Old and new pilot results shall not be mixed.

---

## 32. Known-defect containment does not weaken verification

The stochastic envelope intentionally avoids two already demonstrated canonical DUT defects:

```text
harmful rd=x0 write behavior
odd-raw-target JALR LSB-clear behavior
```

This containment exists to preserve comparative measurement validity.

It does not declare those behaviors correct.

They remain independently represented by directed/mutation evidence.

Any different defect arising inside the frozen stochastic envelope remains eligible for checker detection and shall be retained as experimental evidence.

---

## 33. Computational complexity

For \(N\) accepted instructions, stochastic payload construction and architectural shadow execution are linear in campaign size.

Expected generation complexity is:

$$
O(N).
$$

The register legality calculation for each LW/SW examines at most 32 registers:

$$
O(32)=O(1)
$$

per memory instruction.

Therefore total generation remains:

$$
O(N).
$$

Architectural GPR state is constant-size.

DMEM state is bounded by the canonical 512-byte campaign envelope.

If the complete generated plan is retained for reproducibility, plan storage is:

$$
O(N).
$$

The dominant Week-13 runtime cost is expected to remain RTL simulation rather than generator computation.

---

## 34. Pre-pilot gate

M1-PR pilot execution is prohibited until all of the following pass:

```text
[ ] this addendum is committed
[ ] repository working tree is clean
[ ] M1 RNG known-answer tests pass
[ ] same seed produces identical generated plan
[ ] different root seed may alter the plan
[ ] generated-plan hash is stable
[ ] no stochastic payload writes rd=x0
[ ] structural NOP writeback to x0 is zero
[ ] LW/SW addresses are aligned and within 0..508
[ ] memory viable-source set is never empty
[ ] JALR raw targets are word-aligned
[ ] control-plan preflight passes
[ ] Golden replay matches planned execution
[ ] exact accepted-prefix termination is tested
[ ] accepted count never exceeds the configured hard cap
[ ] no DUT clock edge occurs after the exact-N cut
[ ] final checkpoint uses the same post-instruction-cut path as intermediate checkpoints
[ ] accepted = retired_checked + in_flight is asserted
[ ] in_flight = functional_pending = performance_pending is asserted
[ ] in-flight state remains bounded by the frozen pipeline/timing depth
[ ] coverage-hit lifecycle conservation is asserted
[ ] no unresolved hit is pruned mid-run
[ ] every pending hit references the unresolved accepted tail
[ ] maximum Intent consumer instruction ID never exceeds accepted count
[ ] deterministic zero DMEM initialization is verified
[ ] terminal-divergence handling is tested
[ ] M1-PR uses the common campaign cut/checkpoint driver required for M1/M2/M3
[ ] required telemetry denominators and measurement window match Sections 22.1 and 30
[ ] historical frozen regressions remain passing
```

---

## 35. Freeze statement

Once this document is committed, all M1-PR choices above are frozen before Week-13 pilot observations.

Pilot measurements may reveal:

* runtime cost;
* coverage trajectory;
* branch taken rate;
* operand distributions;
* viable-register-set distributions;
* DUT failures.

Those observations are evidence and diagnostics.

They shall not be used to alter the frozen M1 generator envelope unless the protocol is explicitly reopened, versioned, and all affected pilot observations are rerun.

**Status after commit: FROZEN FOR WEEK-13 IMPLEMENTATION.**
