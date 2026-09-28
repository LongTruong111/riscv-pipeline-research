# Week 13 M1 Pure-Random Pilot — Telemetry v2

## Status

This directory contains the corrected, protocol-complete M1 Pure-Random
pilot telemetry for seeds 11001, 11002, and 11003 at 10,000 accepted
instructions per seed.

The historical dataset in `research/week13/pilot/m1/` is preserved and
must not be deleted or overwritten.

## Supersession scope

The historical v1 runs remain evidence of the original execution and
coverage observations. They are superseded for Week-13 quantitative
pilot reporting because their serialized telemetry schema was incomplete
and `max_intent_consumer_id` was reconstructed from first-cover records
instead of the authoritative campaign cut driver.

The v2 repair does not change the stochastic generator, DUT, accepted
instruction budget, seed mapping, or planned instruction streams.

## Frozen provenance

- DUT revision:
  `595ed75dcf8544c4f7ab3f16966df34ba1c11ee7`
- Protocol revision:
  `fa906a3f8c6630c6e41d9321d79b2c408d04adc5`
- Telemetry-v2 harness revision:
  `c293cc821a95d58ff25cc5adc7edb52c7783bef3`
- Schema:
  `w13.m1-pilot.telemetry.v2`
- Method:
  `M1-PR`
- Accepted budget:
  `10000`
- Seeds:
  `11001`, `11002`, `11003`

## Qualification

Before archival:

- Week-13 Python regression passed 204/204 tests.
- All three frozen 10k plan hashes were reproduced unchanged.
- All three corrected runs completed successfully.
- All three runs reported zero checker mismatches.
- All three runs reported zero post-cut clock edges.
- All three corrected JSON records passed the telemetry-v2 audit.
- The corrected runs were executed from a clean repository tree.

The earlier dirty-tree launch attempts are infrastructure-invalid
pre-execution attempts and are not experimental observations.
