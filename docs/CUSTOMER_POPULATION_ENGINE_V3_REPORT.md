# Customer Population Engine V3 — Build and Validation Report

## Executive conclusion

V3 implements the requested hybrid population architecture: **top-down forecasts determine how much; bottom-up propensities determine who**. The implementation is deterministic, bounded, cohort-preserving, tested, and produces a product-shaped snapshot and Prediction Ledger.

The scientific verdict is nevertheless **FAIL**. The first November final-test run exposed an implementation invariant violation: development selection could choose `raw_bottom_up`, while the exported aggregate anchor still used the top-down existing-customer target. November was therefore revealed under an invalid implementation and is now burned. The corrected run is reported only as a diagnostic and is not eligible for PASS.

On that corrected diagnostic, the capability is **MIXED**:

- Reconciliation reduced buyer error from 37.54% for pure top-down and 38.58% for raw bottom-up to 19.15%.
- It did not improve order or revenue error relative to top-down.
- Existing-customer buyer error was 9.70%, but new-customer buyer error was 26.73%.
- Ranking was preserved, but final AUC was only 0.751, below the preregistered 0.85 threshold.
- Decile calibration was acceptable, but hierarchical category fidelity was marginally worse than the simple comparator.
- Uncertainty covered the corrected final outcomes, but intervals were too wide to demonstrate sharp operational forecasting.

The evidence does **not** earn a more elaborate simulator. It supports simplifying the product architecture to aggregate forecasting + propensity allocation + the existing causal decision layer, until another untouched dataset is available.

## 1. Scope and hypothesis

No new product scope or World State was added. V3 addresses only customer-population forecasting and reconciliation.

The preregistered hypothesis was that a hybrid system would improve aggregate fidelity without destroying customer-level heterogeneity:

1. independently forecast buyers, orders, revenue, new buyers, and existing buyers;
2. estimate bottom-up purchase propensity for known customers;
3. reconcile propensities to the independently selected aggregate target;
4. preserve ranking, bounds, cohort differences, and category composition;
5. quantify aggregate uncertainty without using final-test outcomes for selection.

The complete hypothesis and frozen criteria are in [CUSTOMER_POPULATION_ENGINE_V3_HYPOTHESIS.md](/Users/madsflyvholm/Desktop/decision%20layer/docs/CUSTOMER_POPULATION_ENGINE_V3_HYPOTHESIS.md) and [success_criteria.json](/Users/madsflyvholm/Desktop/decision%20layer/artifacts/customer_population_v3/rees46-electronics-purchases-v3-seed-42/success_criteria.json).

## 2. Dataset and isolation

The new validation dataset is the official REES46 electronics purchase stream, separate from the burned Cosmetics February 2020 test. Source: [official REES46 datasets](https://rees46.com/en/datasets).

| Item | Value |
|---|---:|
| Raw file | `purchases.csv.gz` |
| SHA-256 | `c0637b2dfb41644675204950f609bcce892cab3a158a0b2e15043172157ff0e9` |
| Deduplicated purchase items | 602,113 |
| Customers | 234,745 |
| Orders | 404,070 |
| Revenue | 118,447,243.41 |

The source contains ragged records and malformed timestamps, including rows parsed into 1970. Preparation therefore uses a right-edge parser, deduplication, and the preregistered analysis start of April 2020. The malformed and January–March records were excluded by the frozen time boundary, not by performance selection.

Splits were:

- History: April–May 2020
- Development: June–October 2020
- Final: November 2020
- Seed: 42
- Burned Cosmetics February used: no

## 3. What was built

### Data preparation

`prepare_electronics_purchase_aggregates` streams and parses the purchase file, deduplicates purchase items, and creates customer-month, order, and profile artifacts. It avoids loading the full raw dataset into memory.

### Top-down forecasting

Development-only selection compared:

- last period;
- trailing mean;
- weighted trailing mean;
- linear trend;
- exponential smoothing.

Seasonal naive was explicitly unavailable because the data does not contain a complete seasonal cycle. It was not simulated or silently approximated.

Frozen winners were:

| Target | Selected model |
|---|---|
| Buyers | Last period |
| Existing buyers | Last period |
| New buyers | Weighted trailing mean |
| Orders | Last period |
| Revenue | Weighted trailing mean |

No November metric participated in this selection.

### Bottom-up customer model

A logistic purchase-propensity model uses lagged purchase-history states for existing customers. New customers are forecast separately at aggregate level because they do not exist in the known-customer scoring population. The model preserves heterogeneous rankings and generates explicit cohort states rather than cloning a representative customer.

### Reconciliation

Two bounded methods were compared on development data:

- naive probability scaling;
- logit-intercept reconciliation.

The selected method was naive scaling. It rescales bottom-up propensities to the frozen existing-buyer target while keeping probabilities in `[0, 1]`. Orders and revenue are reconciled after buyer reconciliation. Category revenue uses hierarchical category shares constrained to the aggregate revenue anchor.

The corrected implementation enforces the hard invariant:

```text
sum(reconciled existing-customer probabilities)
    == frozen existing-customer buyer target
```

It fails loudly if the invariant is violated.

### Uncertainty

Aggregate uncertainty is generated by deterministic residual bootstrap over development forecast errors. Each draw preserves coherent buyer/order/revenue construction and produces 5th, 50th, and 95th percentiles. This quantifies temporal forecast error; it is not claimed to be a full generative posterior over individual futures.

### Product snapshot and ledger

V3 emits a product-shaped JSON snapshot containing aggregate anchors, uncertainty, cohort states, customer predictions, category allocation, model selection, and evidence labels. Driver evidence is explicitly marked predictive rather than causal. Frozen predictions are also written to the repository’s Prediction Ledger.

## 4. Preregistration and freeze/reveal integrity

The hypothesis, split, metrics, thresholds, candidate models, and success rules were written before final aggregation and inspection. Frozen artifacts were then generated before scanning November labels.

However, the first reveal found a software-contract defect. The selector was allowed to choose raw bottom-up as a reconciliation method even though the exported aggregate calculation used a different top-down target. This created internally inconsistent customer and aggregate predictions.

Consequences:

- November 2020 is burned.
- The invalid output is preserved in [invalid_first_final_summary.json](/Users/madsflyvholm/Desktop/decision%20layer/artifacts/customer_population_v3/rees46-electronics-purchases-v3-seed-42/invalid_first_final_summary.json).
- The defect was corrected by restricting reconciliation selection to actual reconciliation methods and adding a runtime invariant.
- The corrected November results below are diagnostic only.
- `eligible_for_scientific_pass` is `false`, and the official verdict is forced to `FAIL`.

This prevents a post-reveal repair from being presented as untouched validation.

## 5. Corrected diagnostic results

### Aggregate forecasts

| Metric | Actual | Raw bottom-up | Pure top-down | Reconciled |
|---|---:|---:|---:|---:|
| Buyers | 39,416 | 54,624 | 54,212 | 46,962 |
| Orders | 45,664 | 67,103 | 71,316 | 71,316 |
| Revenue | 12,265,650 | 25,569,981 | 20,556,081 | 20,556,081 |

### Relative error

| Metric | Raw bottom-up | Pure top-down | Reconciled | Reconciled beats top-down |
|---|---:|---:|---:|---|
| Buyers | 38.58% | 37.54% | 19.15% | Yes |
| Orders | 46.95% | 56.18% | 56.18% | No; tie |
| Revenue | 108.47% | 67.59% | 67.59% | No; tie |

Reconciliation materially helped buyer count but did not repair the poorly calibrated order and revenue anchors. V3 therefore did not win on two of three aggregate outcomes and did not satisfy the preregistered trade-off rule.

### Existing versus new customers

| Segment | Predicted buyers | Actual buyers | Relative error |
|---|---:|---:|---:|
| Existing | 7,411 | 8,207 | 9.70% |
| New | 39,551 | 31,209 | 26.73% |

Most remaining buyer error comes from forecasting customer acquisition, not allocation among known customers.

## 6. Ranking and calibration

| Diagnostic | Result |
|---|---:|
| AUC before reconciliation | 0.750843 |
| AUC after reconciliation | 0.750843 |
| Ranking correlation | ~1.000000 |
| Decile ECE | 0.011917 |
| Decile MCE | 0.028248 |

Reconciliation preserved ranking almost exactly. Calibration passed the preregistered ECE and MCE limits, but AUC failed the minimum 0.85 requirement. The ranking is useful but not strong enough to support the intended capability claim.

Development AUC ranged from 0.653 to 0.700. Calibration slopes ranged from 0.742 to 0.940, showing recurring under/over-dispersion rather than a single stable calibration relationship.

### Cohort fidelity

| Cohort | Customers | Predicted purchase rate | Actual purchase rate | Absolute error |
|---|---:|---:|---:|---:|
| Active repeat | 7,411 | 12.24% | 14.28% | 2.03 pp |
| Active single | 46,801 | 5.87% | 9.00% | 3.13 pp |
| Lapsed | 137,575 | 2.73% | 2.13% | 0.60 pp |

The ordering is sensible and heterogeneous, but active-single customers are materially underpredicted.

### Category fidelity

| Method | Jensen–Shannon divergence |
|---|---:|
| Hierarchical category reconciliation | 0.0049783 |
| Simple category comparator | 0.0049760 |

Lower is better. The hierarchical method was marginally worse, so its added complexity is not validated.

## 7. Uncertainty and stability

Development interval coverage was 0.80, meeting the preregistered minimum of 0.70. Corrected final diagnostic intervals were:

| Metric | P05 | P50 | P95 | Actual covered |
|---|---:|---:|---:|---|
| Buyers | 26,187 | 50,308 | 67,738 | Yes |
| Orders | 40,112 | 67,936 | 106,568 | Yes |
| Revenue | 8,617,954 | 20,256,687 | 32,494,207 | Yes |

Coverage alone is not success. These intervals are wide, especially for orders and revenue, and expose unstable month-to-month aggregate dynamics. They are honest enough to prevent false precision but not sharp enough for reliable operating plans.

## 8. Success criteria

| Preregistered condition | Result |
|---|---|
| Aggregate errors within top-down + 2 pp | Pass |
| At least two aggregate wins, or specified trade-off | Fail |
| AUC ≥ 0.85 without degradation | Fail |
| Decile ECE ≤ 0.03 | Pass |
| Decile MCE ≤ 0.10 | Pass |
| Category fidelity beats simple comparator | Fail |
| Development interval coverage ≥ 0.70 | Pass |
| Untouched final implementation | Fail — final burned |

Diagnostic capability verdict: **MIXED**  
Scientific validation verdict: **FAIL**

## 9. Did V3 beat the alternatives?

### Versus pure top-down

Only on buyers. It tied top-down on orders and revenue because those aggregate anchors pass through reconciliation unchanged.

### Versus raw bottom-up

It substantially improved aggregate buyer and revenue error, but raw bottom-up happened to have lower order error than the selected top-down order model. This reinforces that development selection was not stable across the final transition.

### Versus simple top-down + propensity

No validated improvement. The selected buyer reconciliation is effectively the simple bounded scaling construction, and the richer hierarchical category layer was slightly worse. The data does not justify calling the more complex composition superior.

## 10. Scientific interpretation

V3 demonstrates four useful engineering facts:

1. Independently forecasting population totals prevents raw propensity sums from silently becoming market-size forecasts.
2. Reconciliation can preserve individual ranking while enforcing a coherent buyer total.
3. New-customer acquisition must be modeled separately from existing-customer propensity.
4. Explicit uncertainty and invariants reveal when attractive point outputs are operationally weak or internally inconsistent.

It does **not** establish:

- untouched out-of-sample superiority;
- reliable revenue or order forecasting;
- AUC strong enough for high-confidence individual targeting;
- superiority of hierarchical category reconciliation;
- causal explanations of customer behavior;
- transportability to another merchant, category, or time period;
- that the bootstrap intervals are a complete probabilistic representation of population uncertainty.

## 11. Files created or changed

### Source

- `src/commercial_twin/population_v3.py`
- `src/commercial_twin/population_v3_benchmark.py`

### Scripts

- `scripts/prepare_rees46_electronics_purchases.py`
- `scripts/run_customer_population_v3_benchmark.py`

### Tests and documentation

- `tests/test_customer_population_v3.py`
- `docs/CUSTOMER_POPULATION_ENGINE_V3_HYPOTHESIS.md`
- `docs/CUSTOMER_POPULATION_ENGINE_V3_REPORT.md`

### Processed data

- `data/processed/rees46/electronics-purchases/customer_month.parquet`
- `data/processed/rees46/electronics-purchases/orders.parquet`
- `data/processed/rees46/electronics-purchases/profile.json`

### Benchmark artifacts

Under `artifacts/customer_population_v3/rees46-electronics-purchases-v3-seed-42/`:

- `success_criteria.json`
- `development_top_down.parquet`
- `development_reconciliation.parquet`
- `development_category_reconciliation.parquet`
- `temporal_calibration.parquet`
- `frozen_selection.json`
- `frozen_aggregate_forecast.json`
- `frozen_final_customer_predictions.parquet`
- `prediction_ledger.duckdb`
- `customer_population_snapshot_v3.json`
- `invalid_first_final_summary.json`
- `summary.json`

## 12. Automated verification

Final repository checks:

| Check | Result |
|---|---|
| `ruff check .` | Pass |
| `mypy src` | Pass — 108 source files |
| `pytest -q` | Pass — 130 tests |
| V3 unit tests | Pass — 6 tests |
| Corrected benchmark runtime | 1.64 seconds |

V3 tests cover bounded and target-coherent reconciliation, rank preservation, order/revenue coherence, category targets, calibration deciles, and deterministic Monte Carlo output.

## 13. Product recommendation

Do not automatically build a V4 population simulator. The next product architecture should be the smallest design supported by evidence:

```text
aggregate buyer/order/revenue forecast
        +
existing-customer propensity ranking
        +
bounded reconciliation and explicit uncertainty
        +
existing causal decision layer
```

Improve or replace the aggregate new-customer, order, and revenue forecasts only when another truly untouched validation period or dataset is available. Until then, retain internal `TEST THIS` / `NOT ENOUGH EVIDENCE` behavior and do not promote the population engine as scientifically validated.

## Final answer to the V3 question

The engine can now reconcile customer-level heterogeneity with independently forecast population totals and refuse internal incoherence. It cannot yet demonstrate, on an untouched final test, that the full hybrid engine reliably predicts customer populations or economic totals better than simple alternatives. The correct verdict is **FAIL**, with a **MIXED** corrected diagnostic and a clear simplification path.
