# Gate T3 — Baseline Verdict

## Tested candidate

Commit:

`e0c1ae1e35f55630fd27116a19af53a19c5243bd`

## Test program

Three independent RV32I instructions:

```asm
addi x1, x0, 5
addi x2, x0, 7
addi x3, x0, 3
```

The three instructions are intentionally data-independent.
Therefore no RAW dependency is required for correctness of this test.

## Expected architectural state

| Register | Expected |
|---|---:|
| x1 | 5 |
| x2 | 7 |
| x3 | 3 |

## Actual result

| Register | Actual | Result |
|---|---:|---|
| x1 | 5 | PASS |
| x2 | 7 | PASS |
| x3 | 3 | PASS |

Automated checker exit status: 0.

## Waveform observations

| Check | Result |
|---|---|
| Reset initialization | PASS |
| PC progresses 0x000, 0x004, 0x008, ... | PASS |
| Instruction fetch order | PASS |
| Unexpected stall | NONE |
| IF/ID → ID/EX → EX/MEM → MEM/WB progression | PASS |
| Architectural self-check | PASS |

Observed instruction sequence:

- 0x00500093
- 0x00700113
- 0x00300193

## Evidence

- `gateT3_smoke.log`
- `check_smoke3.py`
- `waveform_verification.md`
- `waveforms/smoke3.vcd`
- `waveforms/smoke3.gtkw`
- `diagnostic_tree.md`

## Scope of the claim

Gate T3 demonstrates correct baseline execution of three independent
ADDI instructions through the current five-stage datapath.

Gate T3 does NOT establish complete correctness of:

- all RV32I instructions;
- forwarding combinations;
- load-use hazard handling;
- branch/jump handling;
- memory operations;
- flush behavior.

## Verdict

**PASS**

The tested candidate successfully executes the independent-instruction
smoke test and commits the expected architectural state.
