# TIMING_RULES v2

These rules define the timing contract for the verification environment
after Gate T4.

## TR1 — Functional stimulus drive

Synchronous DUT inputs are normally driven at:

`FallingEdge(clk)`

before the next active `RisingEdge(clk)` sampled by the DUT.

Normal functional stimulus must not be driven at the same active edge
used by the DUT for sequential sampling.

## TR2 — Sequential observation

Sequential DUT state is sampled using:

```python
await RisingEdge(clk)
await ReadOnly()
```

`RisingEdge` alone is not considered a settled observation point.

Experimental evidence:

- immediate sample = 0
- after `ReadOnly` = 1

for both Icarus Verilog 11.0 and Verilator 5.034.

## TR3 — Reset

Reset is asserted for at least three complete clock cycles.

Reset deassertion occurs at `FallingEdge(clk)` so that reset is stable
before the following active edge.

## TR4 — Clock ownership

Each clock signal has exactly one clock generator.

Multiple concurrent verification processes must not drive the same
clock.

## TR5 — Same-timestamp feedback

A verification component must not:

1. observe a DUT result; and
2. drive a dependent functional input

within the same simulation timestamp unless the test explicitly studies
scheduler behavior.

## TR6 — Shared timing infrastructure

Clock, reset, normal input drive, and settled sampling use the common
helpers in:

`tests/timing_utils.py`

Individual tests should not duplicate their own timing rules.

## Portability statement

Same-RisingEdge stimulus produced `first=1, second=2` on both tested
simulators.

This agreement is an experimental observation only and is not treated
as a portable simulator-independent contract.

The verification environment intentionally avoids dependence on this
ordering.
