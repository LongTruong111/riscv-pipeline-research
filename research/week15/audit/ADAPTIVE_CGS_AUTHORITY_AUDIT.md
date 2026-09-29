# Week 15 — Adaptive CGS Authority Audit

## Status

`READ_ONLY_AUDIT_COMPLETE`

This audit was performed before Week-15 Adaptive-CGS qualification
execution and before any Week-15 generator tuning or final-seed use.

## Base

Gate T14 commit:

`08549178134cc2dce65a8b4e8a651e25307176fd`

## Authority result

The audit found no demonstrated `TRUE_OPEN_PROTOCOL_ITEM`.

Week 15 therefore does not introduce a new Adaptive-CGS algorithm.
It consolidates and freezes the already-defined M3 semantics, with
the Week-13 selected hyperparameters overriding the historical
Week-10 engineering hyperparameter instance where applicable.

## Week-13 selected hyperparameters

- epsilon = 0.10
- alpha = 0.5
- q_floor = 0.05
- nominal batch = 500 accepted instructions

The historical Week-10 engineering value `alpha = 0.30` is not the
Week-15/final selected value.

## Inherited frozen Adaptive-CGS semantics

The audited authority surface already defines:

- exactly ten arms A0..A9;
- L2 Intent as the adaptive objective;
- attributable-new-bin epoch reward;
- recency-weighted action-value update;
- Q[a] = 0.0 initialization;
- pull_count[a] = 0 initialization;
- recent_reward[a] = 0.0 initialization;
- epoch_index = 0 initialization;
- no mandatory initial one-pull-per-arm sweep;
- epsilon-greedy action selection;
- uniform exploration over A0..A9;
- maximum-Q exploitation;
- seeded-uniform tie resolution among exact maximum-Q arms;
- Q-floor uniform fallback;
- uncovered-first positive-register targeting;
- A4 ordered distinct d1/d2 target selection;
- deterministic 4:1 targeted-template/background-filler scheduling;
- deterministic coverage-independent filler construction;
- deterministic decision/target/realization RNG-domain separation;
- SHA-256 subsystem-seed derivation.

## Common campaign semantics

M3 remains governed by the common frozen stochastic campaign contract,
including:

- accepted architectural instruction denominator;
- exact accepted-N termination;
- no rounding to adaptive epoch boundaries;
- checkpoint interval of 1000 accepted instructions;
- lifecycle conservation;
- coverage lifecycle;
- common failure taxonomy.

## Epistemic conclusion

No new Week-15 performance-informed design decision is required by the
audited M3 semantics.

Week 15 may now preregister a consolidated Adaptive-CGS freeze contract.
Qualification results must not be used to modify that contract.

The machine-readable source hashes and authority classification are in:

`research/week15/audit/adaptive_cgs_authority_manifest.json`
