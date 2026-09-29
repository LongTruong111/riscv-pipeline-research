# Gate T13 — Week 13 Closure

**Status:** PASS

**Evidence HEAD:** `4d5aa07cc4db770485f02f66d2cce7b81ddbf102`
**Frozen DUT:** `595ed75dcf8544c4f7ab3f16966df34ba1c11ee7`
**Protocol revision:** `fa906a3f8c6630c6e41d9321d79b2c408d04adc5`

## Adaptive hyperparameter selection

The official 81-run pilot completed 81/81 fixed-budget runs across
27 configurations and seeds 13001, 13002, and 13003.

Selected configuration:

- epsilon = 0.10
- alpha = 0.5
- Q_floor = 0.05
- nominal batch = 500
- median normalized L2-Intent AUC = 0.161290322580645
- median L2 Intent bins at N=10000 = 20
- median wall time = 7.045591553 s

Selection follows the frozen rule:
median AUC, then median L2 bins at N=10000; configurations within
the frozen tie condition are resolved by lower median wall time,
larger batch, smaller epsilon, then smaller alpha.

## Full-system performance benchmark

| Method | Median wall / 10k | Median accepted/s | Median cycles/s | Median peak RSS |
| --- | ---: | ---: | ---: | ---: |
| M1 Pure Random | 7.354873945 s | 1359.643 | 1884.601 | 45080 KiB |
| M3 Adaptive selected | 7.045591553 s | 1419.327 | 1419.327 | 38144 KiB |

The benchmark window is the full-system pilot window defined by the
Week-13 protocol. Compilation/elaboration is outside this window.

## Runtime planning estimate

Linear scaling from the median 10k pilot wall time gives:

| Campaign component | Estimate |
| --- | ---: |
| M1, one 100k run | 73.549 s |
| M1, 15 runs | 18.387 min |
| M3, one 100k run | 70.456 s |
| M3, 15 runs | 17.614 min |
| M1 + M3, 30 runs | 36.001 min |

These values are planning estimates only. They are not measured
100k benchmark results and do not include the future M2 Weighted
Random campaign.

## Coverage reachability

PASS. Official M1 pilot seed 11002 reached 62/62 L2 Intent bins.
Therefore no L2 bin in the frozen coverage model remains unexplained
as dead or unreachable at Gate T13.

## Mutation gate

MUT-M1: PASS.

- canonical control passed
- target activations = 12
- checker failures = 12
- first failure instruction = 5
- authoritative checker caught the forwarding mutation

MUT-M2-x0: PASS.

- canonical target activation = 1
- canonical checker failures = 0
- canonical Forward_A = 00
- mutant target activation = 1
- mutant checker failures = 1
- mutant Forward_A = 10
- first failure = week5_h18_control / forward_a_x0_exclusion

MUT-M2-x0 is the mutation identifier; it is not the comparative
method M2 Weighted Random.

## Known non-blocking debt

Verilator WIDTHEXPAND and COMBDLY warnings remain in the frozen RTL.
They are retained as known warning debt and do not alter the frozen
DUT revision for the Week-13 campaign.

## Gate decision

All Gate T13 requirements are satisfied:

Adaptive configuration is selected and frozen; full-system pilot
throughput is measured; final-campaign runtime has a documented
planning estimate; MUT-M1 and MUT-M2-x0 are caught by authoritative
checkers; and the L2 coverage model has a 62/62 reachability witness.

**GATE T13 = PASS**
