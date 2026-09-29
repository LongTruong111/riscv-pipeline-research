# Week 14 Contract — Directed + Static Generator Finalization

## 1. Authority

Week 14 starts from the peeled commit referenced by:

`GATE_T13_COMPLETE^{commit}`

The frozen experimental and verification inputs are not to be changed
during Week 14 unless a reproducible infrastructure defect is first
identified and explicitly invalidates the affected evidence.

Week 14 is a finalization week, not a tuning week.

---

## 2. Gate-T14 Directed interpretation

`Directed = 100% L1` means:

`L1 Intent = 20/20`

with all of the following additionally required for every designated
T01-T20 case:

1. the designated L1 bin is activated;
2. attribution identifies the intended producer/consumer event;
3. every required control/timing oracle is exercised;
4. every required architectural/value oracle is exercised;
5. the observed verdict matches the preregistered expectation.

An Intent hit does not become a Validated hit when control or
architectural realization is incorrect.

Removing T18 from the denominator is prohibited.

Changing a checker expectation to match defective RTL behavior is
prohibited.

---

## 3. Pre-DUT rejection preregistration

Known-defect classification is frozen before the Week-14 final Directed
RTL run.

The authoritative machine-readable artifact is:

`research/week14/preflight/directed_expected_rejections.json`

Classification is by root-cause signature, not merely by case name or by
the existence of a rejected verdict.

A failure is known only if its observed signature matches an exact
preregistered signature.

Any other rejection is unexpected and fails Gate T14.

A missing preregistered rejection must be reported explicitly. It must
not be silently removed from the preregistration after observing RTL
results.

---

## 4. Frozen-DUT expected rejection set

Static analysis of the canonical T01-T20 fixtures yields exactly one
expected Directed rejection:

`T18 / H18 / REGFILE_X0_WRITE`

T18 contains:

`ADDI x0,x1,7`

Under the frozen independent-test initial state:

`x1 = 0`

therefore the architectural result presented to destination x0 is:

`7`

The correct architectural invariant remains:

`x0 = 0`

The frozen DUT physically permits the write, so the preregistered
signature requires an x0 architectural failure while the H18 control
realization itself remains correct.

---

## 5. Non-activated JALR defect

The frozen DUT also retains the known JALR target-bit-0 defect.

However, none of the canonical T01-T20 instructions is JALR.

T15 uses JAL.

Therefore the JALR defect is not in the Week-14 canonical Directed
expected-rejection set.

A future JALR failure may not be retroactively absorbed into the Week-14
known set unless the preregistered fixture set itself already activated
that exact condition.

---

## 6. T19 boundary

T19 contains:

`LW x0,0(x1)`

but the frozen independent-test initial state and deterministic DMEM
initialization give:

`x1 = 0`

`DMEM[0] = 0`

so the architectural write value is zero.

Thus T19 does not preregister an x0-corruption rejection.

The earlier H19 false load-use stall is historical evidence, not a
Week-14 expected rejection; the frozen Gate-T13 DUT contains the
operand-usage-qualified hazard fix.

T19 is therefore required to complete without a target rejection in the
Week-14 final Directed run.

---

## 7. Historical defects are not current expectations

Historical Week-5 H11/H13 forwarding-value failures and H19/H20
load-use false stalls are not copied into the Week-14 expected-rejection
set.

Week-14 expectations are derived from:

1. the Gate-T13 frozen DUT;
2. the frozen known-defect set;
3. the canonical T01-T20 fixtures;
4. pre-DUT static/architectural analysis.

They are not derived from historical failure counts.

---

## 8. Protected provenance

The machine-readable protected-tree artifact is:

`research/week14/preflight/protected_tree_sha.json`

At minimum the following committed trees are frozen against the
Gate-T13 base:

- `design`
- `research/week5/impl`
- `research/week5/rtl`
- `research/week5/vplan`
- `research/week10/adaptive`
- `research/week13`

Tree identity is checked using Git tree objects.

Working-tree changes to protected paths must also be absent.

The guard cannot establish its own authority because it lives in the
modifiable Week-14 tree. Final enforcement therefore also requires
human review of the Week-14 guard and the final Gate-T14 tag.

---

## 9. Directed fixture provenance

The canonical T01-T20 fixture files remain under:

`research/week5/rtl/fixtures/l1/`

Week 14 does not duplicate or rewrite them.

Per-fixture SHA256 values are stored in:

`research/week14/preflight/directed_static_audit.json`

The final Directed runner must verify those hashes before execution.

---

## 10. Per-case isolation

Every Directed case must execute with an independent reset and fresh
architectural/testbench state.

State from T18 must not bleed into T19 or T20.

A combined T01-T20 execution without case isolation is not an acceptable
Gate-T14 result.

---

## 11. M1 Pure Random

M1 reuses the frozen Week-13 implementation unchanged.

Week 14 may package and hash the final configuration but may not retune
or redefine the generator.

M1 uses no runtime coverage feedback.

Finite-sample empirical family frequencies are diagnostic only and are
not a correctness gate.

---

## 12. M2 Weighted Random reuse decision

M2 first attempts composition from the frozen M1 realization and stream
stack.

The intended difference is the static stimulus policy, not the
measurement policy.

Preferred composition:

`M1 legality/realization + M1 stream/runtime + M2 static weighted policy`

with an independent M2 seed namespace.

Frozen Week-13/M1 code is not refactored merely to make this composition
more convenient.

If direct composition is impossible, Week 14 may introduce a thin
adapter.

Only if both approaches are impossible may realization logic be
reimplemented, and any such implementation requires differential
equivalence tests against the appropriate frozen realization behavior.

---

## 13. M2 no-feedback requirement

M2 must not read:

- Intent coverage;
- Validated coverage;
- uncovered bins or registers;
- reward;
- Q values;
- epsilon/alpha state;
- prior DUT outcome.

This requirement will be checked both structurally and behaviorally.

The behavioral requirement is:

for the same seed and static configuration, changing or nulling runtime
coverage state must not change the generated plan or stream.

---

## 14. Common measurement policy

M1, M2 and M3 differ in stimulus policy.

They do not differ in:

- accepted-instruction denominator;
- exact-N cut semantics;
- checkpoint semantics;
- coverage taxonomy;
- checker semantics;
- attribution semantics;
- snapshot/invariant accounting.

Changing these between methods invalidates the comparative interpretation.

---

## 15. Directed-versus-stochastic containment boundary

Directed tests intentionally probe special defect sites including x0.

Positive stochastic M1/M2/M3 campaigns use the frozen legal containment
envelope that avoids known x0/JALR defect activation.

Therefore Directed-versus-stochastic bug-count comparisons are not an
unbiased metric of generator quality.

The comparative campaign evaluates coverage acquisition within the
common frozen stochastic legal envelope.

---

## 16. Gate-T14 core condition

Gate T14 requires all of the following:

`20/20 designated L1 Intent`

and:

`correct attribution`

and:

`all required oracles exercised`

and:

`observed rejection set matches preregistered signatures`

and:

`unexpected rejection count = 0`

plus successful M1/M2 configuration freeze and provenance checks.

Validated coverage remains reported separately and is never falsified to
make the gate green.
