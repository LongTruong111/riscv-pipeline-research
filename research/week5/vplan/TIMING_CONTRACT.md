# T5 Timing Contract

## 1. Purpose

This document freezes the simulation-timing contract inherited from
Week 4 for all subsequent T5 verification infrastructure.

Primary evidence:

- timing characterization commit:
  `77fc28e9f4a95e1f7b4f27a402d7e29af487dba5`
- completed GĐ1 lineage:
  `GATE_GD1_COMPLETE`
- `research/week4/TIMING_RULES.md`
- `research/week4/race_demonstration.md`
- `tests/timing_utils.py`

All referenced Week-4 timing artifacts are present in the current
T5 branch lineage.

The Week-4 timing experiment was performed on an independent
synchronous probe DUT in order to isolate Cocotb scheduler behavior
from the RISC-V microarchitecture.

The Week-4 timing characterization commit descends from the frozen DUT
baseline `DUT_BASELINE_T3`.

No modifications to the frozen `design/` or DUT-related `verif/`
boundary exist between `DUT_BASELINE_T3` and the Week-4 timing
characterization commit.

---

## 2. TR1 — Functional Stimulus Drive

Normal synchronous functional stimulus shall be driven at:

`FallingEdge(clk)`

before the next DUT active sampling edge:

`RisingEdge(clk)`.

Verification code shall not normally drive functional DUT inputs at
the same `RisingEdge(clk)` at which sequential RTL samples them.

Reason:

Same-active-edge driving introduces scheduler-order dependence and is
therefore treated as racy behavior.

Status:

**FROZEN**

---

## 3. TR2 — Sequential Observation

Sequential DUT state shall be observed using:

~~~python
await RisingEdge(clk)
await ReadOnly()
~~~

`RisingEdge(clk)` alone is not considered a settled monitor or
scoreboard observation point.

Week-4 evidence showed:

~~~text
immediate after RisingEdge = old value
after ReadOnly             = updated value
~~~

on both:

- Icarus Verilog 11.0
- Verilator 5.034

This is the canonical sampling phase for:

- monitor observation;
- scoreboard comparison;
- sequential-state coverage collection.

Status:

**FROZEN**

---

## 4. TR3 — Reset Timing

Reset shall remain asserted for at least three complete clock cycles
during verification-environment initialization unless a test has an
explicit reason to use a different reset duration.

Reset deassertion shall occur at:

`FallingEdge(clk)`

so that the deasserted reset value is stable before the following
active `RisingEdge(clk)`.

### Reset-polarity distinction

The Week-4 scheduler probe used an active-low signal named `rst_n`.

The frozen RISC-V DUT uses its own DUT-specific reset semantics.

Therefore T5 inherits the timing rule:

- assert reset for the required interval;
- change/deassert reset away from the active sampling edge;

but does not infer DUT reset polarity from the Week-4 probe helper.

Status:

**FROZEN**

---

## 5. TR4 — Clock Ownership

Each simulated clock shall have exactly one clock generator.

Concurrent verification processes shall not independently drive the
same clock signal.

Status:

**FROZEN**

---

## 6. TR5 — Same-Timestamp Feedback

A verification component shall not:

1. observe a DUT result; and
2. drive a dependent functional input

within the same simulation timestamp during normal verification.

Such same-timestamp feedback is permitted only in a test explicitly
designed to characterize scheduler behavior.

This rule is particularly important for later feedback-driven CGS.

The CGS loop must therefore separate:

`observation -> decision -> later drive event`

rather than forming a zero-time feedback path.

Status:

**FROZEN**

---

## 7. TR6 — Shared Timing Infrastructure

Clock generation, reset sequencing, functional input drive, and
settled sampling shall use common timing helpers rather than duplicate
ad-hoc timing behavior across tests.

Canonical semantic operations are:

~~~text
drive:
    FallingEdge(clk)
    -> assign functional input

sample:
    RisingEdge(clk)
    -> ReadOnly()
    -> observe DUT state
~~~

If the helper implementation is moved or rewritten later, these
semantics must remain unchanged unless the timing contract is formally
revised.

Status:

**FROZEN**

---

## 8. Coverage Sampling Rule

A hazard coverage event may be recorded only after the associated DUT
state has reached the settled observation phase:

~~~python
await RisingEdge(clk)
await ReadOnly()
~~~

A transient combinational value observed before `ReadOnly()` shall not
be counted as a coverage hit.

The collector must additionally apply the validity/bubble semantics
defined in:

`research/week5/vplan/HAZARD_SIGNAL_MAP.md`

Therefore:

`signal match != automatically a valid hazard event`.

A coverage hit requires both:

1. a settled observation point; and
2. a functionally valid producer/consumer event.

Status:

**FROZEN**

---

## 9. Scoreboard Timing Rule

The scoreboard shall compare architectural expected state only after
the DUT state relevant to that comparison is settled.

For sequential state:

~~~python
await RisingEdge(clk)
await ReadOnly()
~~~

is the minimum observation boundary.

The scoreboard is the correctness oracle.

Coverage state must not be used as a substitute correctness oracle.

Status:

**FROZEN**

---

## 10. Portability Boundary

The Week-4 same-RisingEdge experiment happened to produce the same
result on Icarus Verilog 11.0 and Verilator 5.034.

That agreement is only an experimental observation.

It is not treated as a simulator-independent guarantee.

The T5 verification environment intentionally avoids depending on
same-active-edge scheduling order.

---

## 11. T5 Timing Summary

| Operation | Required phase |
|---|---|
| Functional input drive | `FallingEdge(clk)` |
| DUT sequential sampling | `RisingEdge(clk)` |
| Monitor observation | `RisingEdge -> ReadOnly` |
| Scoreboard observation | `RisingEdge -> ReadOnly` |
| Coverage sampling | `RisingEdge -> ReadOnly` plus valid-event qualification |
| Reset deassertion | `FallingEdge(clk)` |
| Same-edge functional drive | Forbidden in normal verification |
| Zero-time feedback | Forbidden in normal verification |

T5 Timing Contract:

**PASS / FROZEN**
