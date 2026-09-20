# Week 9 — L2 Validated Coverage Specification Gap

## Status

OPEN BLOCKER for Gate T9 closure.

This document does not modify the frozen Week-5 L2 semantics.
It records an implementation blocker discovered during Week-9 live
integration and long-run verification.

## Frozen L2 semantics

The frozen L2 space is:

    DependencyDistance x DependentRegister

with:

    DependencyDistance in {d1, d2}
    DependentRegister in {x1, ..., x31}

for exactly 62 bins.

An L2 Intent Hit requires a real architectural RAW dependency with
nearest-writer attribution and executed-program-order distance d1 or d2.

The frozen validation rule is:

    ValidatedHit = IntentHit AND RealizationValid

A failed DUT realization must therefore retain Intent coverage while
not promoting the corresponding Validated coverage.

## Confirmed implementation boundary

`research/week5/impl/coverage_model.py` provides:

    L2CoverageCollector.observe(...)
    L2CoverageCollector.promote_validated(...)

`promote_validated()` is only a state-promotion primitive. Its contract
explicitly requires independent realization checking to succeed before
promotion.

No frozen Week-5 through Week-8 implementation defines an L2
RealizationValid checker.

The existing realization/validation implementations are L1-specific:

    L1ControlRealizationChecker
    L1ValidatedCoverageCollector
    L1ValidationOutcome

## Missing contract

The frozen material does not define a per-L2Hit algorithm that maps:

    L2Hit
        -> required DUT control evidence
        -> required architectural evidence
        -> RealizationValid

In particular, there is no frozen rule defining how an arbitrary
(distance, register) L2 hit is mapped to an L1 behavioral bin.

L2 explicitly excludes the following from its coverage dimensions:

- producer type;
- consumer instruction class;
- forwarding path;
- RS1 versus RS2;
- stall behavior;
- special writeback source.

Those distinctions belong to L1.

Therefore selecting an arbitrary L1 bin as the validation authority for
an L2 bin would invent semantics not present in the frozen plan.

## Prohibited Week-9 shortcuts

Until the missing contract is resolved, Week 9 shall not:

1. equate L2 Validated with L2 Intent;
2. promote L2 solely because the Week-8 FunctionalScoreboard passes;
3. promote L2 solely because PerformanceMonitor passes;
4. map an L2 bin to an arbitrary L1 Hxx bin;
5. use L1 Validated state as an implicit L2 Validated result;
6. redefine dependency distance using cycle distance;
7. modify frozen Week-5 through Week-8 files to manufacture closure.

## Current Week-9 behavior

Week-9 live integration records L2 Intent only.

No L2 Validated promotion is performed.

This is intentional and preserves the frozen distinction between
reachability and DUT correctness.

## Resolution criterion

This blocker may be closed only after an explicit L2 realization
contract is frozen that defines, for each concrete L2Hit:

1. the authoritative evidence required for RealizationValid;
2. which producer and consumer observations participate;
3. how forwarding/control correctness is evaluated;
4. how architectural correctness is evaluated;
5. handling of two simultaneous L2 hits from one consumer;
6. handling of repeated hits after an earlier failed hit;
7. the exact relationship, if any, between L1 validation and L2
   validation;
8. promotion behavior when diagnostic timing evidence and
   architectural evidence disagree.

Only after that contract exists may an L2 realization checker be
implemented and connected to `promote_validated()` /
`record_l2_validated()`.

## Gate T9 impact

The following Week-9 evidence is valid independently of this gap:

- deterministic L1/L2 Intent classification;
- L1 authoritative validated attribution;
- streaming functional/performance equivalence;
- bounded retained verification state;
- long-run RSS measurements;
- throughput measurements;
- campaign runtime estimates;
- streamed checkpoint telemetry.

However Gate T9 shall not claim completed L2 Validated Coverage while
this specification gap remains open.

