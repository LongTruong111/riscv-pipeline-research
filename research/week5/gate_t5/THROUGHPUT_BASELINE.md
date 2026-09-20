# Week-5 Cocotb Throughput Baseline

Environment:

see `ENVIRONMENT_MANIFEST.txt`.

Benchmark configuration:

- Simulator: Verilator 5.034
- Cocotb: 1.9.2
- Cycles per run: 100,000
- Repetitions per mode: 5
- Waveform dumping: disabled
- Per-cycle CSV logging: disabled
- Workspace: Linux-native filesystem

## Minimal

| Rep | cycles/s |
|---:|---:|
| 1 | 17666.540 |
| 2 | 18192.401 |
| 3 | 17302.070 |
| 4 | 18413.391 |
| 5 | 17862.941 |

Median:

`17862.941 cycles/s`

## Simple monitor

| Rep | cycles/s |
|---:|---:|
| 1 | 12671.034 |
| 2 | 13769.556 |
| 3 | 14001.755 |
| 4 | 13937.403 |
| 5 | 13923.913 |

Median:

`13923.913 cycles/s`

## Monitor overhead

Using median throughput:

`slowdown = 1 - 13923.913 / 17862.941`

Therefore:

`monitor slowdown = 22.05%`

The monitor mode is therefore measurably more expensive than the
minimal Cocotb loop and wall-clock overhead must be reported separately
from instruction efficiency.

## Pilot schedule decision

Full Cartesian search:

`3 epsilon × 3 alpha × 3 batch sizes = 27 configurations`

Pilot seeds:

`3`

Per-configuration budget:

`10,000 executed instructions / seed`

Maximum pilot instruction budget:

`810,000 executed instructions`

Using the measured monitor median as the conservative simulation-rate
baseline, the full-grid search is comfortably below the pre-registered
8-hour engineering threshold.

Selected schedule:

`FULL_GRID`

This decision was made from throughput engineering measurements before
observing Adaptive-CGS pilot coverage results.

The measured cycles/s baseline is not itself an instruction/s estimate;
actual Adaptive-CGS runs may incur additional CPI and Python-side
generation/coverage overhead.

## Raw Evidence

Raw benchmark logs are retained in:

`research/week5/gate_t5/throughput_logs/`
