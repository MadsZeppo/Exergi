# Exergi Shopify data contract

Contract version: 1.0  
GraphQL Admin API: `2026-07`  
Mode: read-only

## Scope and access

Default scopes are `read_orders`, `read_products`, `read_inventory`, `read_customers` and
`read_returns`. The code rejects write scopes. `read_all_orders` and
`read_shopify_payments_payouts` are disabled feature gates requiring separate Shopify approval
and explicit deployment configuration.

Without `read_all_orders`, Shopify's standard order-history window is recorded as a coverage
limitation. Exergi does not infer that older history is absent because no older activity occurred.
Protected customer data access must be selected in Shopify's Dev Dashboard. Exergi requests no
name, email, phone or address fields.

## Raw layer

Every accepted object stores:

- merchant ID and deterministic shop ID;
- Shopify source ID and object type;
- source `updatedAt` where supplied;
- API/source version;
- `observed_at` and `ingested_at`;
- canonical JSON and SHA-256 payload hash;
- sync-run ID and replay-safe uniqueness key.

Raw objects are append-only by `(shop, object type, source ID, payload hash)`. Identical webhook
deliveries are rejected by `(shop domain, webhook ID)`. Bulk checkpoints are recorded per
resource, allowing a completed Shopify operation to be downloaded/materialized again without
creating duplicate raw or canonical rows.

## Canonical model

The additive Alembic migration provides shops, connections, raw objects, customer/product/order
grains, discounts, refunds, returns, fulfillments, payment transactions, daily customer/company
state, economic assumptions, data quality, decisions, prediction ledger, experiment contracts,
assignments, mature outcomes and verified-profit ledger.

Canonical records carry source/tenant IDs, event and observation time, ingestion time, currency,
source version and deletion status where applicable. Analytical customer keys are
`HMAC-SHA256(customer-pseudonym-key, shop-id + Shopify-customer-id)`. Guest checkouts remain valid
orders with no customer key.

## Monetary semantics

For each order:

`contribution_profit = net_revenue - refunds - COGS - payment_fees - shipping_subsidy - fulfillment_cost - action_cost`

Components carry one authority:

- `OBSERVED`: directly present in an authorized source;
- `MERCHANT_ASSUMPTION`: explicit versioned merchant input;
- `DERIVED`: deterministic arithmetic over labeled components;
- `MISSING`: not available and not replaced.

Result authority is one of `OBSERVED_CONTRIBUTION_PROFIT`,
`ESTIMATED_CONTRIBUTION_PROFIT`, `NET_REVENUE_ONLY`, `GROSS_REVENUE_ONLY` or
`DATA_NOT_READY`. No currency conversion is performed without an explicit FX source and policy.

## Time and state contract

A row can contribute to a state at time `t` only when both `occurred_at <= t` and
`observed_at <= t`. Daily state is deterministic for the same canonical records, economic
assumption version and cutoff. Future-arriving refunds and events cannot be backfilled into an
earlier snapshot without creating a new version.

## Reconciliation

The reconciliation result compares the same shop, currency and time window for order count,
gross sales, discounts, refunds, net sales and identified customers. Differences are numeric and
must be explained (for example guest checkout, currency exclusion, order-history permission or
as-of timing). A difference is never hidden by a composite score.

## Evidence boundary

Shopify history supports descriptive decomposition, cadence change, discount association,
refund/return diagnostics and time-based forecasting. It does not identify the counterfactual
effect of a new action. The first card is therefore limited to `TEST`, `AVOID`, `BAU` or
`NOT_ENOUGH_EVIDENCE`; `DO` is unavailable for a new merchant.
