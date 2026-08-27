# Online Retail II — Data Semantics Audit

## Provenance

- Publisher: UCI Machine Learning Repository, dataset 502
- Official source: <https://archive.ics.uci.edu/dataset/502/online+retail+ii>
- DOI: `10.24432/C5CG6D`
- License: CC BY 4.0
- Official ZIP SHA-256: `572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb`
- XLSX SHA-256: `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`
- Observed range: 2009-12-01 through 2011-12-09
- Currency: pound sterling according to UCI; no currency field exists in the file

The original XLSX is used. Its observed column names are `Invoice`, `StockCode`,
`Description`, `Quantity`, `InvoiceDate`, `Price`, `Customer ID`, and `Country`.
This differs slightly from the labels on UCI's web page. The mapping is explicit and the
raw schema is preserved in `provenance.json`.

## Frozen commerce semantics

**Order:** one non-cancelled `Invoice` associated with a non-missing `Customer ID`, with at
least one positive-quantity, positive-price purchase line.

**Order value:** the sum of `Quantity * Price` over valid positive purchase lines in that
invoice. It is observed gross revenue, not contribution profit.

**Cancellation:** a line whose invoice identifier begins with `C` (case-insensitive), or a
negative-quantity line reported separately as an inconsistency diagnostic. A cancellation is
not silently converted to a refund because the file lacks refund-settlement semantics.

Exact duplicate lines are retained in the canonical raw Parquet and flagged in this audit.
Models use declared semantics and any deduplication sensitivity must be reported separately.

## Audit counts

| Diagnostic | Count |
|---|---:|
| Transaction lines | 1,067,371 |
| Unique invoice identifiers | 53,628 |
| Valid identified-customer orders | 36,969 |
| Identified customers | 5,942 |
| Repeat customers | 4,255 |
| Countries | 43 |
| Cancellation-prefix lines | 19,494 |
| Negative-quantity lines | 22,950 |
| Zero-price lines | 6,202 |
| Negative-price lines | 5 |
| Missing-Customer-ID lines | 243,007 |
| Exact duplicate lines beyond first occurrence | 34,335 |
| Positive identified-customer gross revenue | £17,743,429.18 |

Cancellation-prefix and negative-quantity counts do not match exactly. Therefore cancellation
semantics must not be inferred solely from sign. Zero/negative-price records are invalid for
positive purchase value but remain available for audit.

## Multiple lines and duplication

Invoices commonly contain multiple product lines; line count is not order count. Exact duplicate
rows may be legitimate repeated recording or duplication, and the dataset provides no immutable
line ID to distinguish them. They are not silently removed from the source-of-truth table.

## Missing identity

243,007 lines lack `Customer ID`. They contribute to observed store activity but cannot support
customer-level state, repeat-purchase labels, cohort assignment, or treatment targeting. Customer
models therefore use only identified customers and report this coverage limitation.

## Wholesalers and extreme baskets

UCI states that many customers are wholesalers. The largest valid observed invoice values include:

| Invoice | Customer | Gross value |
|---|---:|---:|
| 581483 | 16446 | £168,469.60 |
| 541431 | 12346 | £77,183.60 |
| 493819 | 14156 | £44,051.60 |
| 556444 | 15098 | £38,970.00 |
| 524181 | 17450 | £33,167.80 |

These baskets are not deleted. Robust metrics, tail diagnostics, and quantile outputs must accompany
means. No claim is made that this customer mix represents a typical direct-to-consumer merchant.

## Country distribution and World State

The United Kingdom dominates with 981,330 lines, followed by EIRE (17,866), Germany (17,624),
France (14,330), and the Netherlands (5,140). Existing US World State is geographically and
temporally misaligned, so:

`world_state_validation = NOT_AVAILABLE_FOR_THIS_DATASET`

## Fields that do not exist

The dataset has no COGS, margin, discount assignment, marketing exposure, randomization,
propensity, shipping subsidy, campaign cost, reliable category taxonomy, or behavioral funnel
events. These fields remain unavailable; they are never inferred. Consequently:

- contribution profit is not computable;
- campaign and discount causality are not identifiable;
- product descriptions/codes must not be presented as a validated category taxonomy;
- customer-level action questions must fail closed unless evidence comes from an appropriate
  external randomized benchmark and domain transfer is clearly labeled.
