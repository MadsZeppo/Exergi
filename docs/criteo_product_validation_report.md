# Commercial Twin — Criteo randomized product-validation report

**Benchmark:** Criteo Uplift Modeling Dataset, unbiased v2.1  
**Artifact:** `artifacts/benchmarks/criteo/definitive-seed-42-v2`  
**Run date:** 2026-08-25  
**Verdict:** Real customer-response signal demonstrated; Commercial Twin model superiority and abstention value not demonstrated

## Scope and claim boundary

This is real randomized evidence for the layer:

`anonymized customer features + binary campaign assignment → customer response`

It is not World State, pricing, profit, real-customer deployment or individual-counterfactual validation. `treatment` is the randomized intention-to-treat assignment. `exposure` is preserved but forbidden as a model feature because it is post-assignment/endogenous.

The official Criteo/Hugging Face gzip was used under CC BY-NC-SA 4.0. Its SHA-256 matched the publisher value exactly:

`2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc`

## 1. Dataset rows used

All **13,979,592** official rows were ingested and assigned by a deterministic treatment/outcome-blind hash split:

- train: 9,785,466;
- development: 1,397,633;
- untouched test: 2,796,493.

## 2. Treatment/control sizes

Full data:

- treated: 11,882,655;
- control: 2,096,937;
- treatment ratio: 85.0000%.

Test:

- treated: 2,377,738;
- control: 418,755.

## 3. Outcome rates

Full-data averages:

- conversion: 0.291668%;
- visit: 4.699200%;
- exposure: 3.063122%.

Test conversion:

- control: 0.188893%;
- treatment: 0.307351%;
- randomized difference: **+0.118458 percentage points**.

Test visit:

- control: 3.800074%;
- treatment: 4.865759%.

## 4. Models compared

1. static treat-all/constant ATE;
2. outcome-propensity ranking;
3. S-learner/outcome model with treatment;
4. LightGBM T-learner;
5. X-learner;
6. two-fold cross-fitted DRLearner using known randomized propensity;
7. Commercial Twin DR policy/gating view over the same DR estimator.

EconML and DoWhy remained `NOT_INSTALLED`; no challenger result was fabricated. LightGBM required and received the standard native `libomp` runtime dependency.

## 5–6. AUUC and Qini by model

These are raw within-benchmark areas; compare models within each column, not against normalized metrics from other implementations.

| Rank | Model | AUUC | Qini |
|---:|---|---:|---:|
| 1 | Outcome propensity | 0.003385 | 0.000552 |
| 2 | S-learner | 0.003302 | 0.000546 |
| 3 | X-learner | 0.003069 | 0.000510 |
| 4= | DRLearner | 0.003022 | 0.000503 |
| 4= | Commercial Twin DR | 0.003022 | 0.000503 |
| 6 | T-learner | 0.002805 | 0.000397 |
| 7 | Static/tie-random baseline | -0.000049 | -0.000030 |

## 7. Commercial Twin rank

Commercial Twin DR ranked **joint fourth of seven** on both AUUC and Qini. It beat static and T-learner baselines, but lost to outcome propensity, S-learner and X-learner. It tied the standard DRLearner because its ungated response score is that estimator's score.

## 8. Calibration quality

Commercial Twin decile uplift calibration MAE was **0.000132**, or 0.0132 percentage points. Its mean predicted ATE was about 0.0993 percentage points versus the observed 0.1185 points; absolute ATE error was 0.0192 points.

The top predicted decile was notably well calibrated:

- predicted uplift: +0.8664 percentage points;
- observed RCT uplift: +0.8464 points;
- 90% interval: +0.7285 to +0.9643 points.

Calibration was not uniformly monotone. One development-approved ACT decile showed non-positive observed uplift on test. S-learner calibration MAE, 0.0082 percentage points, was better than Commercial Twin DR.

## 9–11. Policy, treat-all and random-policy value

Policy value is an intention-to-treat randomized IPW conversion rate using known propensity 0.85.

| Commercial Twin policy | Value | Random value at same treatment rate | Value above random |
|---|---:|---:|---:|
| Top 5% | 0.002841 | 0.001944 | +0.000897 |
| Top 10% | 0.002916 | 0.002003 | +0.000913 |
| Top 20% | 0.002980 | 0.002122 | +0.000857 |
| Top 30% | 0.002997 | 0.002241 | +0.000756 |
| Top 50% | 0.003020 | 0.002480 | +0.000540 |
| All | **0.003075** | 0.003075 | 0 |
| None | 0.001884 | 0.001884 | 0 |

Commercial Twin targeting clearly beat random targeting at the same constrained budgets. However, without treatment cost or capacity constraints, **treat all was the best tested policy**.

## 12. Best targeting fraction

`ALL` was best. Among restricted targeting policies, 50% had the largest raw value, but still trailed all by 0.000055 conversion probability per user.

This benchmark contains no campaign cost, so it cannot determine the economically optimal targeting fraction.

## 13. Incremental conversions

On the 2,796,493-row test population, IPW estimates versus treat-none were:

- top 5%: +2,675.8 conversions;
- top 10%: +2,884.9;
- top 20%: +3,063.6;
- top 30%: +3,112.8;
- top 50%: +3,175.7;
- treat all: +3,329.5.

These are population-policy estimates, not observed individual counterfactual labels.

## 14. Regret

Commercial Twin regret versus the best available policy, treat-all:

- top 5%: 0.000234 per user;
- top 10%: 0.000159;
- top 20%: 0.000095;
- top 30%: 0.000078;
- top 50%: 0.000055;
- all: 0.

## 15. Gated versus ungated

The gate was selected on development decile uncertainty, then evaluated on untouched test.

| Policy | Acted fraction | Test value | Regret vs treat-all | Incremental conversions vs none |
|---|---:|---:|---:|---:|
| Ungated positive score | 99.78% | 0.003032 | 0.000042 | 3,205.5 |
| Gated ACT | 40.00% | 0.002934 | 0.000140 | 2,932.5 |
| Treat all | 100% | 0.003074 | 0 | 3,324.3 |
| Treat none | 0% | 0.001886 | 0.001189 | 0 |

Disposition counts:

- `DO THIS`: 1,118,598;
- `TEST THIS`: 1,398,245;
- `NOT ENOUGH EVIDENCE`: 279,650.

One of four development-selected ACT deciles was an incorrect confident bin on test. **Gating did not add policy value**; it withheld too much of a broadly beneficial treatment.

## 16. Sample-size curve

The Commercial Twin-compatible T-learner sample curve used 1%, 5%, 10%, 25%, 50% and 100% of the 9,785,466 training rows.

| Training fraction | Rows | AUUC | Qini | Calibration MAE |
|---:|---:|---:|---:|---:|
| 1% | 97,843 | 0.002189 | 0.000171 | 0.002608 |
| 5% | 489,418 | 0.002503 | 0.000364 | 0.001163 |
| 10% | 978,541 | 0.002801 | 0.000404 | 0.000923 |
| 25% | 2,447,165 | 0.002487 | 0.000312 | 0.000956 |
| 50% | 4,892,888 | 0.002381 | 0.000301 | 0.000826 |
| 100% | 9,785,466 | 0.002581 | 0.000334 | 0.000706 |

Calibration generally improved with more data, while ranking was non-monotonic and peaked at 10% in this fixed configuration. This does not establish a universal retailer data threshold; hyperparameters were not retuned per sample size.

## 17. Did Commercial Twin beat simple baselines?

Mixed:

- yes versus static/random ranking and the tested T-learner;
- no versus simple outcome-propensity ranking;
- yes versus random targeting at fixed 5–50% budgets;
- no versus treat-all when there is no treatment cost.

## 18. Did it beat standard uplift models?

No. S-learner and X-learner ranked above it. It tied the standard DRLearner by construction and beat the tested T-learner.

## 19. What failed?

- Commercial Twin was not the best ranking model.
- Its gating policy reduced value and produced one incorrect confident ACT decile.
- Selective targeting did not beat treat-all without costs.
- The sample-size ranking curve was non-monotonic.
- The first metric run exposed invalid physical-order tie handling. That run is preserved separately; v2 uses deterministic treatment/outcome-blind tie breaking, has no NaNs and hard-fails bins lacking either randomized arm.
- EconML/DoWhy challengers were unavailable.

## 20. What has been proven?

On 13.98 million real randomized rows, Commercial Twin's DR score identifies cohorts with materially heterogeneous response. Its top decile prediction closely matched held-out RCT uplift, and its constrained targeting policies substantially outperformed random targeting at equal treatment fractions. The freeze-before-reveal pipeline and append-only batch ledger worked at million-row scale.

## 21. What remains unproven?

- Individual treatment effects: only one potential outcome is observed per user.
- Superiority over simple or standard uplift alternatives.
- Value from abstention/support gating.
- Economic/profit optimality, because costs and revenues are absent.
- Pricing response.
- World State value.
- Transfer to a named customer or another intervention.
- Prospective deployment calibration.

## 22–24. Quality gate

- `pytest -q`: **PASS — 110 tests**.
- `ruff check .`: **PASS**.
- `mypy`: **PASS — 96 source files**.

One pre-existing, non-failing joblib physical-core detection warning remains in a synthetic fixture test.

## 25. Exact next product step

Do not add more architecture. Replace the current Commercial Twin default uplift ranking candidate with a development-selected tournament winner rather than assuming DR wins, and validate that selection on a second randomized commerce intervention with treatment cost or contact cost. Pre-register the policy objective—e.g. top 10% or cost-constrained value—and recalibrate the ACT gate so it must demonstrate incremental value over both ungated targeting and treat-all before becoming product-facing.

## Implementation and artifacts

Created or changed:

- `src/decision_engine/datasets/criteo_uplift.py`
- `src/decision_engine/benchmark/criteo_uplift.py`
- `src/decision_engine/ledger/store.py`
- `scripts/run_criteo_uplift_benchmark.py`
- `scripts/finalize_criteo_product_validation.py`
- `tests/test_criteo_uplift.py`
- `tests/test_criteo_product_validation.py`

Definitive artifacts:

- `summary.json`
- `data_profile.json`
- `model_results.parquet`
- `policy_results.parquet`
- `commercial_twin_policy_curve.parquet`
- `uplift_calibration.parquet`
- `sample_size_curve.parquet`
- `gating_comparison.json`
- `research_product_view.json`
- 14 frozen development/test prediction Parquets
- `prediction_ledger.duckdb`
- `model_registry.duckdb`

The complete artifact root is `artifacts/benchmarks/criteo/definitive-seed-42-v2/`.
