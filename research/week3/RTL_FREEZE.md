# RTL Freeze — Gate T3

## Frozen baseline

Tested commit:

`e0c1ae1e35f55630fd27116a19af53a19c5243bd`

Baseline tag:

`DUT_BASELINE_T3`

## Freeze rationale

The candidate passed:

1. independent three-instruction ADDI smoke;
2. automated architectural checking;
3. waveform-level reset, PC, fetch, stall and pipeline inspection.

Expected and observed state:

- x1 = 5
- x2 = 7
- x3 = 3

## Freeze boundary

The following RTL is considered frozen after Gate T3:

- `design/`
- DUT-related files under `verif/`

No direct RTL modification is allowed after this gate without the
Controlled Change procedure below.

## Controlled Change Procedure

Any RTL change after T3 requires:

1. reproducible failing test;
2. bug report;
3. expected versus actual behavior;
4. first failing cycle/stage;
5. relevant waveform evidence;
6. root-cause hypothesis;
7. minimal RTL patch;
8. regression of all previously passing tests;
9. updated baseline/version if RTL changes are accepted.

## Required regression

At minimum:

- Week-2 RAW Program B;
- Week-3 independent smoke3;
- the new test reproducing the discovered bug.

## Claim limitation

This freeze establishes a stable DUT baseline, not complete functional
verification of the processor.
