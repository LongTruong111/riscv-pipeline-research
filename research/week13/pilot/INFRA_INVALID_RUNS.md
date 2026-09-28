# Week 13 infrastructure-invalid runs

## M1 pilot — seed 11001 — first attempt

- Harness revision: `6ac5a0bf232ed0007067abd9129e0528c0053d07`
- Seed: `11001`
- Budget: `10000 accepted`
- Classification: `INFRA_INVALID`
- Result is excluded from all pilot coverage, AUC, throughput, RSS, and inference.
- No official JSON result was produced.

Cause:

The pilot runner inherited a preflight-specific exact-cut assertion requiring
`window.pending_entry_count == 1`, which assumes that the accepted budget lands
inside a partial final stochastic block.

For this execution, the runtime had already completed and released the final
block, so `window.pending_entry_count == 0`.

Resolution:

The exact-cut cleanup is made shape-independent:

- partial final block -> discard its resident unexecuted suffix;
- complete final block -> no resident suffix exists and no discard is required.

The DUT RTL is unchanged.
