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

## 9. Status

Framework microbenchmark:

`PASS`

Full-DUT throughput baseline:

`PENDING`
