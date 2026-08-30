# Exergi V14 reality-calibration report

Status: `REALITY_CALIBRATED_SEMI_SYNTHETIC_END_TO_END_MECHANISM_BENCHMARK`

V14 qualifies two independent commerce backbones. Complete Journey anchors high-frequency grocery
behavior, observed promotions and seasonality. Online Retail II anchors lower-frequency non-store retail,
heavy-tailed order value and cancellations as an imperfect return/refund marginal proxy.

The exact computed statistics live in `calibration_reference_stats.json`; every mapping is declared in
`calibration_mapping.csv`. Important observed anchors include:

- Complete Journey: median basket value $17.50, mean $29.49, median 43 annual baskets per household.
- Online Retail II: median positive non-cancelled invoice value approximately £304.31 and median four
  invoices per identified customer over the source period.
- Complete Journey observed discount share and weekly sales dispersion calibrate—not determine—the
  synthetic promotion and shock ranges.
- Online Retail II cancellations calibrate a return/refund proxy. Cancellation is not asserted to equal a
  fully matured physical return.

No source treatment effect is imported. COGS, payment fees, fulfilment and action costs are not available
with sufficient authority in either source and are therefore explicit preregistered synthetic cost
components. Any missing critical synthetic cost causes `DATA_NOT_READY`, never zero imputation.
