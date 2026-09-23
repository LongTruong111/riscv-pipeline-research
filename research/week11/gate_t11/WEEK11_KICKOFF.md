# Week 11 — Verification Readiness Kickoff

## Baseline

- Base tag: gate-t10
- Base commit: 55725b9
- Branch: research/week11-verification-readiness

## Frozen coverage

- L1: 20 bins
- L2: 62 bins
- L2 dimensions: {d1,d2} x {x1,...,x31}

## Frozen semantics

Week 5-10 semantics remain authoritative unless explicitly amended.

Do not silently change:
- ExecutionEvent semantics
- executed-program-order dependency distance
- Intent / Validated separation
- Timing Oracle semantics
- adaptive action space
- epsilon-greedy update
- q_floor
- RNG partition
- EBD semantics
- exact-N termination
- bounded IMEM streaming
- checkpoint semantics

## Week 11 priorities

1. Expected-Stall Calculator bug
2. Monitor / attribution bug
3. Performance Monitor false-positive
4. Coverage Collector correctness
5. Adaptive CGS reproducibility
6. Throughput bottleneck

## Current evidence

### Expected-stall

- Timing Oracle unit tests PASS.
- Canonical RTL timing T01-T20 PASS.
- H06/H07 require one stall.
- Other frozen L1 bins require zero stalls.
- No Expected-Stall Calculator defect has yet been reproduced.

Status: UNRESOLVED / NOT YET REPRODUCED.

### T19 / T20

T19 and T20 are known DUT unnecessary-stall cases.

They are not evidence that the expected-stall oracle is incorrect.

### Performance Monitor

Week-8 delta_cycles is absolute lateness relative to the ideal schedule.

Cumulative lateness after an earlier excess stall is intentional frozen
behavior and must not be changed without an amendment.

The Week-11 "Performance Monitor false-positive" issue has not yet been
identified.

Status: UNRESOLVED / NOT YET REPRODUCED.

## Gate T11

- [ ] make unit-tests PASS
- [ ] 50-instruction sequence PASS
- [ ] Timing oracle PASS in-scope suite
- [ ] Intent/validated attribution PASS
- [ ] Adaptive CGS reproducible
- [ ] Full-instrumentation throughput measured
- [ ] Estimated campaign runtime feasible

## Mandatory scope

Do not cut:

- 20 L1 bins
- 62 L2 bins
- Functional Scoreboard
- Cycle-Gap Checker
- 4 generators
- fixed n=15
- frozen reward/update rule
- main mutation M1/M2/M3
- statistical protocol
