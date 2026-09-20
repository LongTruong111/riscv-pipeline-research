# L2 REALIZATION CONTRACT

## 1. Status

This document defines the missing runtime realization contract for
concrete L2 dependency hits.

It is a new verification-contract amendment.

It does not modify the frozen Week-5 through Week-8 files or redefine
the frozen L2 bin universe.

The frozen L2 bin remains:

    DependencyDistance x DependentRegister

with:

    DependencyDistance in {d1, d2}
    DependentRegister in {x1, ..., x31}

for exactly 62 bins.

---

## 2. Motivation

The frozen L2 specification defines:

    ValidatedHit = IntentHit AND RealizationValid

but does not define a complete executable per-L2Hit algorithm for
RealizationValid.

This document supplies that missing contract while preserving:

- executed-program-order dependency distance;
- nearest-writer attribution;
- x0 exclusion;
- separation of L1 and L2 coverage dimensions;
- separation of authoritative functional validation from diagnostic
  performance timing.

---

## 3. Concrete-hit validation

Validation is performed per concrete L2Hit, not merely per L2 bin.

For concrete hit h:

    h = (
        distance,
        register,
        producer_instruction_id,
        consumer_instruction_id
    )

define:

    L2ValidatedHit(h)
        =
        L2IntentHit(h)
        AND SourceControlPass(h)
        AND ProducerArchitecturalPass(h)
        AND ConsumerArchitecturalPass(h)

A later passing occurrence may validate a bin even if an earlier
occurrence of the same bin failed.

Therefore failure is per-hit and must not permanently poison a bin.

---

## 4. Intent authority

The frozen Week-5 L2CoverageCollector remains the authority for L2
Intent classification.

Week 10 shall not independently reclassify dependency distance or
nearest-writer attribution.

The following values are taken directly from the frozen L2Hit:

- distance;
- dependent register;
- producer instruction ID;
- consumer instruction ID;
- producer type;
- consumer type.

---

## 5. SourceControlPass

SourceControlPass validates the microarchitectural realization of the
specific RAW dependency represented by one L2Hit.

It is source-specific.

The consumer ExecutionEvent determines whether the dependent register
participates through:

- RS1;
- RS2;
- or both.

A source role participates only when:

    uses_rsN == True
    AND rsN == hit.register

For each participating source role, the independently generated timing
expectation shall identify:

    source_N_producer_id == hit.producer_instruction_id

and the observed forwarding selector shall equal the independently
expected forwarding selector.

Therefore:

    role_control_pass
        =
        producer_identity_match
        AND forwarding_selector_match

If both RS1 and RS2 refer to the same dependency, both participating
roles must pass even though only one L2 bin is credited.

SourceControlPass additionally requires the consumer's observed
stall_cycles_before_accept to equal the independently expected
stall_cycles_before_accept.

Thus:

    SourceControlPass(h)
        =
        all(participating role_control_pass)
        AND stall_match

At least one participating source role must exist.

---

## 6. What SourceControlPass does not include

Authoritative L2 validation shall not depend on:

- logical retire-cycle delta;
- wall-clock performance;
- benchmark throughput;
- diagnostic performance classification.

Those remain independent timing/performance diagnostics.

In particular:

    observed_retire_cycle != expected_retire_cycle

does not by itself remove an otherwise functionally valid L2
Validated hit.

This preserves the existing project separation between functional
coverage validation and Week-8 performance diagnostics.

---

## 7. ProducerArchitecturalPass

The producer of a positive L2 RAW dependency necessarily writes:

    rd != x0

ProducerArchitecturalPass requires the producer's authoritative
architectural realization to pass.

The required evidence is:

1. producer executed PC is architecturally correct;
2. producer architectural register-write behavior is correct;
3. architectural x0 remains zero.

For a positive RAW producer, writeback correctness includes:

- write enable;
- destination register;
- write data.

Producer correctness shall be evaluated independently from DUT
forwarding values.

---

## 8. ConsumerArchitecturalPass

ConsumerArchitecturalPass requires the architectural behavior of the
consumer instruction to be correct.

The required evidence is:

1. consumer executed PC is architecturally correct;
2. consumer register-write behavior is correct when applicable;
3. consumer store behavior is correct when applicable;
4. architectural x0 remains zero;
5. consumer next-PC behavior is architecturally correct.

The consumer next-PC requirement is satisfied when the next accepted
architectural instruction has:

    next_event.pc == consumer_expected_next_pc

This check is intentionally delayed until the successor instruction is
observed.

For an end-of-campaign consumer whose successor is not observed, the
hit remains unresolved rather than being falsely promoted.

---

## 9. Architectural evidence authority

Architectural expectations shall be produced only by the independent
RV32 architectural model.

DUT datapath values shall not be used as the oracle.

Register-write/store/x0 observations may be checked using semantics
equivalent to the existing frozen architectural / functional
scoreboards.

The implementation may reuse bounded streaming checker results, but
shall not use a pass result whose semantics omit evidence required by
this contract.

---

## 10. Simultaneous L2 hits

One consumer may produce multiple concrete L2 hits.

Example:

    RS1 <- producer at d2
    RS2 <- producer at d1

Each hit is validated independently.

They may share:

- consumer architectural evidence;
- consumer stall evidence;
- consumer next-PC evidence.

But each hit has its own:

- dependent register;
- producer identity;
- participating source role(s);
- expected forwarding selector(s);
- SourceControlPass result.

Failure of one hit does not automatically fail another hit unless the
shared architectural evidence itself fails.

---

## 11. Repeated hit semantics

Validation is occurrence-based.

For one L2 bin B:

    hit_1(B) -> fail
    hit_2(B) -> pass

shall produce:

    IntentSeen(B) = True
    ValidatedSeen(B) = True

after hit_2.

The first failed occurrence shall remain diagnostic evidence but shall
not permanently block later validation.

---

## 12. x0

x0 remains excluded from positive L2 RAW bins.

No L2Hit with:

    register == 0

is valid.

x0 architectural state is still checked as global architectural
evidence for producer/consumer correctness.

Negative x0 hazard behavior remains an L1 responsibility.

---

## 13. Dependency distance

L2 distance remains executed-program-order distance:

    distance
        =
        consumer_instruction_id
        - nearest_writer_instruction_id

for the frozen latest-writer relation.

Pipeline cycles, stalls, bubbles and redirects shall not alter this
distance.

Only:

    d1
    d2

participate in L2.

---

## 14. Relationship to L1

L1 and L2 may reuse the same low-level DUT observations and
architectural evidence.

However:

    L2Validated != arbitrary L1Validated

and no fixed:

    L2 bin -> Hxx

mapping is introduced.

L1 remains the behavioral scenario coverage model.

L2 remains the register-distance reachability model.

The L2 checker evaluates each concrete L2Hit directly.

---

## 15. Diagnostic timing disagreement

Week-7/Week-8 timing diagnostics may disagree with authoritative L2
functional validation.

Example:

    SourceControlPass                = True
    ProducerArchitecturalPass        = True
    ConsumerArchitecturalPass        = True
    PerformanceResult.passed         = False

Then:

    L2ValidatedHit = True

and the timing mismatch is retained independently as diagnostic
evidence.

Performance timing therefore does not silently redefine L2
functional coverage.

---

## 16. Unresolved evidence

A concrete hit shall remain unresolved while any authoritative evidence
required by this contract has not yet arrived.

Unresolved is not equivalent to failed.

No L2 Validated promotion occurs until all required authoritative
evidence is complete.

At campaign termination, unresolved hits shall be reported separately.

---

## 17. Bounded-state requirement

The runtime implementation shall retain only unresolved/in-flight
evidence.

Campaign-length result histories are prohibited from the authoritative
checker.

Required retained state shall be bounded by pipeline/evidence latency,
not by total executed instruction count N.

Therefore:

    retained_state = O(1) with respect to N

for a fixed pipeline and bounded architectural-memory workload.

Average registration and lookup shall be O(1).

---

## 18. Promotion

After one concrete hit resolves:

    SourceControlPass
        AND ProducerArchitecturalPass
        AND ConsumerArchitecturalPass

the implementation may call:

    L2CoverageCollector.promote_validated(...)

and/or:

    CoverageCollector.record_l2_validated(...)

for exactly that concrete hit's:

    (distance, register)

bin.

Promotion shall occur only after Intent for that hit/bin has already
been recorded.

---

## 19. Required tests

Before live integration, unit tests shall prove at least:

1. d1 EX/MEM dependency passes;
2. d2 MEM/WB dependency passes;
3. load-use d1 stall + MEM/WB forwarding passes;
4. wrong forwarding selector fails;
5. wrong producer identity fails;
6. wrong stall count fails;
7. producer architectural failure fails;
8. consumer register-write failure fails;
9. consumer store failure fails;
10. consumer next-PC failure fails;
11. x0 corruption fails architectural validation;
12. simultaneous d1/d2 hits validate independently;
13. rs1 == rs2 produces one L2 bin but validates both roles;
14. failed occurrence followed by passing occurrence promotes;
15. missing successor leaves control-flow consumer unresolved;
16. retire timing mismatch alone does not invalidate L2;
17. retained pending state stays bounded over a long stream.

---

## 20. Closure criterion

The contract is considered implemented only when:

- unit tests pass;
- live RTL integration passes;
- no frozen Week-5 through Week-8 file is modified;
- bounded-state long-run testing passes;
- L2 Intent and L2 Validated remain separately observable;
- checker mismatches prevent the affected occurrence from promotion.

After implementation, the stochastic campaign may use the frozen
thresholds:

    near closure = 59 / 62 validated bins
    full closure = 62 / 62 validated bins

without redefining the frozen L2 bin universe.
