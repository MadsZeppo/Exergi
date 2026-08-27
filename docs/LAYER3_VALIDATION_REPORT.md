# Layer 3 Action/Uplift Validation Report

## Executive conclusion

**Track A — synthetic ground truth: PASS.** The existing action layer, extended with a shared
cross-fitted AIPW estimator, recovered randomized heterogeneous purchase uplift with essentially
zero mean bias, appropriate interval coverage, and no excess placebo false positives. Under strong
measured confounding, naive difference-in-means was severely biased and AIPW removed nearly all of
that bias.

**Track B — Dunnhumby Complete Journey: INSUFFICIENT.** The verified CC0 CRAN 1.1.0 universe was
downloaded and ingested, but the corrected campaign-18 diagnostic fails the preregistered overlap
and control-ESS gates. In addition, the first final run used the wrong population for its propensity
nuisance; campaign-18 outcomes are burned and the corrected result is diagnostic only.

**Overall Layer 3 status: MIXED / INCOMPLETE.** This pass proves that the method can recover known
effects in a controlled data-generating process with observed assignment and measured confounders.
It does not prove that campaign uplift is identified in Dunnhumby or transportable to a merchant.

## 1. Preregistration and freeze discipline

All generators, estimators, metrics, thresholds, evidence labels, seeds, and Dunnhumby availability
rules were frozen in [LAYER3_VALIDATION_PREREGISTRATION.md](/Users/madsflyvholm/Desktop/decision%20layer/docs/LAYER3_VALIDATION_PREREGISTRATION.md)
before synthetic outcome evaluation.

For each synthetic seed/scenario:

1. observed features, assignment, and outcomes entered the estimator;
2. the effect estimate and interval were appended to the existing Prediction Ledger;
3. only then was oracle truth read for bias, RMSE, segment error, and coverage;
4. realized oracle results were appended once through the ledger outcome interface.

Acceptance thresholds were not changed after results were observed.

## 2. Shared implementation

No parallel evidence or action system was introduced. The work reuses:

- `ActionDefinition`, `ActionEvidence`, and existing action families;
- existing evidence types;
- `EvidenceBoundAnswerRenderer`;
- append-only `PredictionLedger` and append-once realized outcomes;
- deterministic seeds;
- existing Online Retail II fail-closed action behavior.

The new `action_evidence_for_dataset` bridge requires observed assignment, valid overlap, and a
frozen backtest before Dunnhumby may return `CAUSAL_OBSERVATIONAL`. Online Retail II continues to
return `INSUFFICIENT`. Dunnhumby can never receive `CAUSAL_RCT` merely because campaign assignment
is recorded.

## 3. Track A generator

The deterministic generator creates 20,000 pseudonymous customers per seed with:

- two continuous pre-treatment covariates;
- a three-level customer segment;
- nonlinear baseline purchase risk;
- true additive purchase uplift of 0.02, 0.05, or 0.08 by segment;
- randomized or confounded treatment assignment;
- Bernoulli purchase outcomes;
- a zero-effect placebo scenario.

Scenarios:

1. `randomized`: treatment is Bernoulli(0.5), independent of customer state;
2. `confounded`: high-baseline-propensity customers are more likely to receive treatment;
3. `placebo`: randomized assignment with true uplift exactly zero.

The benchmark ran seeds 0–99: 100 valid seeds per scenario and six million customer observations in
total.

## 4. Estimator

The adjusted estimator is five-fold cross-fitted AIPW/doubly robust estimation:

```text
ψᵢ = m₁(Xᵢ) - m₀(Xᵢ)
     + Tᵢ(Yᵢ - m₁(Xᵢ)) / e(Xᵢ)
     - (1-Tᵢ)(Yᵢ - m₀(Xᵢ)) / (1-e(Xᵢ))
```

where:

- `e(X)` is a logistic treatment-propensity nuisance;
- `m0(X)` and `m1(X)` are arm-specific logistic outcome nuisances;
- nuisances use the preregistered nonlinear pre-treatment basis;
- no row receives a nuisance prediction from a model trained on that row;
- propensities are clipped to `[0.02, 0.98]`, with clipping reported;
- ATE is the mean orthogonal pseudo-outcome;
- segment effects are pseudo-outcome means within frozen segments;
- nominal 95% intervals use the influence-function standard error.

Naive difference-in-means is retained as a deliberate negative-control estimator.

## 5. Randomized recovery results

| Metric | Result | Preregistered criterion | Pass |
|---|---:|---:|---|
| Mean true ATE | 0.050018 | — | — |
| Mean adjusted ATE | 0.050012 | — | — |
| Adjusted bias | -0.0000066 | absolute bias < 0.005 | PASS |
| Adjusted RMSE | 0.005796 | < 0.010 | PASS |
| Mean absolute segment error | 0.007189 | < 0.010 | PASS |
| Segment-assigned CATE RMSE | 0.008422 | reported | — |
| Nominal 95% coverage | 0.93 | 0.88–0.99 | PASS |
| Valid seeds | 100 | at least 95 | PASS |
| Mean overlap fraction | 1.000 | diagnostic | — |
| Mean clipped fraction | 0.000 | diagnostic | — |

The adjusted engine recovered both the aggregate effect and the heterogeneous segment pattern. A
matching total did not hide large segment errors under the preregistered segment criterion.

Evidence label: `CAUSAL_RCT` within the synthetic randomized validation universe only.

## 6. Confounding stress test

| Metric | Naive | Adjusted AIPW |
|---|---:|---:|
| Mean true ATE | 0.050018 | 0.050018 |
| Mean estimate | 0.151303 | 0.049757 |
| Bias | +0.101285 | -0.000261 |
| RMSE | 0.101446 | 0.006602 |

Additional diagnostics:

- mean segment absolute error: 0.009813;
- nominal interval coverage: 0.97;
- mean overlap fraction: 0.9832;
- mean clipped fraction: 0.00169;
- mean treated ESS: 6,017;
- mean control ESS: 6,883.

Preregistered confounding criteria:

- naive absolute bias at least 0.010: PASS;
- adjusted absolute bias no more than 60% of naive bias: PASS.

The adjusted absolute bias is approximately 0.26% of the naive absolute bias. This verifies recovery
under this measured-confounding DGP. It does not prove ignorability in real observational data.

Evidence label: `CAUSAL_OBSERVATIONAL`, with measured-confounding and positivity assumptions.

## 7. Placebo/null-effect test

| Metric | Result | Criterion | Pass |
|---|---:|---:|---|
| True effect | 0 | — | — |
| Mean adjusted estimate | -0.0000107 | absolute mean < 0.005 | PASS |
| False-positive rate | 0.04 | <= 0.10 | PASS |
| Nominal 95% coverage | 0.96 | diagnostic | — |

The engine did not manufacture a systematic effect when oracle uplift was zero.

## 8. Track A verdict

All nine preregistered conditions passed:

- randomized bias;
- randomized RMSE;
- randomized segment error;
- randomized interval coverage;
- placebo mean;
- placebo false-positive rate;
- demonstrable naive confounding bias;
- material adjusted bias reduction;
- valid seed count.

**Track A verdict: PASS.**

## 9. Dunnhumby ingestion and provenance

The data was acquired through the archived CRAN `completejourney` 1.1.0 package and the full
`transactions.rds` URL documented in its own source. The package `DESCRIPTION` states `License:
CC0`. Package and transaction hashes were verified and persisted.

This is the package's full **one-year, 2,469-household universe**, not the larger original two-year
Source Files release. All 1,559 campaign-assigned households occur in its 1,469,307 transaction
lines, making the selected preregistered action temporally evaluable, but conclusions are scoped to
this CRAN universe.

Actual counts:

- 1,469,307 transaction lines and 155,848 baskets;
- 2,469 households;
- 92,331 products;
- 6,589 campaign assignments across 27 campaigns;
- 116,204 coupon-product-campaign rows;
- 2,102 coupon redemptions.

`scripts/prepare_dunnhumby.py` accepts a configurable raw directory, source reference,
license/terms reference, and output directory.

Required concepts:

- transaction data;
- product;
- campaign table;
- campaign description;
- coupon;
- coupon redemption.

For every supplied file it validates required columns, streams CSV/CSV.GZ to Parquet, and records:

- raw filename;
- SHA-256;
- raw schema;
- row count;
- processed filename;
- source and license/terms;
- placement/retrieval time;
- observed versus derived fields;
- canonical mappings.

Real ingestion and fixture validation passed for all six concepts. Coupon redemption is explicitly
engagement, not treatment assignment.

## 10. Actual Dunnhumby backtest

The locked cutoff is 2017-09-20. Fifteen eligible campaigns occur before it and six eligible
campaigns occur at/after it with complete 30-day outcome windows. Campaign 18 was selected without
outcomes because it had the largest qualified treated support.

| Item | Result |
|---|---:|
| Campaign | 18 |
| Start | 2017-10-30 |
| Households | 2,469 |
| Treated | 1,133 |
| Comparison | 1,336 |
| Frozen transported uplift | +0.05474 |
| Naive observed difference | +0.19814 |
| Corrected diagnostic AIPW effect | +0.00523 |
| AIPW standard error | 0.01439 |
| AIPW 95% interval | [-0.02298, 0.03344] |

The adjusted effect is not statistically distinguishable from zero. The large naive difference is
mostly removed by pre-exposure adjustment, consistent with strong targeted-assignment confounding.
This does not prove that the adjusted estimate eliminates hidden confounding.

Diagnostics:

| Gate/diagnostic | Result | Requirement | Pass |
|---|---:|---:|---|
| Treated ESS | 714.7 | >= 200 | PASS |
| Control ESS | 166.3 | >= 200 | **FAIL** |
| Propensity overlap | 79.91% | >= 80% | **FAIL** |
| Fraction clipped | 11.87% | report | — |
| Max SMD before weighting | 1.399 | report | — |
| Max SMD after weighting | 0.360 | report | — |
| A/A outcome p-value | 0.441 | >= 0.05 | PASS |
| A/A SRM p-value | 0.572 | no SRM | PASS |

Frozen uplift calibration was unstable: the five predicted groups did not produce a monotone
realized DR effect, and the fourth group reversed sign. This further argues against customer-facing
uplift precision.

### Freeze/reveal incident

The first run trained propensity on pooled development campaign assignments, not cross-fitted
campaign-18 assignment. Although outcomes were properly excluded from the frozen predictions, this
was the wrong treatment-nuisance target. The invalid output is preserved as
`invalid_first_backtest_summary.json`.

The correction cross-fits campaign-18 treatment assignment while retaining outcome models trained
only on development campaigns. Because campaign-18 outcomes had already been revealed, the
corrected figures are diagnostic only. `untouched_final_implementation = false` is a hard failure.

Full status: [DUNNHUMBY_COMPLETE_JOURNEY_DATA_AUDIT.md](/Users/madsflyvholm/Desktop/decision%20layer/docs/DUNNHUMBY_COMPLETE_JOURNEY_DATA_AUDIT.md).

## 11. Track B verdict

**Track B verdict: INSUFFICIENT.**

Data acquisition and ingestion PASS. A/A and SRM PASS. Treatment overlap and control ESS FAIL. The
untouched-final invariant also FAILS after the propensity implementation defect. The official
evidence is therefore `INSUFFICIENT`, never `CAUSAL_RCT` and not customer-facing
`CAUSAL_OBSERVATIONAL`.

## 12. Query/evidence double proof

The same action contract now has two tested paths:

| Dataset state | Evidence result |
|---|---|
| Online Retail II, no assignment | `INSUFFICIENT` / NOT ENOUGH EVIDENCE |
| Dunnhumby if assignment + overlap + ESS + untouched freeze all pass | `CAUSAL_OBSERVATIONAL` with assumptions |
| Current Dunnhumby result: overlap/ESS/freeze failure | `INSUFFICIENT` |

The observational renderer says “Under the stated identification assumptions…”. It never uses
randomized wording. Existing safety rules were not weakened.

## 13. Economics

Synthetic outcomes are purchase probabilities. The ingested Dunnhumby universe contains observed
sales and discount fields but not contribution-profit economics. COGS, campaign
costs, shipping subsidies, cannibalization, and pull-forward remain unavailable unless explicitly
present and validated.

`profit_status = NOT_COMPUTABLE_MISSING_COST_FIELDS`

Revenue is not profit.

## 14. Files created or changed

### Source

- `src/decision_engine/causal/layer3_validation.py`
- `src/decision_engine/causal/dunnhumby_backtest.py`
- `src/decision_engine/datasets/dunnhumby.py`
- `src/commercial_twin/customer_twin_core.py`

### Scripts

- `scripts/generate_synthetic_uplift.py`
- `scripts/run_layer3_synthetic_validation.py`
- `scripts/download_completejourney_cran.py`
- `scripts/prepare_dunnhumby.py`
- `scripts/run_dunnhumby_layer3_backtest.py`

### Tests

- `tests/test_layer3_validation.py`

### Documentation

- `docs/LAYER3_VALIDATION_PREREGISTRATION.md`
- `docs/LAYER3_VALIDATION_REPORT.md`
- `docs/DUNNHUMBY_COMPLETE_JOURNEY_DATA_AUDIT.md`

### Artifacts

- `artifacts/layer3_validation/synthetic/summary.json`
- `artifacts/layer3_validation/synthetic/seed_results.json`
- `artifacts/layer3_validation/synthetic/prediction_ledger.duckdb`
- `artifacts/layer3_validation/dunnhumby/summary.json`
- `artifacts/layer3_validation/dunnhumby/frozen_prediction.json`
- `artifacts/layer3_validation/dunnhumby/prediction_ledger.duckdb`
- `artifacts/layer3_validation/dunnhumby/invalid_first_backtest_summary.json`

## 15. Tests and quality

New tests cover:

- randomized recovery of known uplift;
- confounding-bias demonstration and adjustment;
- zero-effect placebo interval;
- multi-seed interval-coverage fixture;
- loud missing-Dunnhumby failure;
- six-file provenance/schema/hash generation;
- observational versus insufficient wording;
- the same action contract distinguishing Online Retail II from supported Dunnhumby evidence;
- existing ledger append-once semantics remain green.

Final repository gate:

| Check | Result |
|---|---|
| `ruff check .` | PASS |
| `mypy src` | PASS — 115 source files |
| `pytest -q` | PASS — 159 tests |

## 16. What this proves

This pass proves that:

- the implemented AIPW engine is approximately unbiased under randomized assignment in the frozen
  synthetic DGP;
- it recovers heterogeneous segment effects within preregistered error;
- its nominal 95% uncertainty has acceptable empirical coverage across 100 seeds;
- it does not systematically invent uplift under a zero-effect placebo;
- measured-confounding adjustment can dramatically outperform naive comparison when the necessary
  pre-treatment confounders are observed;
- effect estimates can be frozen and evaluated through the existing Prediction Ledger;
- evidence wording and dataset support remain fail-closed.

## 17. What this does not prove

It does not prove that:

- hidden/unmeasured confounding is solved;
- Dunnhumby campaign assignment satisfies ignorability or positivity;
- the corrected Dunnhumby diagnostic is an untouched final validation;
- synthetic calibration transfers to a merchant;
- Criteo advertising effects transfer to email, coupon, offer, or discount actions;
- any individual treatment effect is observed;
- campaign revenue equals incremental contribution profit;
- a random future customer should receive a specific action.

## Final answer

The Layer 3 engine **passed the synthetic ground-truth test**. It recovered the known randomized ATE
and segment heterogeneity, produced 93% coverage for nominal 95% intervals, passed the null placebo,
and removed the large measured-confounding bias that broke the naive estimator.

The Dunnhumby backtest was run, but its official evidence is **INSUFFICIENT**. The adjusted diagnostic
effect was +0.00523 with a 95% interval from -0.02298 to +0.03344, versus a naive +0.19814. A/A and
SRM passed, but overlap was 79.91%, control ESS was 166.3, and the first final implementation defect
burned campaign 18. Another untouched target campaign/dataset is required for a valid final claim.

Therefore the honest distinction is:

> The method works in a controlled universe where assignment and relevant confounders are observed.
> We have not yet shown that a real merchant campaign effect is identifiable or transportable.
