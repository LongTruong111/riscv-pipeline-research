# Gate T15 Result

## Status

**PASS**

Gate T15 closes the pre-final-campaign freeze and reproducibility qualification for the M0–M3 method set.

This gate does **not** contain final campaign results. No final campaign seed was executed before closure.

## Frozen method set

- **M0 — Directed:** Week14 directed closure / defect-confirmation method.
- **M1 — Pure Random:** frozen final stochastic baseline.
- **M2 — Static Weighted Random:** frozen static generator.
- **M3 — Adaptive CGS:** frozen epsilon-greedy multi-armed-bandit generator with recency-weighted action-value updates.

The complete method identities, artifact hashes, and final campaign seed allocations are frozen in:

`research/week15/audit/M0_M3_FREEZE_MANIFEST.json`

## M3 reproducibility qualification

The fresh-process qualification matrix contained six runs:

- seed 15001: A/B, 10,000 accepted instructions each;
- seed 15002: A/B, 10,000 accepted instructions each;
- seed 15003: A/B, 100,000 accepted instructions each.

Total qualification budget: **240,000 accepted instructions**.

All same-seed A/B pairs produced identical SHA-256 hashes for every gate-required canonical trace:

- `instruction_stream`
- `arm_decision_trace`
- `reward_trace`
- `coverage_trace`

Qualification status: **PASS**.

Performance thresholds and achieved coverage levels were not Gate T15 acceptance criteria. Qualification results were not used to tune the generator, reward, hyperparameters, RNG, targeting, templates, filler policy, or tie-breaking behavior.

## Qualification chronology

The preserved qualification chronology is:

1. Attempt 001 — `INFRA_INVALID`
2. Attempt 002 — `INFRA_INVALID`
3. Attempt 003 — `INFRA_INVALID`
4. Attempt 004 — `PASS`

The invalid attempts remain preserved as historical evidence. No selective rerun was used to construct the passing matrix.

## Gate conditions

At closure:

- Gate T14 remains intact with strongest status `RECOVERED_WITH_ERRATUM`.
- All 18 required Adaptive-CGS freeze fields are defined.
- `true_open_protocol_items = []`.
- Canonical trace serialization was frozen before qualification.
- The complete fresh-process qualification matrix passed.
- All gate-required A/B trace hashes matched.
- Protected source/authority hashes remained unchanged.
- No post-qualification semantic change occurred.
- No qualification result was used for tuning.
- No final campaign seed was used before Gate T15.
- The M0–M3 final method manifest is complete.

## Final campaign authorization

After the annotated `GATE_T15_COMPLETE` tag is created and verified, the frozen final comparative campaign is authorized:

- M1 seeds: `1001..1015`
- M2 seeds: `2001..2015`
- M3 seeds: `3001..3015`
- 100,000 accepted instructions per run
- 15 runs per stochastic method
- 45 runs total
- 4,500,000 accepted instructions total
- no seed replacement or deletion
- no tuning after Gate T15

Final campaign status at this closure: **NOT RUN**.
