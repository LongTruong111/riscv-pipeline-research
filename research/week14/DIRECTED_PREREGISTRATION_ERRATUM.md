# Week 14 Directed Preregistration Erratum

## Status

This is a post-falsification erratum.

It does not rewrite or replace the original preregistration commit.

Original preregistration:

`8a3067599fce0643d815bcfc5f9794f06381985c`

Final Directed harness:

`183803b73c64085e3e4f675fc99cf3e4af76cea7`

The first final Directed run is preserved unchanged under:

`research/week14/results/attempt1_preregistered/`

---

## Original prediction

Before the final RTL run, the Week-14 analysis predicted exactly one
known rejection:

`T18 / H18 / REGFILE_X0_WRITE`

T19 was predicted to validate.

That prediction was falsified.

The first final run therefore remains a Gate-T14 FAIL under the original
contract.

---

## Attempt-1 observation

The first run produced:

- L1 Intent: 20/20
- L1 Validated: 18/20
- T18/H18: rejected as preregistered
- T19/H18: rejected
- T19/H19: rejected
- T20/H20: validated

All required oracle categories and attribution paths were exercised.

T19 had no architectural failure. Its rejection was caused by one
unexpected stall cycle.

---

## Root-cause correction

The pre-run analysis incorrectly treated the Week-13 hazard fix as
closing both H19 and H20.

Static inspection of the frozen Gate-T13 RTL shows otherwise.

The frozen `HazardDetection.sv` now qualifies comparisons by whether the
consumer architecturally uses rs1 or rs2. This closes the H20
raw-unused-rs2 false-hazard class.

However, its stall expression still does not exclude a load destination
of x0.

Therefore:

`LOAD rd=x0`

followed by an instruction reading x0 still causes a false load-use
stall.

This is the H19 defect.

A clean rebuild after deleting the Week-5 Verilator simulator cache
reproduced T19 with one stall while T20 validated with zero stalls.

The observation is therefore not attributable to stale simulator state.

---

## Correct frozen-DUT interpretation

The Gate-T13 DUT retains three relevant defect classes:

1. writable physical RegFile entry x0;
2. false load-use hazard when the load destination is x0;
3. JALR target bit 0 is not cleared.

Within canonical T01-T20:

- T18 activates defect 1;
- T19 activates defect 2;
- the JALR defect is not activated.

T19 also produces an incidental H18 Intent hit. H18 and H19 are both
rejected in that case because the same false stall violates the control
contract for the same consumer. They are correlated observations of one
root cause, not two independent DUT defects.

---

## Methodological treatment

The original preregistration is immutable.

Attempt 1 remains FAIL under that preregistration.

This erratum may be used for subsequent technical reporting and
confirmation runs, but it must not be described as having been
preregistered before Attempt 1.

No DUT, Week-5 verification logic, fixture, or Gate-T13 evidence is
changed by this erratum.
