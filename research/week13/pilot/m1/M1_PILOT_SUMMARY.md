# Week 13 M1 Pure Random Pilot Summary

Official fixed-budget observations only.
The first infrastructure-invalid seed-11001 attempt is excluded.

| Seed | Status | Wall s | Accepted/s | Cycles/s | Peak RSS KiB | Cycles | L1 Intent | L2 Intent |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 11001 | COMPLETED | 7.616386 | 1312.96 | 1823.83 | 45064 | 13891 | 16 | 60 |
| 11002 | COMPLETED | 7.468953 | 1338.88 | 1855.82 | 44940 | 13861 | 18 | 62 |
| 11003 | COMPLETED | 7.684443 | 1301.33 | 1801.56 | 44996 | 13844 | 17 | 60 |

## Median

- Wall time: 7.616386 s
- Accepted instructions/s: 1312.96
- Cycles/s: 1823.83
- Peak RSS: 44996 KiB
- Cycles: 13861
- L1 Intent bins at 10k: 17/20
- L2 Intent bins at 10k: 60/62

## Runtime estimate

- Estimated measured-window time for one 100k M1 run: 76.16 s
- Estimated measured-window time for 15 sequential M1 runs: 19.04 min

Normalized AUC is intentionally not computed here until the exact frozen preregistered AUC definition is re-confirmed.
