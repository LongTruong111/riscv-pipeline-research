# Week 15 — Provenance Repair 001

## Classification

`SEMANTICS_PRESERVING_PROVENANCE_FIX`

## Timing

This correction was made after the Adaptive-CGS Week-15 freeze contract
was preregistered but before:

- implementation-conformance qualification;
- reproducibility qualification;
- any Week-15 qualification seed execution;
- any final seed execution.

## Defect

The frozen contract referenced the authority identifier:

`week13_common_protocol`

from the stopping-rule authority list, but the machine-readable authority
manifest did not contain a record with that identifier.

The referenced authority itself already existed and had already been
audited:

`research/week13/protocol/STOCHASTIC_GENERATOR_ADDENDUM.md`

## Repair

The missing authority-manifest record was added with its frozen SHA-256.

The contract's authority-manifest SHA-256 pointer was then regenerated.

No Adaptive-CGS semantic field was changed.

In particular, this repair does not change:

- arm taxonomy;
- templates;
- reward;
- epsilon;
- alpha;
- q_floor;
- update rule;
- batch semantics;
- initialization;
- action selection;
- register targeting;
- filler policy;
- seed derivation;
- stopping semantics;
- qualification seeds or budgets.

## Qualification consequence

No qualification evidence existed before this repair.

Therefore no experimental rerun or evidence supersession is required.
