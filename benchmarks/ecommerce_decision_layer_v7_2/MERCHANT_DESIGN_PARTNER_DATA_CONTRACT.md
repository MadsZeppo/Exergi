# Merchant Design-Partner Data Contract

## Purpose and authority

This is a read-only schema and validation pipeline for the first merchant shadow pilot. It supports
historical audit, frozen recommendation generation, merchant-approved randomization, and matured
contribution-profit evaluation. It cannot execute a campaign or mutate merchant systems.

## Unit-level required schema

| Field | Type / rule | Timing |
|---|---|---|
| `stable_unit_id` | non-empty string, unique in extract | fixed before assignment |
| `assignment_timestamp` | timezone-aware datetime | assignment |
| `randomized_assignment` | declared arm | assignment |
| `logged_propensity` | `(0, 1]`, equals frozen arm probability | assignment |
| `eligible` | must be true for evaluation table | frozen before assignment |
| `eligibility_timestamp` | timezone-aware, no later than assignment | pretreatment |
| `pretreatment_features` | unique names, value plus source timestamp | every timestamp no later than assignment |
| `purchase_count` | nonnegative integer | matured outcome |
| `return_count` | nonnegative integer | matured outcome |
| `gross_purchase_revenue` | nonnegative monetary value | matured outcome |
| `returns_and_refunds` | nonnegative monetary value | matured outcome |
| `merchant_funded_discounts` | nonnegative monetary value | matured outcome |
| `item_level_cogs` | nonnegative monetary value | matured outcome |
| `fulfillment_cost` | nonnegative monetary value | matured outcome |
| `payment_fees` | nonnegative monetary value | matured outcome |
| `campaign_action_cost` | nonnegative monetary value | assignment/outcome ledger |
| `contribution_profit` | signed monetary value, must reconcile exactly | matured outcome |
| `outcome_maturity_timestamp` | timezone-aware and after assignment | frozen outcome window |

Contribution profit is validated as:

`gross revenue − refunds − merchant discounts − COGS − fulfillment − payment fees − action cost`.

Incomplete cost ledgers cannot silently become profit evidence. Duplicate IDs, unknown arms,
propensity mismatches, missing required features, post-assignment feature timestamps, immature
outcomes, or unreconciled contribution profit fail validation.

## Experiment-level schema

The merchant schema freezes the randomization unit, allowed arms, one propensity per arm summing to
one, required pretreatment features, and `contribution_profit` as the primary outcome. Both
`read_only=true` and `autonomous_action_allowed=false` are enforced by validation and cannot be
overridden by configuration.

## Read-only protocol

Stages must advance exactly once, in order:

1. **Historical audit** — validate IDs, timing, outcome maturity, economics coverage, and candidate
   randomization unit.
2. **Preregistration** — freeze eligibility, arms, propensity, primary outcome, maturity window,
   estimand, estimator, cost definition, thresholds, and hashes.
3. **Shadow recommendations** — generate recommendations without execution; log all candidates and
   merchant-visible reasons.
4. **Merchant-approved randomized test** — require explicit timestamped merchant approval before
   assignments; Exergi has no autonomous-action permission.
5. **Matured contribution-profit evaluation** — wait for the frozen maturity timestamp, reconcile
   every cost component, and evaluate ITT using logged propensities.

The implementation is in
`src/commercial_twin/merchant_validation/design_partner_contract.py`. Focused tests cover temporal
leakage, profit reconciliation, duplicates, maturity, sequential approval, and the autonomous-action
prohibition.

