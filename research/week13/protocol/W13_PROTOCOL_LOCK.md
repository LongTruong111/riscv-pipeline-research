# Week13 Pilot Protocol Lock

## Baseline

Week13 development baseline:

- tag: gate-t12
- commit: 4cb369083cc6e6c3f9c945442e44780591a10074

No pilot coverage result has been observed at the time this lock is
created.

## Protocol authority

For Adaptive-CGS fields explicitly redefined by the later closed
Gate-T5 preregistration:

research/week5/gate_t5/ADAPTIVE_PREREGISTRATION.md

is authoritative over the earlier:

research/week5/vplan/ADAPTIVE_CGS_SPEC.md

This authority relationship is explicitly frozen by:

research/week10/ADAPTIVE_CGS_CONTRACT.md

Week10 campaign execution amendments remain authoritative for execution
semantics introduced before pilot execution.

## Frozen candidate space

epsilon:
- 0.05
- 0.10
- 0.20

alpha:
- 0.1
- 0.3
- 0.5

nominal batch:
- 500
- 1000
- 2000 accepted executed instructions

Cartesian configurations:

3 x 3 x 3 = 27

## Pilot seeds

- 13001
- 13002
- 13003

Adaptive pilot runs:

27 x 3 = 81

## Pilot budget

Exactly:

10000 accepted executed instructions / configuration / seed

Maximum Adaptive pilot budget:

810000 accepted executed instructions

Accepted architectural instruction remains the canonical progress and
budget denominator.

## Adaptive execution semantics

- 10 frozen arms A0-A9
- epsilon-greedy policy
- recency-weighted Q update
- Q_floor = 0.05
- targeted-template : filler = 80 : 20
- no mandatory initial one-pull-per-arm sweep
- adaptive state resets independently for every seed
- no warm start between runs
- checkpoint interval = 1000 accepted instructions
- normal pilot termination must be exact at 10000 accepted instructions

## Hyperparameter-selection data

Adaptive optimization uses L2 Intent Coverage.

Validated Coverage and checker results are recorded independently but
must not affect:

- reward
- Q update
- arm selection
- register targeting
- hyperparameter selection

## Selection criterion

Primary:
- median normalized L2 Intent Coverage AUC across the three pilot seeds
- evaluated over 0..10000 accepted instructions
- coverage checkpoints every 1000 accepted instructions

Secondary:
- median L2 Intent bins@10000 across the three pilot seeds

Tertiary:
- median wall-clock time across the three pilot seeds

Practical tie:

- normalized AUC difference < 1 percent
AND
- bins@10000 difference <= 1 bin

Deterministic practical-tie resolution:

1. lower median wall-clock time
2. larger batch size
3. smaller epsilon
4. smaller alpha

Exactly one final Adaptive-CGS configuration shall be selected.

No configuration shall be selected by visual inspection of coverage
curves.

## Pilot-data quarantine

Pilot observations are used only for Adaptive-CGS configuration
selection.

They shall not be included in:

- final M1/M2/M3 comparative datasets
- inferential statistical tests
- final comparative sample size

## Legacy definitions explicitly rejected

The following earlier VPlan values are obsolete for the Adaptive pilot:

- seeds {101, 202, 303}
- 100000 instructions/configuration/seed
- 100:0 discretionary template:filler
- mandatory one-pull-per-arm initial sweep

No Week13 implementation may restore these legacy definitions.
