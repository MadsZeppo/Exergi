# Merchant pilot readiness

Overall status: **READY FOR READ-ONLY SHADOW MODE**.

Synthetic and public proxy data do not establish merchant contribution profit. The failed V7.1
sequential gates also prevent promotion to a fixed active randomized pilot in this pass.

| Component | Status | Evidence and boundary |
|---|---|---|
| State/data | SHADOW READY | Versioned CSV/Parquet contracts and fail-closed ID, time, currency, linkage and cost checks exist. No merchant extract has been received. |
| Prediction | DEVELOPMENT ONLY | Pre-outcome expectation can be ledgered, clearly labelled as prediction rather than causal result. |
| Causal action viability | NOT VALIDATED | Public RCTs validate mechanics/proxy outcomes, not this merchant/action/economics. |
| Personalization | NOT VALIDATED | Optional; the pilot defaults to one population intervention versus BAU. |
| Economics | SHADOW READY | Customer-level CP requires discounts, refunds, COGS, shipping, payment and channel cost; any missing field disables profit claims. |
| Sequential safety | FAIL | Committed-risk budgets held, but frozen stop-latency and post-observable-loss gates failed. |
| Evidence/claim authority | SHADOW READY | Legacy oracle priors are quarantined; real-data claims remain dataset-specific. |
| Pilot integration | SHADOW READY | Deterministic assignment export, immutable contract and hash-chained ledger exist; no live connector or send path exists. |
| Operations | PARTIAL | Runbook and data request exist. Merchant approval, DPA/access, real extract and dry-run are still absent. |

## What shadow mode can do

It can validate a merchant extract, compute the eligible cohort, freeze a two-arm experiment,
produce an assignment file without sending it, ingest mature customer-level outcomes, and produce
an audited ITT report. It cannot autonomously launch, message customers, claim profit before
maturity, or scale an action.

## Promotion blocker

Before a fixed randomized pilot, the team must repair sequential stop behavior under a newly
preregistered V7.2 protocol and complete a merchant-specific shadow run with economically complete
data. V7.1 thresholds cannot be changed after the observed failure.
