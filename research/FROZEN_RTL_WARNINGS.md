# Frozen RTL Warning Register

## Purpose

This document records simulator/lint warnings observed on the frozen DUT baseline. The warnings are documented rather than repaired because the research methodology requires the DUT to remain unchanged after Gate T3.

Baseline invariant:

- `design/*` is frozen after `DUT_BASELINE_T3`.
- verification infrastructure may classify or expose DUT behavior;
- maintenance work must not silently repair the DUT.

## Observed Verilator Baseline

Observed with Verilator 5.034 during the Gate-T8 live regression.

### W1 — `imm_Gen.sv` width expansion

Location: `design/imm_Gen.sv`, SRAI immediate path.

The conditional true branch:

```systemverilog
{7'b0, inst_code[24:20]}
```

is 12 bits wide while `Imm_out` is 32 bits.

Verilator reports `WIDTHEXPAND` and expands the value to the destination width.

**Risk:** implicit width extension makes the intended 32-bit representation tool-dependent in presentation and weakens lint cleanliness.

**Research handling:** documented only; no DUT modification.

### W2 — `datamemory.sv` address width expansion

Locations:

```systemverilog
raddress = {{22{1'b0}}, a};
waddress = {{22{1'b0}}, {a[8:2], {2{1'b0}}}};
```

With 9-bit `a`, both right-hand expressions are 31 bits while the destinations are 32 bits.

Verilator reports `WIDTHEXPAND`.

**Risk:** implicit zero-extension is relied upon.

**Research handling:** documented only; no DUT modification.

### W3 — nonblocking assignment in combinational logic

`design/datamemory.sv` uses nonblocking assignments such as:

```systemverilog
rd <= ...
Wr <= ...
Datain <= ...
```

inside an `always @*` combinational process.

Verilator reports `COMBDLY` and states that these assignments are executed as blocking assignments.

**Risk:** simulator portability. Different scheduling semantics can produce tool-dependent behavior, especially if a checker relies on delta-cycle timing around these combinational outputs.

**Research handling:** the verification timing contract avoids same-active-edge assumptions and samples at controlled phases. The DUT remains frozen.

## Status

These warnings are **known baseline technical debt**, not generated-file hygiene issues and not missing stimulus.

They must not be suppressed in a way that hides new warnings. If the DUT is intentionally revised in a future post-baseline experiment, fixes should be isolated to a separate DUT-revision branch and evaluated against the frozen baseline.
