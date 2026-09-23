# Verification Utilities

This directory contains utilities inherited from the original project. The current research flow primarily uses the cocotb runners under `research/week*/rtl/`.

## Memory Image Formats

Two flows coexist and must not be confused:

1. `assembler.py` is a **legacy utility** and writes `instruction.mif`.
2. The current behavioral RAM models in `design/ramOnChip32.v` and `design/ramOnChipData.v` load:
   - root-level `instruction.hex`
   - root-level `data.hex`

Therefore, the output of `assembler.py` is **not consumed directly by the current behavioral RAM flow**. Convert/regenerate the required root-level HEX image before using the current Icarus/Verilator research runners.

The root `data.hex` may be empty; the behavioral data RAM initializes memory to zero before applying any contents present in that file.

## Legacy ModelSim/Questa Flow

The files `compile_verilog` and `runtb_top` are retained as a legacy interactive simulation flow.

Run ModelSim/Questa **from the repository root**:

```tcl
do verif/runtb_top
```

`verif/compile_verilog` uses repository-relative paths. The RAM implementation currently committed in `design/` is behavioral and does not require the historical Altera memory-IP library.

## Research Flow

For reproducible research regressions, prefer the versioned runners, for example:

```bash
research/week8/rtl/run_week8_case.sh T01
```

Do not invoke cocotb test modules such as `test_week8_live.py` directly with pytest; the `dut` object is provided only when cocotb is launched by the simulator harness.
