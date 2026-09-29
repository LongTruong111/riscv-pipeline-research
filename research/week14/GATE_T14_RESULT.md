# Gate T14 — Directed + Static Generator Finalization

## Final status

`RECOVERED_WITH_ERRATUM`

A plain `PASS` is explicitly prohibited by the frozen Directed recovery
contract.

## Directed method — M0

The original preregistered Directed gate attempt remains:

`FAIL`

It is not reclassified.

The failure was caused by a preregistration interpretation error regarding
H19. The frozen DUT still contains the load-rd-x0 false-stall defect that the
original Week-14 preregistration incorrectly assumed had already been fixed.

A prospective post-erratum recovery contract was subsequently frozen and
executed.

Recovery confirmation:

`PASS_POST_ERRATUM_CONFIRMATION`

Observed Directed closure:

- Intent: `20/20`;
- attribution exercised: `20/20`;
- control oracle exercised: `20/20`;
- architectural oracle exercised: `20/20`;
- Validated: `18/20`.

The two designated known root causes are:

1. `REGFILE_X0_WRITE` — T18 / H18;
2. `LOAD_RD_X0_FALSE_STALL` — T19 / H19.

The H18 and H19 rejection records observed inside T19 are correlated
observations of the same load-rd-x0 false-stall root cause, not two separate
defects.

## Pure Random — M1

The final M1 configuration is frozen.

It preserves:

- no runtime coverage feedback;
- static uniform generation policy;
- accepted-instruction denominator;
- checkpoint interval of 1000;
- final seeds `1001..1015`;
- final budget of `100000` accepted instructions per seed.

The final M1 `100k x 15` campaign was not executed in Week 14.

## Weighted Random — M2

The static Weighted-Random generator is frozen with the preregistered
16-ticket arm distribution.

It uses no adaptive coverage, reward, or uncovered-bin feedback.

The bounded runtime compatibility preflight passed.

The non-final RTL smoke:

- seed: `14001`;
- accepted: `1000`;
- released entries: `405`;
- image words patched: `1048`;
- maximum resident IMEM words: `128`;
- L1 Intent / Validated: `17 / 17`;
- L2 Intent / Validated: `62 / 62`.

The exact frozen plan hash was:

`3b23d6e4887e305100542416c77f93994b229c9f9dab91ac4c0ac9f86465d2c9`

The final M2 seeds remain `2001..2015`, each with a budget of `100000`
accepted instructions. That campaign was not executed in Week 14.

## Protected state

The protected Gate-T13 design, Week-5 verification infrastructure,
Week-10 adaptive implementation, and Week-13 campaign infrastructure remain
unchanged according to their frozen tree hashes.

## Scope and limitations

Gate T14 closes the Week-14 objective:

`Directed + Static Generator Finalization`

It does not claim final comparative M1/M2/M3 campaign results.

The canonical T01-T20 Directed suite does not activate the frozen JALR
target-bit-0 defect.

Positive M1/M2 stochastic generation intentionally excludes positive writes
to `x0`; H18/H19 remain separately covered Directed/known-defect
obligations.

Accordingly, the strongest valid Gate-T14 closure label is:

`RECOVERED_WITH_ERRATUM`
