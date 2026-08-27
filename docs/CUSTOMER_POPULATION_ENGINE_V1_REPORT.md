# Customer Population Engine V1 — real-data validation

## Executive conclusion

Customer Population Engine V1 was implemented and evaluated with a strict chronological
freeze → simulate → reveal design on real, anonymised commerce events.

Overall verdict: **FAIL**.

The frozen engine calibrated aggregate buyer count reasonably, but it did not beat the
strongest simple baseline on any of the seven preregistered comparisons. It underpredicted
orders by 42.1% and overpredicted revenue by 203.0%. The simulated revenue interval did not
contain the actual outcome. No final-test tuning was performed and the negative result is
preserved.

## 1. Dataset used

The preferred REES46 multi-category data is legally available, but its monthly files are
1.6–2.7 GB each. Downloading the required sequence would have been irresponsible for this
workspace. The benchmark therefore uses REES46/Open CDP's officially published anonymised
electronics behavior dataset, a 20.3 MB compressed real-event file.

Source: `https://data.rees46.com/datasets/electronics-events/electronics-events.csv.gz`

SHA-256:
`cbcbedc28c39a6b2add493bbbd9f71c061ad9d84087b85e64c442e4d47f418e7`

The publisher describes its datasets as anonymous and available for analysis/research. No
PII is introduced.

## 2–4. Scale and history

- Events: **885,129**
- Unique pseudonymous customers: **407,283**
- Event range: **24 September 2020–28 February 2021**
- Event types: view, cart, purchase
- Final snapshot known customers: **336,452**
- Final snapshot active customers: **79,699**
- Median observations per known customer: **1**
- Mean state reliability: **0.0846**

The extreme sparsity is a central finding, not a hidden implementation detail.

## 5. CustomerState fields

V1 state includes:

- recency since last view, cart, and purchase;
- view and cart frequency over 7/30/90 days;
- purchase frequency over 30/90/180 days;
- spend over 30/90/180 days;
- AOV and median observed item price;
- dominant category and category concentration;
- product-repeat rate;
- view→cart, cart→purchase, and abandonment rates;
- recent purchase-frequency and spend change;
- NEW, ACTIVE, COOLING, or DORMANT lifecycle state;
- observation count, effective history, reliability, shrinkage strength, and ESS.

Unavailable attributes are not inferred. Geography, discount, channel, order ID, returns,
and quantity are explicitly unavailable in this source.

## 6–8. Cohorts, representation and shrinkage

Eight deterministic MiniBatchKMeans cohorts are built from standardized, transformed
behavioral state. Labels remain neutral (`Cohort 01` … `Cohort 08`), and descriptions are
generated only from observed statistics.

The model tournament compares transparent RFM/state features with state plus a learned
low-dimensional category representation. The category representation is fit on training
data only using one-hot category states followed by truncated SVD. No transformer or LLM
behavior model is used.

Sparse-customer propensity uses empirical-Bayes-style shrinkage:

```text
weight_individual = observations / (observations + 20)
estimate = weight_individual × individual evidence
         + (1 - weight_individual) × population prior
```

The individual weight, reliability, and effective sample size are persisted.

## 9–10. Model tournament and selected models

Compared for purchase, orders, and spend:

- population average;
- last-period persistence;
- shrunk RFM;
- cohort average;
- histogram gradient boosting on RFM/behavioral state;
- histogram gradient boosting with learned category representation.

Development-only winners frozen before final reveal:

| Outcome | Selected model |
|---|---|
| Purchase probability | population average |
| Expected orders | gradient boosting RFM |
| Expected spend | cohort average |

Complexity did not automatically win. Category representation did not earn selection on the
final frozen tournament.

## 11. Rolling cutoffs

Development cutoffs:

- 1 December 2020 → next 30 days;
- 1 January 2021 → next 30 days.

Final untouched cutoff:

- 1 February 2021 → next 30 days.

The final model choices, success criteria, predictions, and Prediction Ledger entry were
written before final outcomes were evaluated.

## 12. Strongest baselines

The strongest baseline varies by outcome. On final aggregate metrics:

- purchase: population average;
- orders: population average, 6.55% aggregate error;
- revenue: the best simple baseline, 34.21% aggregate error.

The frozen engine did not strictly beat a simple baseline on any preregistered comparison.

## 13–20. Final fidelity metrics

| Metric | Frozen engine result |
|---|---:|
| Purchase Brier score | 0.001143 |
| Purchase calibration error | 0.000070 |
| Buyer-count relative error | 6.13% |
| Order aggregate relative error | 42.14% |
| Revenue aggregate relative error | 202.97% |
| AOV/spend distribution Wasserstein distance | 401.57 |
| Category-mix Jensen–Shannon divergence | 0.13588 |
| Mean cohort purchase-calibration error | 0.00480 |

Simulated versus actual:

| Outcome | Simulation mean | 90% interval | Actual |
|---|---:|---:|---:|
| Buyers | 363 | 335–394 | 385 |
| Orders | 264 | 236–295 | 456 |
| Revenue | $470,101 | $467,800–$472,143 | $155,143 |

Population buyer calibration was useful, but order, revenue, category and cohort fidelity
were insufficient. Aggregate accuracy did not coexist with useful individual heterogeneity.

## 21–23. Baseline battle and heterogeneity

Did the Twin beat baselines? **No: 0 of 7 preregistered final comparisons.**

Observed cohorts exhibit real descriptive heterogeneity: trailing purchase rates range from
approximately 0% to 43.8%. However, the selected purchase model is the population average,
so it does not preserve that heterogeneity in forward customer probabilities. This is one
reason the overall result fails even though buyer totals are close.

## 24–25. World State and DriverEvidence

Dataset geography is unknown. World State is therefore:

`NOT_AVAILABLE_FOR_VALIDATION`

and:

`world_effect_validated=false`.

DriverEvidence distinguishes `CAUSAL`, `PREDICTIVE`, `CONTEXT_ONLY`, and `UNKNOWN`.
Predictive evidence uses historical-association language and cannot generate causal
“because” wording. Current benchmark driver evidence is predictive only.

## 26. Product-shaped snapshot

Generated artifacts include a typed `CustomerPopulationSnapshot`, its JSON serialization,
and a future product-view Markdown prototype. They show state, neutral cohorts, uncertainty,
support, model versions and the explicit FAIL status without creating personas or causal
claims.

## 27. Runtime

Definitive benchmark runtime: **approximately 16 seconds** on this workspace after canonical
Parquet ingestion.

## 28–30. Quality gates

- pytest: **121 passed**;
- Ruff: **passed** for the complete repository;
- MyPy: **passed for 104 source files**.

The only warning was joblib falling back from physical- to logical-core detection. It did
not change benchmark or test results.

## 31. Overall verdict

**FAIL**.

The system can construct and update a leakage-safe probabilistic customer population, freeze
predictions, and evaluate multiple resolutions. It cannot yet reproduce the next 30 days
better than strong simple baselines.

## 32. Exact next step

Do not broaden the product. The next scientific step is to improve temporal outcome
construction and sparse-population modeling on development cutoffs only—especially
zero-inflated order/spend modeling, returning-versus-new customer decomposition, and cohort
probability calibration—then preregister and run a new untouched time period or second real
dataset. The February holdout must not be reused for tuning.

## Files created

- `src/commercial_twin/population_contracts.py`
- `src/commercial_twin/population_ingestion.py`
- `src/commercial_twin/population_state.py`
- `src/commercial_twin/population_models.py`
- `src/commercial_twin/population_factory.py`
- `src/commercial_twin/population_benchmark.py`
- `scripts/run_customer_population_benchmark.py`
- `tests/test_customer_population.py`
- `docs/SHOPIFY_CUSTOMER_TWIN_MAPPING.md`
- this report

`src/commercial_twin/__init__.py` was extended with the lazy `CustomerTwinFactory` export.

## Primary artifacts

- `success_criteria.json`
- `frozen_final_customer_predictions.parquet`
- `prediction_ledger.duckdb`
- `development_tournament.parquet`
- `final_metrics.parquet`
- `cohort_fidelity.parquet`
- `summary.json`
- `customer_population_snapshot.json`
- `product_experience.md`

All reside under:

`artifacts/customer_population/rees46-electronics-v1-seed-42/`
