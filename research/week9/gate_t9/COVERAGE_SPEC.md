# Week 9 Coverage Collector Contract

## 1. Frozen prerequisites

Week 9 inherits without modification:

- L1 = exactly 20 bins: H01..H20
- L2 = exactly 62 bins
- L2 dimensions:
  - dependency distance in {d1, d2}
  - architectural dependent register in {x1..x31}
- dependency distance is executed-program-order distance
- x0 is excluded from positive L2 RAW coverage
- Intent Coverage and Validated Coverage are distinct
- previous Week 5-8 artifacts remain frozen

The obsolete 1,922-bin L2 definition MUST NOT be restored.

## 2. Coverage levels

### Intent hit

An Intent hit means the executed stimulus semantically contains the
coverage scenario.

Intent classification must not depend on whether the DUT behaves correctly.

### Validated hit

A hit may be promoted only when the required realization and
architectural evidence passes.

Conceptually:

ValidatedHit =
    IntentHit
    AND ControlPass
    AND RequiredArchitecturePass

Promotion is per-hit.

A rejected hit does not permanently invalidate a bin. A later hit may
successfully validate the same bin.

## 3. First-hit metadata

Intent and Validated first-hit metadata are tracked independently.

For each bin:

- intent_first_instruction_id
- intent_first_cycle
- intent_first_wall_ns

- validated_first_instruction_id
- validated_first_cycle
- validated_first_wall_ns

First-hit metadata is immutable after first assignment.

Wall-time metadata is telemetry and is not required to be deterministic.

## 4. Deterministic state

For identical executed event streams, coverage collection must produce
identical:

- hit bins
- first-hit instruction IDs
- first-hit cycles
- checkpoint instruction counts
- Intent/Validated counts
- validation classifications

Wall-time values are explicitly excluded from deterministic equality.

## 5. Checkpoints

Coverage checkpoints occur every 1,000 executed instructions:

1000, 2000, 3000, ...

Checkpointing is based on accepted executed-program-order instruction
count, not simulation cycle count and not raw fetched instruction count.

Stalled instructions do not create additional executed events.

Flushed/wrong-path instructions do not create executed events.

## 6. Validation status

Week 9 uses the following attribution statuses:

- INTENDED
- REALIZED_CORRECTLY
- TIMING_MISMATCH
- FUNCTIONAL_MISMATCH
- TIMING_AND_FUNCTIONAL_MISMATCH
- UNRESOLVED

Functional and performance evidence remain independent.

A timing mismatch alone must not be reclassified as a functional failure.

A functional mismatch alone must not imply a timing failure.

## 7. Complexity and retained state

Coverage state must be bounded with campaign length.

Target:

- O(1) expected work per hit/update
- O(N) total work for N executed instructions
- O(1) coverage retained state with respect to N

Long-run InstructionEvent / RetireEvent / attribution records must not be
appended indefinitely to in-memory Python lists merely for coverage.

Long-term detailed telemetry should be streamed or batch-written.

## 8. Canonical regression invariants

For frozen canonical T01..T20:

- L1 Intent = 20/20
- L1 Validated = 15/20

Known unvalidated bins remain:

- H11
- H13
- H18
- H19
- H20

These are known DUT defects and must not be treated as missing stimulus.
