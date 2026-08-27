# Commercial Twin — first customer data contract

This contract describes the minimum historical data needed to evaluate a first modern US brand. It is a data-readiness contract, not a promise that observational data identifies causal effects.

## Delivery format

- Preferred: Parquet; accepted: UTF-8 CSV.
- One row per transaction line unless a table below states otherwise.
- All timestamps must include a timezone or be accompanied by a documented source timezone.
- Stable pseudonymous IDs are required; do not send names, email addresses, street addresses, phone numbers, payment details, or other direct identifiers.
- Provide a data dictionary, extraction timestamp, source-system name, row count and known quality limitations for every file.
- Initial evaluation window: ideally 24–36 months, with at least 12 months and explicit coverage dates.

## Required transaction table

| Field | Type | Meaning and validation |
|---|---|---|
| `transaction_timestamp` | timestamp | Time the order/transaction became effective; timezone required |
| `customer_id` | string | Stable pseudonymous customer identifier |
| `order_id` | string | Stable pseudonymous order identifier |
| `product_id` | string | Stable SKU/product identifier |
| `category_id` | string | Stable, documented product category |
| `quantity` | number | Purchased units; document cancellations and negative rows |
| `list_price` | number | Pre-discount unit price in documented currency |
| `actual_price` | number | Paid unit price before tax/shipping unless documented otherwise |
| `discount` | number | Discount depth or amount, with its unit explicitly documented |
| `customer_geography` | string | US state code where defensible; document billing/shipping/account basis |

`unit_cogs` is required if contribution-profit recommendations are desired. Without reliable COGS, the Twin may estimate behavior and revenue but must not present contribution profit as known.

## Required action and treatment metadata

For every promotion, message, offer or price intervention used for causal evaluation:

| Field | Meaning |
|---|---|
| `action_id` | Stable intervention/campaign identifier |
| `action_type` | Discount, coupon, email, paid campaign, price change, etc. |
| `assigned_at` | Assignment/decision time, before outcomes |
| `effective_start`, `effective_end` | Treatment exposure window |
| `eligible_population` | Reconstructable eligibility rule |
| `assigned_treatment` | Actual randomized or operational assignment |
| `control_definition` | Explicit no-action/status-quo definition |
| `assignment_probability` | Required for randomized or known-propensity designs |
| `randomization_unit` | Customer, session, store, geography, etc. |
| `experiment_id` | Experiment linkage where applicable |

If assignment probabilities or eligibility cannot be reconstructed, mark them unavailable. Do not infer randomization from balanced-looking data.

## High-value context

- promotion calendar and stacking rules;
- site/store traffic and sessions;
- campaign send, impression and click timestamps;
- returns, cancellations and refunds;
- inventory and stockout history;
- acquisition channel and first-touch date;
- marketing spend and campaign scope;
- store/channel identifiers;
- product launches, retirements and assortment changes;
- price and cost effective-date history.

## Optional context

- defensibly sourced competitor prices or promotion indicators;
- regional operational events;
- documented customer segment labels that existed before treatment.

Optional fields are never silently treated as complete. Competitor or third-party data must include provenance and observation time.

## Temporal and causal requirements

Every field used for a decision must have been available before that decision. The delivery should distinguish:

- event time;
- source-system ingestion time where available;
- correction/revision time;
- treatment assignment time;
- outcome observation time.

Post-treatment mediators—such as clicks caused by a campaign—must not be used as pre-treatment features for that campaign's effect estimate.

## Geography and World State

Customer geography should normally be a two-letter US state code. National or unknown geography is accepted but reduces geographic resolution. Commercial Twin resolves external signals as:

`STATE → REGION → NATIONAL → NOT_AVAILABLE`

The resolved geography, fallback reason, source, series, release date and vintage status remain visible. National values are not relabeled as state values.

## Data-quality acceptance checks

Before modeling, Commercial Twin will report:

- schema and type compliance;
- duplicate order-line rate;
- missingness by field and time;
- impossible price/quantity/discount values;
- timestamp ordering and future leakage;
- ID stability and coverage;
- treatment/control counts and assignment balance;
- treatment support by customer/company context;
- COGS completeness;
- geography coverage;
- outcome reveal completeness;
- breaks caused by tracking or policy changes.

## Security and transfer

Use the mutually agreed encrypted transfer channel and least-privilege access. Apply the company's retention and deletion policy. Direct personal identifiers are out of scope for the initial engagement.

## Deliverables after readiness review

The first review returns:

1. a canonical data profile;
2. leakage and temporal-integrity findings;
3. treatment-support and experiment-quality diagnostics;
4. capability-level `READY`, `LIMITED` or `NOT_READY` status;
5. an explicit list of claims the available data can and cannot support;
6. a proposed frozen benchmark and prospective validation plan.

No `ACT` recommendation is issued solely because this schema is populated. Support, uncertainty, falsification and economic evidence must also pass.
