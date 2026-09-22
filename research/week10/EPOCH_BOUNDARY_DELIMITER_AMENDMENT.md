# Week10 Epoch-Boundary Delimiter Amendment

## 1. Status

This document is an additive Week10 implementation/protocol amendment.

It does not modify frozen Week5 artifacts.

The amendment is introduced before the Gate-T10 5000-executed-instruction
engineering run, before the preregistered pilot, and before final M1/M2/M3
campaign execution.

The amendment is motivated solely by a demonstrated implementation-level
causality constraint in the frozen DUT pipeline. It is not selected from
coverage-performance results and does not alter the frozen arm set,
epsilon, alpha, Q-floor rule, register-targeting rule, attribution rule,
or final seed protocol.

Where this document explicitly addresses epoch-boundary synchronization
and its accounting, it is authoritative for Week10 adaptive execution.

---

## 2. Observed Causality Constraint

The frozen instruction-memory path is:

```text
CPU FallingEdge
    -> synchronous IMEM read using current PC

CPU RisingEdge
    -> fetched word enters IF/ID A
    -> current IF/ID instruction enters ID/EX B
    -> PC advances
```

The final `ExecutionEvent` of an adaptive epoch becomes available only
after the RisingEdge that admits the final payload instruction into
ID/EX.

At that same RisingEdge, IF/ID has already latched the instruction at
the next sequential PC.

Therefore:

```text
fetch(next sequential word)
    precedes
reward/Q update
    precedes
next-arm selection
```

A runtime patch performed after the final epoch event is consequently
too late to change the already-latched next IF/ID instruction.

The measured failing boundary was:

```text
IF/ID PC             = 0x068
IF/ID word           = 0x00000000
patched IMEM[0x068]  = 0x00002f83
IF/ID after patch    = 0x00000000

timing expected PC   = 0x068
next accepted PC     = 0x06c
```

This establishes a one-instruction lookahead causality requirement.

---

## 3. Epoch-Boundary Delimiter

A deterministic epoch-boundary delimiter (EBD) is introduced.

The frozen EBD instruction is:

```asm
bne x0, x0, +4
```

Encoding:

```text
0x00001263
```

Properties required of the EBD:

- ISA-legal in the frozen supported subset;
- deterministic;
- no GPR write;
- no memory write;
- no positive-register source;
- no positive L2 RAW dependency;
- no control-flow redirect;
- no hidden adaptive decision;
- no RNG consumption;
- no selected-arm attribution.

For the frozen DUT:

```text
rs1 = x0
rs2 = x0

BNE condition:
x0 != x0 -> false

PcSel = 0
```

Therefore the architectural successor is the sequential `PC + 4`.

---

## 4. H18 / Negative-Coverage Safety

The EBD architecturally reads x0.

H18 requires the immediately preceding executed instruction to be a
producer whose encoded destination is x0.

The frozen A0-A9 realizations satisfy:

```text
if the final executed template instruction writes a GPR:
    rd is in x1..x31
```

A8 ends in STORE and does not write a GPR.

Frozen campaign filler also writes only a positive auxiliary register.

Therefore an ordinary complete adaptive epoch payload cannot end with
a producer whose destination is x0.

The EBD consequently does not intentionally create H18 at an epoch
boundary under the frozen template/filler policy.

Any violation of this predecessor invariant is a fail-fast condition.

---

## 5. Logical Epoch Ownership

Each adaptive feedback epoch owns exactly one EBD.

The logical executed order for epoch `t` is:

```text
EBD_t
payload_t
```

where `payload_t` consists only of:

```text
selected-arm complete template instances
+
deterministic campaign background fillers
```

For `t > 0`, `EBD_t` is physically pre-seeded before the previous epoch
finishes so that it is already available to the DUT one-instruction
lookahead.

`EBD_0` is pre-seeded before initial execution.

The EBD is logically owned by the epoch in which it executes, not by
the epoch whose physical image preparation placed it in memory.

---

## 6. Executed-Instruction Accounting

The EBD is a real architecturally executed instruction.

It MUST therefore count toward all campaign quantities defined over
executed instructions.

For epoch `t`:

```text
DeltaN_t =
    1 EBD
    + actual executed adaptive payload instructions
```

The adaptive reward remains:

```text
R_t =
    1000
    * DeltaNewAttributedL2IntentBins_t
    / DeltaN_t
```

The EBD contributes zero attributable reward.

It counts toward:

- executed-instruction numbering;
- reward denominator;
- nominal batch accounting;
- 1000-executed-instruction checkpoints;
- engineering dry-run instruction budget;
- pilot/final Nmax;
- timing/architectural executed order.

It MUST NOT be silently removed from any executed-instruction metric.

---

## 7. Batch Boundary

For nominal batch threshold `b`, exactly one EBD is already part of the
epoch executed count.

The selected arm therefore generates complete template instances until:

```text
1 + planned_payload_executed >= b
```

A complete template instance is never split merely to hit `b`.

Thus:

```text
DeltaN_actual >= b
```

subject to normal complete-template overshoot and final-run truncation
rules.

The EBD itself is never split or omitted from a started epoch.

---

## 8. 80:20 Payload Composition

The frozen deterministic 80:20 scheduler remains unchanged.

It continues to operate on adaptive payload image words:

```text
4 targeted-template image words
:
1 campaign background filler
```

The EBD is a separate deterministic synchronization class.

It is:

- not a targeted-template instruction;
- not a campaign filler;
- not a structural template instruction;
- excluded from the cumulative `T` used by the 4:1 filler scheduler.

Therefore the frozen 80:20 rule is interpreted as:

```text
80:20 adaptive-payload composition
```

and the EBD count is reported separately.

No EBD insertion may consume RNG state or alter filler-scheduler state.

---

## 9. Coverage Semantics

The EBD remains present in architecturally executed order.

It is processed by the normal execution monitor and architectural/timing
models.

It receives no selected-arm attribution.

Because it is an executed instruction, it may increase executed-order
distance between incidental dependencies spanning an epoch boundary.

This is an explicit fixed synchronization effect.

The EBD MUST NOT be removed from executed history merely to preserve an
incidental cross-epoch dependency distance.

Intended dependencies inside an adaptive template remain unchanged
because the EBD is placed outside complete template instances.

---

## 10. Runtime Boundary Protocol

For transition from epoch `t` to epoch `t+1`:

```text
1. payload_t executes.

2. EBD_(t+1) is already present at the next sequential word.

3. Final payload_t RisingEdge:
       final payload instruction enters ID/EX;
       EBD_(t+1) enters IF/ID.

4. Final payload event is finalized.

5. Sole CPU clock task is killed while clk is HIGH.

6. No DUT clock edge occurs during adaptation.

7. Epoch t reward is finalized.

8. Q for the selected arm is updated.

9. Epoch t+1 decision and uncovered-first target are selected from the
   retained post-epoch-t state.

10. payload_(t+1) is generated and patched beginning at:
        EBD_PC + 4

11. Mutable timing/program state is extended consistently.

12. Clock restarts from HIGH toward FallingEdge.

13. FallingEdge fetches the first payload_(t+1) word.

14. Next RisingEdge:
        EBD_(t+1) enters ID/EX;
        first payload_(t+1) word enters IF/ID.

15. Continuous architectural/timing/coverage execution resumes.
```

No DUT reset occurs at an ordinary epoch boundary.

---

## 11. Fail-Fast Conditions

The adaptive campaign MUST halt rather than silently compensate if any
of the following occurs:

- predicted EBD PC differs from the actual boundary PC;
- EBD instruction word differs from `0x00001263`;
- EBD is missing from IF/ID at the expected boundary;
- EBD experiences an unexpected stall;
- EBD causes `PcSel != 0`;
- EBD is not accepted into ID/EX exactly once;
- sequential payload successor is not `EBD_PC + 4`;
- predecessor unexpectedly writes x0;
- EBD causes an unexpected H18/H19/H20 scenario;
- accepted executed order diverges from the planned stream;
- EBD accounting diverges between planner, accepted tracker, reward,
  checkpoint, or Nmax counters;
- more than one clock owner exists;
- reset is asserted at an ordinary epoch transition.

No oracle skip, instruction-index reset, coverage reset, or hidden
boundary correction is permitted.

---

## 12. Evidence Required Before Campaign Use

The following gates are mandatory:

1. static ISA/decode/model proof;
2. static frozen-RTL BNE/PcSel proof;
3. static A0-A9 predecessor/x0 proof;
4. standalone RTL EBD micro-gate;
5. pure-Python EBD accounting tests;
6. multi-epoch RTL continuity gate;
7. one-epoch RTL regression;
8. complete Week10 unit regression;
9. frozen Week5-Week8 diff gate.

The standalone RTL proof must establish:

```text
ordinary predecessor
-> BNE x0,x0,+4
-> sequential sentinel
```

with:

```text
stall = 0
PcSel = 0
no reset
no missing event
no duplicate event
sequential PC continuity
```

---

## 13. Current Verification Evidence

The standalone EBD RTL micro-gate passed with:

```text
TESTS = 1
PASS  = 1
FAIL  = 0
```

The proof dynamically established that:

- `BNE x0,x0,+4` reaches IF/ID;
- it is admitted into ID/EX unchanged;
- it does not assert `PcSel`;
- the sequential sentinel follows at `PC + 4`;
- no reset, missing instruction, duplicate instruction, or redirect is
  required.

---

## 14. Complexity and Overhead

The EBD adds exactly one executed synchronization instruction per
feedback epoch.

For an epoch of approximately `b` executed instructions, its fractional
instruction overhead is:

```text
O(1 / b)
```

Approximately:

```text
b = 500   -> <= ~0.20%
b = 1000  -> <= ~0.10%
b = 2000  -> <= ~0.05%
```

The insertion and accounting cost is O(1) per epoch.

It does not alter the asymptotic complexity of arm selection, register
targeting, provenance lookup, coverage collection, or reward update.

---

## 15. Known Limitation

This amendment solves the one-instruction epoch-boundary lookahead
problem only.

It does NOT establish correctness for adaptive execution across the
9-bit / 128-word IMEM wrap boundary.

Wrap-aware planner, architectural-PC, timing-oracle, and accepted-stream
semantics remain a separate mandatory gate before the 5000-instruction
engineering campaign.
