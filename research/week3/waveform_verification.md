# Week 3 Smoke Waveform Verification

## Test
- addi x1, x0, 5
- addi x2, x0, 7
- addi x3, x0, 3

## Observations

| Check | Result |
|---|---|
| Reset initialization | PASS |
| PC sequence 0x000, 0x004, 0x008, ... | PASS |
| Instruction fetch order correct | PASS |
| Unexpected stall | NONE |
| Pipeline A/B/C/D progresses | PASS |
| Self-check x1=5, x2=7, x3=3 | PASS |

## Conclusion

The independent-instruction smoke test passes at both architectural
and microarchitectural levels. No RAW dependency exists in this test,
and no unexpected stall is observed.
