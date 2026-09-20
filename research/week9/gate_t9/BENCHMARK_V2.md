# Week 9 — Benchmark v2

## Configuration

Simulator: Verilator 5.034
Cocotb: 1.9.2

Runs:

    5 repetitions
    100,000 cycles per repetition

Verification path includes bounded streaming:

- Timing Oracle v1 equivalent;
- functional checking equivalent to frozen Week-8 semantics;
- performance checking equivalent to frozen Week-8 semantics;
- L1 Intent coverage;
- L2 Intent coverage;
- Week-9 checkpoint coverage state.

L2 Validated promotion is intentionally excluded because the frozen
L2 RealizationValid contract is unresolved. See:

    L2_VALIDATION_SPEC_GAP.md

## Results

| Rep | cycles/s | instructions/s | RSS delta KiB | first->second degradation |
|---:|---:|---:|---:|---:|
| 1 | 4800.267 | 3200.242 | 280 | 0.143% |
| 2 | 5100.444 | 3400.364 | 296 | -15.215% |
| 3 | 5212.243 | 3474.898 | 280 | -0.869% |
| 4 | 5330.407 | 3553.676 | 284 | 1.525% |
| 5 | 5215.072 | 3476.784 | 284 | -4.182% |

Median:

    cycles/s                    = 5212.243
    instructions/s              = 3474.898
    throughput degradation      = -0.869%
    RSS start->mid delta         = 264 KiB
    RSS start->end delta         = 284 KiB
    slowdown vs T5 minimal       = 70.821%
    slowdown vs T5 monitor       = 62.566%

Each run executed:

    100,000 cycles
    66,668 executed instructions

## Correctness

Across all five runs:

    functional_failures  = 0
    performance_failures = 0

Maximum retained transient state:

    performance expectations <= 3
    functional expectations  <= 3

Golden-model long-run data-memory footprint is bounded by the fixed
benchmark address set.

## Memory assessment

Median RSS growth:

    start -> midpoint = 264 KiB
    start -> end      = 284 KiB

Therefore the second half contributes approximately:

    284 - 264 = 20 KiB

additional median RSS despite executing approximately another half of
the campaign.

Together with the explicit <=3 in-flight state bounds, the measurement
does not show near-linear retained-state growth with campaign length.

## Throughput assessment

Median first-to-second-half degradation is:

    -0.869%

A negative value means the measured second half was slightly faster
than the first half.

Therefore no progressive throughput degradation with campaign length
was observed.

The absolute instrumentation overhead remains substantial:

    70.821% slowdown versus T5 minimal baseline
    62.566% slowdown versus T5 monitor baseline

This overhead must be reported as a verification-economics result and
must not be hidden.

## Runtime estimate

At median throughput:

    100,000 / 3474.898
        ~= 28.78 seconds

for 100,000 executed instructions under this benchmark workload.

This estimate is workload- and environment-specific and is not a
replacement for the final stochastic campaign runtime measurement.
