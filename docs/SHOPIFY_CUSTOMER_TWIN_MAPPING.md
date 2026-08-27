# Future Shopify → Customer Twin mapping

This is a future ingestion contract only. It does not implement OAuth or call Shopify.

## Onboarding sequence

`CONNECT → VALIDATE → BUILD TWIN → READY`

## Canonical mapping

| Shopify source | Canonical object/field | Status and caveat |
|---|---|---|
| Customer GID | `CustomerEvent.customer_id` | Observed pseudonymous key; do not ingest name/email into modeling |
| Order `createdAt` | `event_time` | Observed |
| Order GID | `order_id` | Observed |
| Line item product/variant GID | `product_id` / Product | Observed |
| Product type or taxonomy | `category_id` | Observed where maintained; otherwise unavailable |
| Vendor | `brand` | Observed where maintained |
| Line quantity | `quantity` | Observed |
| Original and discounted line totals | `price`, `discount` | Observed; preserve currency |
| Order source/channel | `channel` | Observed where Shopify exposes it |
| Refund and refunded line items | Refund / `return_flag` | Observed refund, not necessarily physical return |
| Customer default address | `geography` | Optional coarse geography only; minimize PII |
| Order transaction | purchase event | Observed commercial outcome |

## Additional sources required

| Capability | Required source |
|---|---|
| Product views, sessions and carts | Shopify Web Pixels/customer events or consented first-party analytics |
| Email/SMS sends and exposure | Klaviyo or another messaging provider |
| Ad impressions/clicks | Marketing-platform exposure logs |
| Physical returns and reasons | Returns-management or warehouse system |
| Cost and contribution margin | ERP/accounting/product-cost source |
| Inventory and availability | Shopify inventory plus warehouse feeds |

Browsing, message exposure and ad exposure must not be inferred from orders. Refunds must
not automatically be described as returns. Every mapped field retains observed, derived,
or unavailable provenance.
