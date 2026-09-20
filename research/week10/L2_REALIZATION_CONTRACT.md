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

## 7. ParticipantArchitecturalPass

Architectural validation is evaluated per participating instruction.

For participant instruction `i`, define:

    ParticipantArchitecturalPass(i)
        =
        PCPass(i)
        AND WritebackPass(i)
        AND StorePass(i)
        AND NextPCPass(i)
        AND ConditionalX0Pass(i)

The required evidence is produced from the independent architectural
model and the existing architectural observation semantics.

### 7.1 Current-PC correctness

The accepted instruction PC must equal the independent architectural
model's expected current PC.

The DUT's 9-bit PC shall not be used to truncate a wider Golden PC in
order to manufacture a pass.

### 7.2 Register-write correctness

Architectural register-write behavior must be correct:

- write enable;
- destination register;
- write data;

when an architectural register write is expected.

Unexpected architectural GPR writes must fail.

### 7.3 Store correctness

Store behavior must be correct:

- store enable;
- address;
- data;

when a store is expected.

Unexpected stores must fail.

### 7.4 Next-PC correctness

The participant's expected `next_pc` is taken from the independent
architectural model.

When the next accepted architectural instruction is observed:

    observed_successor_pc == participant_expected_next_pc

must hold.

This evidence is attributed to the predecessor instruction.

Therefore control-flow correctness is validated without redefining
executed-program-order dependency distance.

For the final instruction of a campaign, if no successor is observed,
`next_pc` remains unresolved rather than being falsely passed.

### 7.5 Conditional x0 correctness

x0 is not a global pass requirement for every positive L2 hit.

An x0 check is authoritative for a participant only when that
participant instruction itself attempts to write `rd=x0`:

    event.writes_rd == True
    AND event.rd == 0

This prevents an unrelated persistent x0 defect from poisoning all later
positive L2 validation.

For ordinary positive L2 participants whose destination is not x0, an
unrelated global x0 mismatch shall not invalidate the hit.

---

## 8. ProducerArchitecturalPass

For producer instruction `p`:

    ProducerArchitecturalPass
        =
        ParticipantArchitecturalPass(p)

A positive L2 producer necessarily satisfies:

    producer.rd != x0

because x0 cannot carry architectural producer state.

The producer nevertheless requires correct:

- current PC;
- register-write behavior;
- store behavior;
- next-PC behavior.

Conditional x0 evidence applies only if required by the participant rule
above.

---

## 9. ConsumerArchitecturalPass

For consumer instruction `c`:

    ConsumerArchitecturalPass
        =
        ParticipantArchitecturalPass(c)

The consumer therefore requires correct:

- current PC;
- register-write behavior;
- store behavior;
- next-PC behavior.

If the consumer itself attempts to write `rd=x0`, x0 preservation is
also required for that consumer.

Week-8 `FunctionalResult.passed` shall not be consumed wholesale as the
L2 architectural verdict because that result includes an unconditional
global x0 check.

The Week-10 implementation shall instead consume the individual
authoritative architectural evidence needed by this contract.

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
10. producer next-PC failure fails;
11. consumer next-PC failure fails;
12. consumer-local rd=x0 corruption fails that hit;
13. unrelated pre-existing x0 corruption does not poison an ordinary
    positive L2 hit;
14. simultaneous d1/d2 hits validate independently;
15. rs1 == rs2 produces one L2 bin but validates both roles;
16. failed occurrence followed by passing occurrence promotes;
17. missing successor leaves the affected hit unresolved;
18. retire timing mismatch alone does not invalidate L2;
19. retained pending state stays bounded over a long stream.

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
