# Win-back pilot data request — schema V1

Provide UTF-8 CSV or Parquet. Use stable pseudonymous IDs, ISO-8601 timezone-aware timestamps, one
declared currency and no free-text personal data.

| File | Required fields |
|---|---|
| `customers` | `customer_id`, `created_at`, `timezone`, `currency`, `consent`, `suppressed` |
| `orders` | `order_id`, `customer_id`, `ordered_at`, `currency`, `gross_item_sales`, `line_discounts`, `shipping_revenue`, `payment_transaction_cost` |
| `order_lines` | `order_line_id`, `order_id`, `product_id`, `quantity`, `gross_sales`, `discount`, `cogs` |
| `products` | `product_id`, `category`, `currency`, `unit_cogs` |
| `discounts` | `discount_id`, `order_id`, `amount`, `merchant_funded_amount`, `currency` |
| `returns` | `return_id`, `order_id`, optional `order_line_id`, `returned_at`, `refund_amount`, `currency` |
| `eligibility` | `customer_id`, `snapshot_at`, `historical_purchase_count`, `last_purchase_at`, `last_parallel_campaign_at`, `consent`, `suppressed` |
| `channel_costs` | `experiment_id`, `customer_id`, `channel_cost`, `shipping_subsidy`, `currency` |
| `delivery` | `experiment_id`, `customer_id`, assigned `arm`, `delivered_at`, `exposed_at` |
| `outcomes` | `experiment_id`, `merchant_id`, `customer_id`, `measured_at`, `currency`, `net_revenue`, `merchant_funded_discount`, `refunds_returns`, `cogs`, `shipping_subsidy`, `payment_transaction_cost`, `channel_cost`, `unsubscribe` |

## Required metadata

Also provide merchant ID, extract timestamp, data cutoff, timezone, currency, source-system names,
file SHA-256 checksums, COGS definition, discount-funding definition, return-lag policy, shipping
subsidy definition, payment-fee definition and channel/contact-cost contract.

Delivery/exposure is diagnostic only. ITT treatment is the immutable randomized assignment.
