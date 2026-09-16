# Week 4 — Scheduler Race Demonstration

## 1. Environment

| Component | Version |
|---|---|
| Python | 3.10.12 |
| Cocotb | 1.9.2 |
| Icarus Verilog | 11.0 |
| Verilator | 5.034 |
| Clock period | 10 ns |

## 2. Probe DUT

The experiment uses an independent 8-bit synchronous counter instead
of the frozen RISC-V DUT.

The counter updates on `posedge clk` using a nonblocking assignment:

`count <= count + 1`

when `en = 1`.

Using a dedicated probe isolates scheduler behavior from the
microarchitecture of the RISC-V processor.

## 3. Experiment E1 — Drive at RisingEdge

The testbench changes `en` in the same simulation timestamp as the
active edge sampled by the DUT.

Observed results:

| Simulator | first | second |
|---|---:|---:|
| Icarus 11.0 | 1 | 2 |
| Verilator 5.034 | 1 | 2 |

Both tested simulators produced the same observation.

However, this result is not treated as a portable scheduling contract,
because the stimulus is applied at the same active edge as the DUT
sampling event.

## 4. Experiment E2 — Drive at FallingEdge

The input is driven at `FallingEdge(clk)` and is therefore stable before
the next active sampling edge.

Observed results:

| Simulator | first | second |
|---|---:|---:|
| Icarus 11.0 | 1 | 1 |
| Verilator 5.034 | 1 | 1 |

The observed behavior matches the expected deterministic timing model.

## 5. Experiment E3 — Sampling Phase

The counter is sampled twice around one rising-edge event:

1. immediately after `RisingEdge`;
2. after `ReadOnly`.

Observed results:

| Simulator | Immediate | After ReadOnly |
|---|---:|---:|
| Icarus 11.0 | 0 | 1 |
| Verilator 5.034 | 0 | 1 |

Therefore, waking on `RisingEdge` alone does not guarantee that the
sequentially updated state is suitable for monitor/checker observation.

## 6. Waveform evidence

Signals:

- `clk`
- `rst_n`
- `en`
- `count[7:0]`

Artifacts:

- `waveforms/week4_race.vcd`
- `waveforms/week4_race.gtkw`
- `logs/icarus_timing.log`
- `logs/verilator_timing.log`

## 7. Conclusion

Normal verification stimulus must not depend on same-active-edge
scheduling behavior.

The verification environment therefore adopts:

- functional input drive away from the DUT active sampling edge;
- sequential observation after `RisingEdge` followed by `ReadOnly`.

The identical same-edge result obtained from the two tested simulators
does not prove that this behavior is portable to other simulators,
versions, or callback implementations.
