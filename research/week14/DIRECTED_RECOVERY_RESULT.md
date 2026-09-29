# Week 14 Directed Recovery Result

## Historical status

The original preregistered Directed attempt remains FAIL.

It is preserved under:

`research/week14/results/attempt1_preregistered/`

The original result is not reclassified.

## Post-erratum confirmation

Status:

`PASS_POST_ERRATUM_CONFIRMATION`

Results:

- canonical Directed cases: 20;
- L1 Intent: 20/20;
- L1 Validated: 18/20;
- attribution exercised: 20/20;
- control oracle exercised: 20/20;
- architectural oracle exercised: 20/20.

Validated:

T01-T17 and T20.

Known-defect rejections:

- T18/H18 — `REGFILE_X0_WRITE`;
- T19/H19 — `LOAD_RD_X0_FALSE_STALL`.

T19 also produces a correlated incidental H18 rejection from the same
false-stall root cause.

No additional rejected case or root cause was observed.

## Gate interpretation

The Directed obligation is complete under the post-erratum recovery
contract.

This does not complete Gate T14 by itself.

If all remaining Week-14 obligations pass, the allowed final gate status
is:

`RECOVERED_WITH_ERRATUM`

A plain `PASS` status is not used because the original preregistration
was falsified.
