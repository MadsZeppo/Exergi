# Customer Population Engine V2 — order and revenue generation

## Executive result

Customer Population Engine V2 fixes V1's incoherent revenue generator and explicitly models
new-customer arrivals. It was selected on December 2019 and January 2020 REES46 Cosmetics
development periods, frozen, and evaluated once on February 2020.

Preregistered verdict: **MIXED**.

V2 improved revenue error from V1's 203.0% to 23.7%, retained strong purchase heterogeneity
(AUC 0.907), and beat simple purchase/category challengers. It still lost all three mandatory
population metrics—buyers, orders and revenue—to a last-period top-down forecast. Therefore
it does not pass.

V1 and V2 use different stores and time periods, so their errors are directional rather than
a paired model comparison.

## 1. Was there a labeling bug?

Yes.

- Purchase events are item/line events, not necessarily orders. A customer-session is an
  order. V1's customer-local session count was substantially correct.
- V1 did not explicitly remove exact duplicates. There were 655 exact event duplicates,
  including three purchase rows.
- V1 headline outcomes silently excluded future customers without CustomerState. In the
  burned electronics February, 3,956 of 4,341 buyers were new.
- V1 independently generated buyers, orders and spend, permitting the impossible result of
  fewer orders than buyers.

Full audit: `docs/CUSTOMER_POPULATION_V1_FAILURE_AUDIT.md`.

## 2. Why did V1 overpredict revenue?

For existing customers:

| Component | V1 predicted | V1 actual | Relative error | Revenue-error contribution |
|---|---:|---:|---:|---:|
| Buyers | 361.4 | 385 | -6.1% | -$30,706 |
| Orders/buyer | 0.730 | 1.184 | -38.4% | -$311,630 |
| Revenue/order | $1,781.52 | $340.23 | +423.6% | +$657,231 |

The implied order value invented the revenue. Sparse customers with zero historical purchases
received $456,219 predicted revenue versus $92,320 actual. V1 simultaneously omitted $1.22m
of actual new-customer revenue.

## Dataset and strict validation

V2 uses the legally published, anonymised REES46 Cosmetics event history:

- 19,583,742 exact-row-deduplicated events;
- 1,639,358 pseudonymous customers;
- 156,574 customer-session orders;
- $6,344,593 observed purchase-item revenue;
- October 2019–February 2020.

Five compressed files total 482 MB. DuckDB streams them into a 44 MB customer-month/order
representation; raw multi-million-row events are never materialized in Python memory.

Development: December and January. Final: February. February rows are scanned only after
success criteria, selection, predictions and Prediction Ledger records are frozen.

## Generative architecture

V2 uses a coherent hurdle chain:

1. Purchase incidence: `P(purchase next month)`.
2. Conditional orders: `E[orders | purchase]`, constrained to at least one.
3. Conditional order value: `E[value | order]`.
4. Existing revenue: incidence × conditional orders × conditional value.
5. A separate new-customer arrival and first-order process.
6. Coherent aggregate Monte Carlo where orders cannot be below buyers.

## Tournament

### Purchase incidence

Compared population average, shrunk RFM, logistic classification and gradient boosting.

Winner: **calibrated logistic**.

### Conditional order count

Compared cohort mean, Poisson, Negative Binomial and boosted count models.

Winner: **Poisson**.

### Conditional order value

Compared cohort mean, lognormal, Gamma, Tweedie and quantile boosting.

Winner: **quantile boosting**.

No development winsorization or final clipping was introduced. Gamma/Tweedie training uses a
$0.01 positive floor for the 20 non-positive orders required by their mathematical support;
actual evaluation values remain unchanged.

### New-customer arrivals

Compared trailing, trend and overdispersed count candidates.

Winner: **trailing mean**.

### Top-down population challenger

Compared last period, historical mean and linear trend.

Winner: **last period**.

## 3–6. V1 versus V2 headline errors

| Metric | V1 | V2 | Note |
|---|---:|---:|---|
| Buyer-count error | 6.13% | 37.86% | V2 includes new arrivals; different store |
| Order-count error | 42.14% | 39.51% | modest directional improvement |
| Revenue error | 202.97% | 23.74% | major directional improvement |
| Revenue/order error | 423.6% | -11.31% | hurdle/value model fixed explosion |

V2 predicted versus actual:

| Population metric | Predicted | Actual |
|---|---:|---:|
| Buyers | 35,511 | 25,759 |
| Orders | 41,018 | 29,401 |
| Revenue | $1,492,221 | $1,205,969 |

The coherent simulation's 90% ranges also missed all actual totals, so aggregate
probabilistic calibration is unacceptable despite individual purchase calibration.

## 7. New-customer error

| Metric | Predicted | Actual | Relative error |
|---|---:|---:|---:|
| New buyers | 14,918 | 12,588 | +18.51% |
| New orders | 16,155 | 13,536 | +19.35% |
| New revenue | $608,030 | $503,396 | +20.79% |

New customers are now explicit and no longer mixed into existing CustomerState predictions.

## 8. Top-down versus bottom-up

| Metric | Bottom-up V2 error | Top-down last-period error |
|---|---:|---:|
| Buyers | 37.86% | 9.55% |
| Orders | 39.51% | 10.15% |
| Revenue | 23.74% | 9.52% |

Top-down wins decisively. No reconciliation is promoted because a development-approved
reconciliation rule was not preregistered.

## 9. Heavy-tail diagnostics

| Quantile | Actual order value | Predicted conditional value |
|---|---:|---:|
| p50 | $28.75 | $25.58 |
| p90 | $79.29 | $27.89 |
| p95 | $108.53 | $35.42 |
| p99 | $238.08 | $50.04 |
| max | $1,523.27 | $129.71 |
| Top-1% share | 9.13% | 2.31% |

V2 no longer explodes the upper tail; it now understates it materially. Revenue overprediction
comes mainly from too many predicted buyers, not extreme conditional values.

## 10–14. Frozen winners and strongest baseline

- Best purchase model: calibrated logistic.
- Best conditional order-count model: Poisson.
- Best conditional order-value model: quantile boosting.
- Best arrival model: trailing mean.
- Strongest final aggregate baseline: last-period top-down.

All winners were development-selected; `test_metrics_used=false` is persisted.

## 15. Rolling development behavior

The selected purchase model's buyer-count relative error changed from 77.7% in December to
18.2% in January. Conditional Poisson order aggregate error improved from 6.45% to 1.98%.
Quantile order-value aggregate error changed from 8.78% to 25.49%.

This temporal instability correctly warned that a single bottom-up population estimate was
not reliable.

## 16. Heterogeneity quality

Final existing-customer purchase AUC: **0.9066**.

Separate tables report predicted and actual purchase rates for:

- active purchasers, cooling browsers and dormant customers;
- high/low historical frequency;
- high/low repeat propensity;
- top 20 observed category affinities.

Thus V2 retains meaningful ranking heterogeneity even though aggregate incidence is
miscalibrated. The model is useful for separation, not yet for total-volume generation.

## 17. Calibration

- Existing-customer purchase Brier: **0.008712**.
- Purchase log loss: **0.039763**.
- Purchase calibration error: **0.005533**.
- Existing buyer-count relative error from the purchase model: **56.35%**.

Low average calibration error coexists with a large rare-event aggregate error. Both are
reported; the former does not excuse the latter.

## 18–19. Baseline battle and verdict

V2 won four of seven primary tests:

- purchase Brier: win;
- purchase calibration: pass;
- heterogeneity AUC: pass;
- category-revenue JS: win;
- buyer count: loss;
- orders: loss;
- revenue: loss.

PASS required at least five of seven **and mandatory wins on buyer count, orders and revenue**.

Final verdict: **MIXED**.

## 20. Exact next step

Do not broaden the product and do not tune on Cosmetics February.

The next scientific step is a new development dataset/period focused on incidence and arrival
level calibration, followed by preregistered top-down/bottom-up reconciliation. Conditional
order frequency and value are now much less problematic; the dominant remaining error is
overprediction of buyer incidence, including new arrivals. A new untouched period is required
for any subsequent final claim.

## Artifacts

Under `artifacts/customer_population_v2/rees46-cosmetics-v2-seed-42/`:

- `success_criteria.json`;
- `frozen_selection.json`;
- `frozen_final_existing_customer_predictions.parquet`;
- `frozen_new_customer_prediction.json`;
- `development_tournament.parquet`;
- `prediction_ledger.duckdb`;
- `summary.json`.

V1 diagnostic artifact:

- `artifacts/customer_population/rees46-electronics-v1-seed-42/failure_decomposition.json`.

## Quality

- pytest: **124 passed**;
- Ruff: **passed** across the repository;
- MyPy: **passed for 106 source files**.

The only warning was joblib's fallback from physical- to logical-core detection. It did not
change results.

## Files created

- `src/commercial_twin/population_v2.py`
- `src/commercial_twin/population_v2_benchmark.py`
- `scripts/prepare_rees46_cosmetics.py`
- `scripts/audit_customer_population_v1_failure.py`
- `scripts/run_customer_population_v2_benchmark.py`
- `tests/test_customer_population_v2.py`
- `docs/CUSTOMER_POPULATION_V1_FAILURE_AUDIT.md`
- `docs/CUSTOMER_POPULATION_ENGINE_V2_REPORT.md`

New real data and processed tables are under `data/raw/rees46/cosmetics/` and
`data/processed/rees46/cosmetics/` respectively.
