# RISC-V Pipeline Verification Research

This repository extends an existing pipelined RISC-V SystemVerilog core with a staged verification-research workflow. The DUT is intentionally frozen after Gate T3 so later work can evaluate verification methods against a stable baseline rather than silently repairing observed defects.

## Current Research State

The active research line has progressed through:

- **Gate T3** — DUT reconnaissance, independent smoke validation, and RTL freeze.
- **Week 4** — simulator scheduling/timing contract and race experiments.
- **Gate T5** — hazard-space definition, executable coverage model, directed realization checks, and performance preflight.
- **Gate T6** — independent Golden Functional Model and bounded Timing Oracle v0.
- **Gate T7** — Timing Oracle v1, retire monitoring, hazard attribution, and reset-boundary validation.
- **Gate T8** — independent Functional Scoreboard, Performance Monitor, and cross-verdict classification.

Gate-closure evidence is kept under `research/week*/`. The frozen DUT is under `design/`.

## Important Baseline Constraint

The project does **not** claim that every implemented RV32I instruction is defect-free. The research baseline deliberately retains known DUT defects so the verification environment can detect and classify them.

The frozen known defect set currently includes:

- H11
- H13
- H18
- H19
- H20

See `research/week5/rtl/CONTROL_REALIZATION_FINDINGS.md` and later gate-closure documents for the evidence and attribution.

## Repository Layout

```text
design/                 Frozen SystemVerilog DUT
verif/                  Legacy/original verification utilities and testbench
sim/                    Original simulation examples + ignored runtime outputs
tests/                  Week-4 scheduler/timing probe
research/
  rtl_audit/             RTL reconnaissance
  signals/               Signal inventory and observability work
  waveforms/             Curated historical waveform evidence
  week3/                 Smoke validation + DUT freeze evidence
  week4/                 Timing/race contract
  week5/                 vPlan, coverage, directed realization, preflight
  week6/                 Golden functional model + Timing Oracle v0
  week7/                 Timing Oracle v1 + retire/attribution monitors
  week8/                 Functional/performance scoreboard integration
```

Generated build products, Python caches, simulator result XML, and ordinary runtime waveforms are intentionally ignored.

## Python Regression

Python 3.10 is the frozen development baseline.

```bash
python3 -m pip install -r requirements.txt
pytest research/week5/impl/tests -q
pytest research/week6/tests -q
pytest research/week7/tests -q
pytest research/week8/tests -q
```

The Gate-T8 baseline recorded:

```text
Week 5: 142 passed
Week 6: 64 passed
Week 7: 40 passed
Week 8: 36 passed
```

These counts are historical gate evidence; rerun the commands above after any maintenance change.

## Live RTL Regression

Live RTL tests are cocotb tests and must be launched through their simulator runners, not by invoking the cocotb test modules directly with pytest.

Gate T8 directed live cases:

```bash
for c in T01 T11 T19 T20; do
    research/week8/rtl/run_week8_case.sh "$c"
done
```

Expected classification coverage:

- T01: `CORRECT_ON_TIME`
- T11: `FUNCTIONAL_ONLY_FAIL`
- T19: `PERFORMANCE_ONLY_FAIL`
- T20: `PERFORMANCE_ONLY_FAIL`

The runners mutate the root `instruction.hex` only temporarily and restore it on exit. Because that file is shared, live RTL cases must be run **sequentially**, not in parallel.

## Runtime vs. Evidence Artifacts

Runtime simulator outputs belong in ignored locations such as `sim/` or `sim_build/`.

Curated logs and waveforms already committed under `research/` are historical experimental evidence and should not be overwritten by ordinary regression runs.

## Tool Baseline

The recorded Week-5 environment includes:

- Ubuntu 22.04 / WSL2
- Python 3.10.12
- cocotb 1.9.2
- pytest 8.3.2
- Icarus Verilog 11.0
- Verilator 5.034

See `research/week5/gate_t5/ENVIRONMENT_MANIFEST.txt` for the complete captured environment.

## Upstream Provenance

This repository is based on the pipelined RISC-V implementation by the original project contributors and the earlier work acknowledged by that project. The research layer in `research/` is additive and preserves the DUT baseline for verification experiments.

## Scope

The research claims are limited to the explicitly declared verification scope in the versioned vPlan and gate documents. They should not be interpreted as proof of complete RV32I correctness.
