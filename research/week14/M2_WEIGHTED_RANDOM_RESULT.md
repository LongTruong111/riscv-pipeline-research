# Week 14 M2 Weighted-Random Qualification Result

## Frozen method

Method:

`M2-WR — Weighted Random`

The arm distribution is static and was frozen before this RTL smoke.

No runtime coverage, reward, checker-result, or adaptive target feedback is
used to select arms or target registers.

## Static generator witness

Non-final witness:

- seed: `14001`;
- accepted budget: `1000`;
- block count: `405`;
- image words: `1048`;
- plan hash:
  `3b23d6e4887e305100542416c77f93994b229c9f9dab91ac4c0ac9f86465d2c9`.

The final block for this witness is complete rather than partial.

The partial-final-block exact-cut path was qualified separately by the
runtime-compatibility regression.

## Bounded-runtime qualification

The M2 plan was first qualified against the frozen Week-13 bounded runtime
stack without RTL execution.

Observed:

- accepted: `1000`;
- max resident IMEM words: `128`;
- final pending entries: `0`;
- final used words: `0`;
- logical generations crossed: through generation `8`.

## RTL smoke

Harness commit:

`e651878db8c071943f1ed1d9ae687eb5af5f19be`

The harness was frozen before the RTL smoke.

Result:

`PASS`

Observed:

- accepted: `1000`;
- retired at exact cut: `997`;
- in flight at exact cut: `3`;
- cycles: `1104`;
- stalls: `56`;
- flushes: `24`;
- released entries: `405`;
- refill pauses: `230`;
- patched words: `1048`;
- patch reuses: `920`;
- maximum resident words: `128`;
- L1 Intent / Validated: `17 / 17`;
- L2 Intent / Validated: `62 / 62`.

The checker stack reported no functional, performance, or accepted-timing
failure.

The exact accepted plan hash matched the frozen static witness.

## Scope

This result qualifies the Week-14 M2 static generator and its compatibility
with the frozen bounded RTL campaign infrastructure.

It is not a final comparative campaign.

Final M2 seeds remain:

`2001..2015`

with:

`100000 accepted instructions per seed`

and were not executed in Week 14.
