# First merchant win-back runbook

## Before contact

Offer one bounded read-only shadow study followed, only after approval, by a fixed customer-level
RCT. Do not promise profit, personalization or autonomous rollout. Ask for one accountable merchant
owner, one technical data owner and one person authorized to approve the experiment.

## Access and files

Request encrypted CSV or Parquet exports described in `DATA_REQUEST_TEMPLATE.md`. Read-only export
access is sufficient. No write access to Shopify, Klaviyo or the campaign tool is required for
shadow mode. Agree currency, timezone, retention, deletion and pseudonymous customer-ID handling in
the DPA/security process.

## Week 1

1. Record merchant, currency, timezone, data cutoff and checksums.
2. Run `python -m decision_engine.pilots.winback.runner readiness <extract-dir>`.
3. Reconcile customer/order counts with the merchant.
4. Resolve missing COGS, discount funding, returns, shipping, payment and channel costs.
5. Verify consent/suppression, duplicate IDs, return linkage and timestamp ordering.
6. Freeze inactivity, minimum purchase and parallel-campaign exclusion rules.
7. Size the two-arm test from the CP variance and merchant-approved MDE.

Any unresolved assignment, propensity, currency, maturity or required-cost issue yields
`DATA_NOT_READY`.

## Shadow mode

Run `prepare-shadow` with the approved config. Review the frozen contract hash, eligible count,
planned sample, deterministic 50/50 propensities, assignment-export checksum and ledger chain. The
file is not sent by Exergi. Merchant and analyst independently approve the exact contract and export.

## Launch responsibility

The merchant imports the approved assignment file into its campaign system and implements exactly
the assigned arm. It returns delivery/exposure logs for contamination diagnostics. Exergi does not
autonomously execute the campaign. No exclusions or arm changes are permitted after freeze except a
documented safety stop.

## Outcome maturity and analysis

Wait the full frozen horizon, including the declared return window. Then ingest one outcome row per
assigned customer, including zero purchasers. Primary analysis is customer-level ITT by assigned
arm, not exposure or compliance. Report CP per eligible customer, total incremental CP, confidence
intervals, SRM, missingness, differential attrition, contamination and guardrails.

## Decision

- `SCALE`: mature ITT lower bound above zero and every integrity/economic guard passes.
- `CONTINUE_TESTING`: interval overlaps zero or information is insufficient.
- `STOP`: mature ITT upper bound below zero or a safety/integrity stop applies.

Even `SCALE` requires a human merchant decision. One pilot cannot establish a general merchant
profit claim.

## Stop conditions

Stop or refuse analysis for SRM, assignment mutation, missing propensity, contamination, differential
attrition, incomplete costs, mixed currency, outcome before maturity, unlinked returns, privacy or
consent failure, or breached merchant/action-family risk budget.
