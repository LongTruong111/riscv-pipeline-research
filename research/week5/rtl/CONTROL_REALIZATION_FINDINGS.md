# Week 5 L1 Realization and Validated-Coverage Findings

## Scope

This artifact records live RTL evidence from the canonical T01-T20
directed L1 regression.

The verification flow deliberately separates:

1. Intent Coverage
2. Control Realization
3. Architectural Realization
4. Validated Coverage

A directed test may therefore PASS Intent reachability while its
canonical target bin is rejected from Validated Coverage.

---

## Validation Contract

For one concrete L1 Intent hit:

`ValidatedHit = IntentHit AND ControlValid AND ArchitecturalValid`

Promotion is performed per hit rather than globally per simulation.

A failed hit does not permanently invalidate a bin. A later independent
hit may still promote that bin if all required realization checks pass.

Canonical T01-T20 aggregation uses the configured target bin of each
directed case. Incidental bins observed in the same run are not counted
as additional canonical targets.

---

## Canonical Regression Summary

Simulator: Verilator

Canonical targets:

- Intent run: 20
- Intent pass: 20
- Intent fail: 0
- Intent Coverage: 20/20 = 100.0%

Validated targets:

- Validated pass: 15
- Validated rejected: 5
- Validated unknown: 0
- Validated Coverage: 15/20 = 75.0%

Canonical unvalidated bins:

- H11
- H13
- H18
- H19
- H20

All canonical cases completed with `validation_pending=0`.

---

## Canonical Result Matrix

| Bin | Intent | Control | Architectural | Validated | Primary evidence |
|---|---|---|---|---|---|
| H01 | PASS | PASS | PASS | PASS | canonical forwarding realization |
| H02 | PASS | PASS | PASS | PASS | canonical forwarding realization |
| H03 | PASS | PASS | PASS | PASS | canonical forwarding realization |
| H04 | PASS | PASS | PASS | PASS | canonical forwarding realization |
| H05 | PASS | PASS | PASS | PASS | RF-boundary realization |
| H06 | PASS | PASS | PASS | PASS | exactly one load-use stall |
| H07 | PASS | PASS | PASS | PASS | exactly one load-use stall |
| H08 | PASS | PASS | PASS | PASS | d2 load forwarding |
| H09 | PASS | PASS | PASS | PASS | d2 load forwarding |
| H10 | PASS | PASS | PASS | PASS | dual-source d1+d2 forwarding |
| H11 | PASS | PASS | FAIL | REJECTED | consumer writeback mismatch |
| H12 | PASS | PASS | PASS | PASS | d2 LUI realization |
| H13 | PASS | PASS | FAIL | REJECTED | consumer writeback mismatch |
| H14 | PASS | PASS | PASS | PASS | d2 AUIPC realization |
| H15 | PASS | PASS | PASS | PASS | redirect/link realization |
| H16 | PASS | PASS | PASS | PASS | store-data realization |
| H17 | PASS | PASS | PASS | PASS | newest-writer priority |
| H18 | PASS | PASS | FAIL | REJECTED | architectural x0 corruption |
| H19 | PASS | FAIL | PASS | REJECTED | false load-use stall on rd=x0 |
| H20 | PASS | FAIL | PASS | REJECTED | false stall on unused raw rs2 field |

---

## H11 — LUI d1 Forwarding Value Defect

Canonical control realization passed.

The forwarding selector selected the expected EX/MEM path, but the
architectural consumer result was incorrect.

Observed live evidence:

- consumer instruction index: 2
- expected writeback: `0x12345001`
- observed writeback: `0x00000002`

Result:

- IntentHit(H11) = PASS
- ControlRealization(H11) = PASS
- ArchitecturalRealization(H11) = FAIL
- ValidatedHit(H11) = REJECTED

This demonstrates that forwarding-path selection alone is insufficient:
the selected path may carry the wrong value.

---

## H13 — AUIPC d1 Forwarding Value Defect

Canonical control realization passed.

Observed live evidence:

- consumer instruction index: 2
- expected writeback: `0x12345001`
- observed writeback: `0x00000001`

Result:

- IntentHit(H13) = PASS
- ControlRealization(H13) = PASS
- ArchitecturalRealization(H13) = FAIL
- ValidatedHit(H13) = REJECTED

As with H11, the forwarding selector is correct while the forwarded
architectural value is incorrect.

---

## H18 — Architectural x0 Corruption

The canonical T18 control realization passed, including forwarding
exclusion.

However, direct architectural-state observation found:

- instruction index 1: expected x0 = `0x00000000`,
  observed x0 = `0x00000007`
- instruction index 2: expected x0 = `0x00000000`,
  observed x0 = `0x00000007`

Result:

- IntentHit(H18) = PASS
- ControlRealization(H18) = PASS
- ArchitecturalRealization(H18) = FAIL
- ValidatedHit(H18) = REJECTED

This distinguishes correct forwarding exclusion from incorrect
architectural register-zero state.

---

## H19 — False Stall for LOAD rd=x0

Canonical sequence contains a load writing x0 followed by a consumer
whose source is x0.

Architectural expectation:

`stall_cycles_before_accept = 0`

Observed:

`stall_cycles_before_accept = 1`

The same T19 run also incidentally hits H18. Both observations inherit
the same false-stall control mismatch, but this does not replace the
independent canonical T18 result above.

Result for canonical H19:

- IntentHit(H19) = PASS
- ControlRealization(H19) = FAIL
- ArchitecturalRealization(H19) = PASS
- ValidatedHit(H19) = REJECTED

The defect is therefore a control/timing defect in this witness rather
than an incorrect final architectural result.

---

## H20 — False Stall on Architecturally Unused rs2 Field

Canonical sequence uses an OP-IMM consumer whose raw instruction field
`[24:20]` numerically matches the preceding load destination, although
that field is not architecturally used as rs2.

Architectural expectation:

`stall_cycles_before_accept = 0`

Observed:

`stall_cycles_before_accept = 1`

Result:

- IntentHit(H20) = PASS
- ControlRealization(H20) = FAIL
- ArchitecturalRealization(H20) = PASS
- ValidatedHit(H20) = REJECTED

The defect is consistent with hazard detection using raw instruction
fields without qualifying whether rs2 is architecturally consumed.

---

## Important Interpretation Boundary

The following quantities must not be conflated:

`Intent Coverage != Validated Coverage`

The canonical campaign reaches every declared L1 scenario:

`Intent Coverage = 20/20 = 100%`

but only fifteen canonical witnesses satisfy both control and
architectural realization:

`Validated Coverage = 15/20 = 75%`

This difference is verification evidence, not a failure of the stimulus
generator.

The five rejected canonical targets expose three distinct defect classes:

1. forwarding-value correctness: H11, H13;
2. architectural-state correctness: H18;
3. unnecessary hazard stalls: H19, H20.

---

## Scalability

The live validation path avoids retaining an unbounded execution history.

L1 attribution requires dependency history only through d3, therefore
verification-side event retention is bounded.

Architectural evidence is also pruned after it is no longer required by
pending validation hits.

Consequently, retained verification state is O(1) with respect to total
campaign instruction count, apart from the bounded number of in-flight
validation observations.
