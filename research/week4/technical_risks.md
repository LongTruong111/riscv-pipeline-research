# Week 4 — Technical Risks

## R1 — Potential HazardDetection false positive

### Observation

The current HazardDetection equation compares:

ID_EX_rd == IF_ID_RS1
or
ID_EX_rd == IF_ID_RS2

whenever ID_EX_MemRead is asserted.

### Potential edge cases

1. ID_EX_rd = x0.
2. IF/ID instruction formats where bits [24:20] are not semantically
   an rs2 source operand.

### Current classification

HYPOTHESIS — not a confirmed DUT bug.

### Required validation

Directed tests are required before classifying the behavior as a bug.

### Change policy

No RTL change is made because DUT_BASELINE_T3 is frozen.
