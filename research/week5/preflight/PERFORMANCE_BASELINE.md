# WEEK-5 PERFORMANCE PREFLIGHT BASELINE

## 1. Purpose

This artifact records the Week-5 Cocotb/Verilator framework throughput
microbenchmark before Adaptive CGS pilot configuration is frozen.

This benchmark measures simulator/Python interaction overhead using the
minimal `week4_counter` RTL fixture.

It is not yet the final full-DUT campaign throughput estimate.

---

## 2. Environment

Repository:

`/home/logan/nckh/RISC-V-Pipeline`

Filesystem:

`ext4`

Simulator:

`Verilator 5.034`

Cocotb:

`1.9.2`

Python:

`3.10.12`

Waveform tracing was disabled.

Per-cycle disk and console logging were disabled inside the measured
loop.

---

## 3. Benchmark Configuration

Each measured run executed:

`100,000 cycles`

Two configurations were measured.

### Baseline

One Cocotb coroutine wake-up per rising edge.

No monitored signal was read inside the measured loop.

### Simple monitor

One rising-edge wake-up followed by:

`ReadOnly()`

and one signal read per simulated cycle.

Three measured repetitions were collected for each configuration.

---

## 4. Raw Results

### Baseline

| Run | Wall time (s) | Throughput (cycles/s) |
| --- | ------------: | --------------------: |
| 1   |      5.963437 |             16768.853 |
| 2   |      5.322683 |             18787.518 |
| 3   |      5.345167 |             18708.491 |

Mean wall time:

`5.543762 s`

Wall-time standard deviation:

`0.363623 s`

Mean throughput:

`18088.287 cycles/s`

Throughput standard deviation:

`1143.347 cycles/s`

---

### Simple monitor

| Run | Wall time (s) | Throughput (cycles/s) |
| --- | ------------: | --------------------: |
| 1   |      7.821992 |             12784.467 |
| 2   |      6.707632 |             14908.391 |
| 3   |      6.780077 |             14749.096 |

Mean wall time:

`7.103234 s`

Wall-time standard deviation:

`0.623516 s`

Mean throughput:

`14147.318 cycles/s`

Throughput standard deviation:

`1182.948 cycles/s`

---

## 5. Monitor Overhead

Using the mean measured wall times:

`overhead = (T_monitor - T_baseline) / T_baseline`

gives:

`28.13%`

Thus even a minimal settled Cocotb signal monitor introduces a
measurable framework-level cost.

This supports the frozen logging rule that per-cycle I/O and unnecessary
monitor work must be avoided in comparative campaigns.

---

## 6. Variability

The baseline throughput coefficient of variation is approximately:

`6.32%`

The simple-monitor throughput coefficient of variation is approximately:

`8.36%`

The first repetition of both benchmark modes is slower than the
subsequent repetitions.

This is consistent with a possible warm-up / host-state effect, but the
current experiment is insufficient to attribute the cause.

The first runs are therefore retained in the reported statistics.

---

## 7. Protocol for Subsequent Full-DUT Measurements

For subsequent throughput characterization, the measurement procedure
is pre-registered as:

1. build the DUT once;
2. execute one warm-up run that is not included in the reported
   statistics;
3. execute at least three measured repetitions;
4. use the same simulator, filesystem, waveform, and logging settings;
5. report mean and standard deviation;
6. retain raw logs.

The warm-up exclusion is defined before observing the full-DUT
measurement results.

---

## 8. Interpretation Boundary

This microbenchmark establishes:

* Cocotb/Verilator framework throughput;
* incremental cost of a simple settled monitor;
* host-level run-to-run variability.

It does not establish:

* full pipeline DUT throughput;
* scoreboard overhead;
* functional coverage collector overhead;
* Adaptive CGS overhead;
* final campaign runtime.

Therefore Adaptive CGS pilot-grid size shall not be frozen solely from
this microbenchmark.

A full-DUT throughput measurement is required first.

---

## 9. Framework Microbenchmark Checkpoint

Framework microbenchmark:

`PASS`

At this checkpoint, the full-DUT throughput baseline had not yet been
measured.

That dependency was subsequently resolved by the full-DUT benchmark
documented in Sections 10–13.

Full-DUT throughput baseline:

`RESOLVED — PASS`

## 10. Full-DUT Throughput Baseline

After the framework microbenchmark, throughput was measured using the
complete `riscv` RTL hierarchy.

The measurement retained the same environment:

* Verilator 5.034;
* Cocotb 1.9.2;
* Python 3.10.12;
* Linux-native ext4 filesystem;
* waveform tracing disabled;
* no per-cycle disk or console logging.

The DUT used the repository-local `instruction.hex` and `data.hex`
memory images.

The measurement protocol was pre-registered as:

1. one warm-up run excluded from statistics;
2. three measured repetitions;
3. 100,000 simulated cycles per run.

### Full-DUT Baseline

Measured runs:

| Run | Wall time (s) | Throughput (cycles/s) |
| --- | ------------: | --------------------: |
| 1   |      6.044995 |             16542.611 |
| 2   |      5.324711 |             18780.364 |
| 3   |      5.518618 |             18120.480 |

Mean wall time:

`5.629441 s`

Wall-time standard deviation:

`0.372711 s`

Mean throughput:

`17814.485 cycles/s`

Throughput standard deviation:

`1149.830 cycles/s`

Throughput coefficient of variation:

`6.45%`

### Full-DUT Simple Monitor

Measured runs:

| Run | Wall time (s) | Throughput (cycles/s) |
| --- | ------------: | --------------------: |
| 1   |      8.262041 |             12103.547 |
| 2   |      8.022836 |             12464.420 |
| 3   |      7.810280 |             12803.638 |

Mean wall time:

`8.031719 s`

Wall-time standard deviation:

`0.226011 s`

Mean throughput:

`12457.202 cycles/s`

Throughput standard deviation:

`350.101 cycles/s`

Throughput coefficient of variation:

`2.81%`

### Full-DUT Monitor Overhead

Using measured mean wall times:

`overhead = (8.031719 - 5.629441) / 5.629441`

therefore:

`monitor overhead = 42.67%`

The corresponding mean throughput reduction is approximately:

`30.07%`

The monitor result is more stable than the baseline measurement across
the three measured repetitions.

---

## 11. Interpretation

The full-DUT result establishes that simulator throughput remains on the
order of:

`10^4 cycles/s`

under lightweight Cocotb monitoring.

The simple monitor is not equivalent to the future complete
scoreboard, coverage collector, or Adaptive CGS implementation.

Therefore the measured throughput is used for feasibility planning,
not as a prediction of final comparative-campaign wall time.

The final verification stack may be slower because it will perform:

* pre-edge and post-edge observations;
* dependency reconstruction;
* scoreboard processing;
* L1/L2 coverage classification;
* adaptive-policy updates;
* checkpoint telemetry.

---

## 12. Adaptive CGS Pilot Feasibility Decision

The candidate space is:

`epsilon in {0.05, 0.10, 0.20}`

`alpha in {0.1, 0.3, 0.5}`

`batch_size in {500, 1000, 2000}`

The complete Cartesian product contains:

`3 × 3 × 3 = 27 configurations`

The full-DUT throughput preflight does not provide evidence that this
search space must be reduced for computational reasons.

Therefore the Week-5 pre-registration shall retain the complete
27-configuration Cartesian search space.

Pilot execution shall use:

`3 fixed pilot seeds per configuration`

and a maximum budget of:

`100,000 executed instructions per seed`

Thus the maximum pilot design contains:

`27 × 3 = 81 runs`

and:

`8,100,000 executed instructions`

before accounting for pipeline-cycle overhead.

The 3 pilot seeds are used only for hyperparameter selection and shall
be fixed before observing pilot coverage results.

No candidate value may be introduced or removed after pilot coverage
results have been observed.

---

## 13. Preflight Status

Framework throughput baseline:

`PASS`

Full-DUT throughput baseline:

`PASS`

Linux-native filesystem contract:

`PASS`

Logging/I/O preflight:

`PASS`

Adaptive CGS Cartesian-grid feasibility:

`PASS`

Performance preflight status:

`PASS / COMPLETE`
