# Gate T12 Status

## 1. Scope

Week 12 closes the verification-readiness smoke gate for:

- canonical 50–100 instruction end-to-end execution;
- architectural, functional, timing, coverage, and telemetry checks;
- isolated forwarding mutation smoke;
- authoritative mutation detection;
- immutable first-failure capture;
- diagnostic waveform preservation;
- regression against the frozen Gate-T11 baseline.

The frozen Gate-T11 DUT and Week5–Week11 verification semantics are not
modified.

## 2. Gate Definition

```text
E2E_PASS =
    accepted_58
    AND retired_58
    AND architectural_pass
    AND functional_pass
    AND performance_pass
    AND coverage_valid
    AND telemetry_complete

M1_CAUGHT =
    canonical_control_pass
    AND mutation_target_activated
    AND authoritative_checker_failure
    AND first_failure_known
    AND waveform_saved

T12_PASS =
    E2E_PASS
    AND M1_CAUGHT
    AND regression_pass
```

## 3. Golden58 E2E

Canonical workload:

```text
accepted=58
retired=58
stalls=10
flushes=0
functional_failed=0
performance_failed=0
total_excess_cycles=0
first_failure=None
coverage_executed=58
```

Coverage result:

```text
l1_intent=4
l1_validated=4
l2_intent=4
l2_validated=4
l2_terminal_pending=1
checkpoints=0
```

The single terminal L2 pending concrete hit is expected because no
synthetic instruction 59 is fabricated after the final accepted
instruction.
Because 58 accepted instructions is below the frozen 1000-instruction
production checkpoint interval, zero checkpoints is expected.
Telemetry confirms:

```text
accepted_instructions=58
retired_instructions=58
architectural_pass=True
functional_pass=True
performance_pass=True
coverage_valid=True
first_failure=None
git_dirty=False
```

Result:

```text
E2E PASS
```

## 4. M1-Smoke Definition

Week-12 M1-smoke disables:

```text
EX/MEM -> Forward_A
```

The isolated mutant is:

```text
research/week12/mutants/ForwardingUnit_m1.sv
```

Canonical:

```text
design/ForwardingUnit.sv
```

is excluded from the mutation build.
No canonical DUT source is modified.

## 5. Mutation Target Activation

The mutation workload is the frozen Week11 integrated-50 sequence.
Target activation is derived independently from mutant output using the
canonical forwarding expectation:

```text
expected Forward_A == 2'b10
```

Observed:

```text
accepted=50
target_activations=12
target_suppressed=12
observed_forward_a_10=0
first_target_instruction_id=5
first_target_pc=0x010
```

Result:

```text
PASS
```

## 6. Canonical A/B Control

Canonical integrated-50 result:

```text
accepted=50
retired=50
expected_stalls=7
observed_stalls=7
flush_cycles=0
```

Authoritative canonical checker result:

```text
PASS
```

## 7. Authoritative Mutation Detection

M1-smoke must compile and execute. Compile failure, crash, timeout, or
missing target activation is not considered a valid mutation kill.
Observed mutant result:

```text
accepted=50
retired=50
target_activations=12
checker_failures=12
first_failure_instruction_id=5
first_failure_cycle=5
expected_forward_a=2'b10
observed_forward_a=2'b00
```

The authoritative checker is based on the frozen Week11 integrated
timing/forwarding expectation.
Result:

```text
M1 CAUGHT
```

## 8. First-Failure Evidence

The immutable first failure is:

```text
kind=control
checker=week11_integrated_timing
check_name=forward_a
instruction_id=5
cycle=5
pc=0x010
expected=2
observed=0
```

Evidence is recorded before the mutation verdict is evaluated.
First-failure retained state is bounded:

```text
O(1)
```

with respect to campaign length.

## 9. Waveform Evidence

Trace-enabled mutant build confirms:

```text
VM_TRACE=1
VM_TRACE_VCD=1
```

Waveform:

```text
sim_build/week12_m1_checker/week12_m1_failure.vcd
```

Observed size:

```text
274519 bytes
```

SHA-256:

```text
0365ca0de4881fb9427a093ee630f3e6789093fae85d3850bbe5ee6dddf0d6cb
```

The waveform is a diagnostic runtime artifact and is not committed to
the source tree.

## 10. Mutation Telemetry

Final mutation telemetry confirms:

```text
schema_version=week12.mutation.v1
dut_variant=m1-smoke
workload=integrated50
canonical_control_pass=True
mutant_compile_pass=True
mutant_simulation_pass=True
accepted_instructions=50
retired_instructions=50
target_activation_count=12
target_suppressed_count=12
checker_failure_count=12
authoritative_checker_failure=True
mutation_caught=True
first_target_instruction_id=5
git_dirty=False
```

Result:

```text
PASS
```

## 11. Final Regression

Frozen Week8–Week11 Python regression:

```text
608 / 608 PASS
```

Focused timing regression:

```text
research/week7/tests/test_timing_oracle_v1.py
research/week5/impl/tests/test_signal_adapter.py
```

```text
30 / 30 PASS
```

Week11 integrated RTL-50:

```text
PASS
```

Week12 unit regression:

```text
17 / 17 PASS
```

Week12 Golden58 E2E:

```text
PASS
```

Week12 M1 A/B:

```text
PASS
```

Final result:

```text
P6_REGRESSION=PASS
```

An intermediate regression-discovery command accidentally selected the
cocotb RTL file:

```text
research/week5/rtl/test_execution_stream_live.py
```

for execution under plain pytest. It produced a simulator-fixture setup
error after the actual 30 focused Python tests had passed.
The corrected focused Python contract produced:

```text
30 / 30 PASS
```

No DUT or verification semantic change was required.

## 12. Frozen-Tree Integrity

Comparison against gate-t11 shows no modifications under:

```text
design
research/week5
research/week6
research/week7
research/week8
research/week9
research/week10
research/week11
```

Final integrity:

```text
git diff --check              PASS
instruction.hex restoration  PASS
working tree cleanliness     PASS
```

## 13. Complexity

For N accepted architectural instructions:

```text
simulation/checking complexity = O(N)
```

First-failure retained state is:

```text
O(1)
```

Coverage state remains bounded by the frozen L1/L2 universes.

## 14. Gate T12 Decision

E2E conditions:

```text
accepted_58         PASS
retired_58          PASS
architectural_pass  PASS
functional_pass     PASS
performance_pass    PASS
coverage_valid      PASS
telemetry_complete  PASS
```

Therefore:

```text
E2E_PASS=True
```

Mutation conditions:

```text
canonical_control_pass         PASS
mutation_target_activated      PASS
authoritative_checker_failure  PASS
first_failure_known            PASS
waveform_saved                 PASS
```

Therefore:

```text
M1_CAUGHT=True
```

Regression:

```text
regression_pass=True
```

Therefore:

```text
T12_PASS=True
```

# PASS
