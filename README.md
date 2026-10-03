# Coverage Saturation and Adaptive Test Generation for RISC-V

Research on coverage saturation dynamics and adaptive test generation
for data hazard verification in a 5-stage RISC-V processor.

This project investigates how different stimulus-generation strategies
explore a defined hazard-coverage space, how coverage growth slows near
closure, and whether coverage feedback can improve verification efficiency.

The research combines functional checking, pipeline timing checks,
coverage analysis, and reproducible experiments on a frozen DUT.

## Research Objectives

The project aims to:

- Build a self-checking verification environment for a 5-stage RV32I processor.
- Define a layered coverage model for data hazards and their handling mechanisms.
- Study coverage growth, saturation, and long-tail closure.
- Compare directed, random, weighted-random, and adaptive stimulus generation.
- Evaluate verification cost in terms of instruction budget and wall-clock time.
- Assess checker effectiveness through controlled fault injection and mutation testing.

Adaptive stimulus generation is evaluated as a research hypothesis.
Improvement over the comparison methods is not assumed.

## Verification Approach

### Functional and Pipeline Timing Checks

The verification environment checks both architectural results and
pipeline timing behavior within the declared research scope.

Functional checking compares observed architectural behavior against
an independent reference model.

Pipeline timing checks examine expected stalls and cycle gaps between
retirement events. These checks target cases where architectural results
remain correct but unnecessary stalls or timing deviations occur.

### Coverage Model

The coverage model describes the selected data-hazard scenarios,
instruction dependencies, and relevant pipeline responses.

Coverage objectives are accompanied by scope definitions and
reachability analysis. Coverage completion is interpreted relative
to this model; it does not establish complete processor correctness.

### Stimulus Generation

| Method | Role |
|---|---|
| Directed | Exercise selected scenarios and confirm specific defects |
| Pure Random | Provide a non-adaptive random baseline |
| Static Weighted Random | Bias generation using fixed sampling weights |
| Adaptive Coverage-Guided Stimulus | Adjust stimulus selection using coverage feedback |

Adaptive CGS organizes stimulus templates into hazard-related groups.
Coverage gains contribute to a reward signal used to update selection
preferences while balancing exploration and exploitation.

The adaptive policy uses an epsilon-greedy multi-armed-bandit approach.
Its effectiveness is evaluated under explicitly frozen experimental conditions.

## Experimental Evaluation

The research examines:

- Coverage accumulation over the instruction budget.
- Progress near saturation and the effort required to close remaining bins.
- Variability across independently initialized runs.
- Simulation and feedback-processing costs.
- Detection of functional and pipeline timing defects.

Experimental contracts define the method configurations, seed sets,
budgets, metrics, and statistical procedures for each campaign.

The proposal describes the intended research scope. Versioned contracts
and experimental records document what was implemented, executed, and accepted.

Results are limited to the selected DUT, coverage model, generators,
configurations, and experimental conditions. They do not establish
universal superiority of an adaptive or non-adaptive method.

## DUT Baseline and Scope

The project builds on an existing pipelined RISC-V SystemVerilog core.

The DUT is frozen so verification methods can be compared against a stable
design. Documented defects are intentionally preserved as part of this
research baseline.

The project does not claim complete RV32I correctness. Supported
instructions, hazard scenarios, exclusions, and known defects are
defined in the verification plan and associated research records.

## Repository Organization

| Directory | Contents |
|---|---|
| `design/` | Frozen SystemVerilog DUT |
| `research/` | Research implementation, verification plans, coverage models, experiments, and evidence |
| `verif/` | Original verification utilities and testbench |
| `tests/` | Scheduler and timing probes |
| `sim/` | Simulation examples and runtime outputs |
| `doc/` | Original project documentation |

Experiment-specific configurations, runners, and evidence are maintained
under `research/`. Their availability depends on the selected source revision.

## Reproducibility

Experiments are tied to recorded source revisions, tool versions,
configurations, seeds, and execution budgets.

To reproduce an experiment:

1. Select its documented source revision.
2. Follow the corresponding environment manifest.
3. Use the experiment-specific runner and configuration.
4. Compare outputs against the applicable acceptance criteria.

Python checks and live RTL simulations use different entry points.
Launch cocotb tests through their simulator runners.

Preserve committed logs, manifests, experimental records, and curated waveforms.
Ordinary runtime outputs should be written to the designated ignored
directories.

## Research Deliverables

The planned deliverables include:

- An automated verification environment.
- A documented hazard-coverage model and verification plan.
- An Adaptive CGS implementation and comparison methods.
- Experimental datasets and analysis utilities.
- Fault-injection and mutation-testing evidence.
- Reproduction instructions and a final research report.

## Upstream Acknowledgements

The DUT derives from
[estufa-cin-ufpe/RISC-V-Pipeline](https://github.com/estufa-cin-ufpe/RISC-V-Pipeline),
with original contributors
[joaopmarinho](https://github.com/joaopmarinho) and
[nathaliafab](https://github.com/nathaliafab).

The upstream project also acknowledges
[Yifan Xu's RISC-V-PipeLine](https://github.com/yifax/RISC-V-PipeLine).

This repository adds the verification-research framework while preserving
upstream attribution and the frozen DUT baseline.
