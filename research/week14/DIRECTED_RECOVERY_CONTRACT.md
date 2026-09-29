# Week 14 Directed Recovery Contract

## Purpose

The original Week-14 Directed preregistration was falsified.

That result is preserved and remains FAIL.

This document defines a separate prospective confirmation contract after
the post-falsification erratum. It does not rewrite the original
preregistration and must not be described as preregistered before the
first Directed run.

---

## Historical chain

Gate T13:

`ff6e2cf...`

Original Week-14 preregistration:

`8a30675...`

Final Directed harness:

`183803b...`

Original final Directed Attempt 1:

`FAIL`

Post-falsification erratum:

`059b931...`

The recovery confirmation occurs only after this contract is committed.

---

## Corrected frozen-DUT defect interpretation

The canonical Directed suite activates two known frozen-DUT defects.

### T18 / H18

Root cause:

`REGFILE_X0_WRITE`

Correct behavior remains:

`x0 = 0`

Observed frozen-DUT defect signature:

`x0 = 7`

Control behavior must otherwise remain correct.

This is an architectural rejection.

### T19 / H19

Root cause:

`LOAD_RD_X0_FALSE_STALL`

Correct behavior remains:

`stall_cycles = 0`

The frozen DUT instead produces:

`stall_cycles = 1`

The T19 stream generates both H18 and H19 Intent observations for the
same consumer. Both control realizations are rejected by the same false
stall.

The H18 and H19 rejection records in T19 are therefore correlated
evidence of one root cause, not two independent DUT defects.

This is a control rejection.

---

## Required successful cases

All canonical cases except T18 and T19 must become Validated:

T01-T17 and T20.

In particular:

- T11 must validate;
- T13 must validate;
- T20 must validate.

---

## Directed confirmation target

The confirmation run must produce:

- designated Intent: 20/20;
- attribution exercised: 20/20;
- control/timing oracle exercised: 20/20;
- architectural/value oracle exercised: 20/20;
- Validated: 18/20;
- T18 rejected only by its registered-x0 architectural defect signature;
- T19 rejected only by its load-rd-x0 false-stall root cause;
- no unexpected root cause;
- no missing known root cause.

Normative expectations are not changed to defective DUT behavior.

For example, T19 still has an expected correct stall count of zero.
The observed one-cycle stall is stored separately as the known defect
signature.

---

## Status semantics

The original preregistered Directed attempt remains:

`FAIL`

A successful recovery confirmation is labeled:

`PASS_POST_ERRATUM_CONFIRMATION`

It is not labeled as the original preregistered PASS.

If the Directed recovery confirmation and every other Gate-T14
obligation pass, the strongest allowed final Week-14 gate label is:

`RECOVERED_WITH_ERRATUM`

A plain `PASS` label is prohibited because it would erase the
preregistration falsification.
