# Week 3 Diagnostic Tree

## Purpose

Localization procedure for failures of the independent-instruction
smoke test.

The test program is:

- addi x1, x0, 5
- addi x2, x0, 7
- addi x3, x0, 3

Because all three instructions read x0, no RAW dependency is expected.

---

## Diagnostic flow

SMOKE3 FAIL
|
+-- [0] Instruction stream correct at IMEM output?
|      Signal: dp.instr_mem.get_dataOut
|      Expected:
|        0x00500093
|        0x00700113
|        0x00300193
|
+-- NO
|      Check:
|        - instruction.hex replacement
|        - byte order
|        - $readmemh loader
|        - instruction memory addressing
|
+-- YES
       |
       +-- [1] PC progresses correctly?
       |      Signal: dp.pcreg.q
       |
       +-- NO
       |      Check:
       |        - reset
       |        - PC register
       |        - PC update path
       |
       +-- YES
              |
              +-- [2] Unexpected stall?
              |      Signal: dp.detect.stall
              |      Expected: 0
              |
              +-- YES
              |      Suspect:
              |        - HazardDetection false positive
              |
              +-- NO
                     |
                     +-- [3] IF/ID correct?
                     |      Pipeline register: dp.A
                     |
                     +-- [4] ID/EX correct?
                     |      Pipeline register: dp.B
                     |
                     +-- [5] EX/MEM correct?
                     |      Pipeline register: dp.C
                     |
                     +-- [6] MEM/WB correct?
                     |      Pipeline register: dp.D
                     |
                     +-- [7] Write-back correct?
                            Check:
                              - D.RegWrite
                              - D.rd
                              - write-back value
                              - RegFile write

## Localization rule

Identify the earliest pipeline stage where:

actual != expected

Do not debug later stages until the first failing stage is identified.
