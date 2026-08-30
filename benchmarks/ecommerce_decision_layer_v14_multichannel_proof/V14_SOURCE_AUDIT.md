# Exergi V14 source audit

Status: `V14_REALITY_CALIBRATION_QUALIFIED`

## 84.51° Complete Journey

- **Unit:** an item line within a retail basket; basket, product, store and pseudonymous household IDs
  are observed.
- **Time:** transaction timestamp, day and numbered week. All 1,469,307 timestamps parse; observed weeks
  span 1–53.
- **Schema:** household, store, basket, product, quantity, sales value, three discount fields, week,
  timestamp and day. The exact source schema is persisted in `V14_SOURCE_SNAPSHOT.json`.
- **Missingness:** no missing customer, basket, product, quantity, sales value or timestamp in the
  processed transaction extract.
- **Duplicates:** zero byte-equivalent logical item-line duplicates after grouping every observed field.
- **Special values:** 8,869 zero-quantity and 11,226 zero-sales lines. They are retained in aggregate
  diagnostics but cannot define positive order economics by themselves.
- **Returns:** no authoritative return/refund field. Negative quantity is not observed. V14 must not infer
  mature returns from this source.
- **Money:** `SALES_VALUE` and observed discount components support sales/discount calibration only.
  There is no COGS, fulfilment, payment fee or contribution-profit authority.
- **Concentration:** the top 1% of households account for about 6.27% of sales and the top 10% for 35.14%.
- **Temporal behavior:** median observed inter-basket gap is two days; zero-day repeat baskets exist.

Campaign receipt and coupon redemption are observational events, not randomized assignments. They are
not used to estimate causal response.

## UCI Online Retail II

- **Unit:** an item line within an invoice or cancellation; invoice, stock, timestamp, quantity, price,
  customer and country fields are observed.
- **Time:** invoice timestamps span 1 December 2009 to 9 December 2011. The processed Parquet stores
  timezone-aware timestamps.
- **Missingness:** 243,007 lines lack customer ID and 4,382 lack description; core invoice, product,
  quantity, price and timestamp fields are present.
- **Duplicates:** 12,133 excess rows in 11,297 exact duplicate groups. Duplicate-sensitive statistics use
  invoice-level aggregation; the raw duplicate rate is preserved as a calibration limitation.
- **Cancellations:** 19,494 lines and 8,292 invoices carry the source cancellation marker. Cancellation
  is a refund/return proxy, not evidence of a completed physical return or its operational cost.
- **Special values:** 22,950 negative-quantity lines, five negative-price lines and 6,202 zero-price
  lines. Positive order-value calibration excludes cancelled/nonpositive invoices.
- **Money:** unit price × quantity supports observed invoice-value calibration. It does not support COGS,
  shipping, fees, refunds maturity or contribution profit.
- **Concentration:** the top 1% of identified customers account for about 31.42% of net line value and
  the top 10% for 63.74%.
- **Temporal behavior:** median interpurchase gap among identified non-cancelled invoices is 25 days.

## Integrity conclusion

The two sources are independent and adequate for aggregate reality calibration. They are insufficient
for randomized causal truth, channel effects or contribution-profit claims. No entity is joined across
sources, no model is selected, and no synthetic outcome is generated in this checkpoint.
