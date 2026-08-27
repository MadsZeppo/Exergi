# COMMERCIAL TWIN — World State V1 progress report

**Repository:** `/Users/madsflyvholm/Desktop/decision layer`  
**Pass:** World State V1, causal challengers, uplift protocol and presentation contracts  
**Status:** Partial implementation with completed initial ablations; not a completed production or scientific sign-off

## 1. Objective

This pass asks one deliberately narrow question:

> Does adding real, point-in-time macro and consumer context measurably improve Commercial Twin prediction and calibration on historical data?

The implementation preserves the existing `CommercialTwin`, continuous doubly robust estimator, support gate, uncertainty, Prediction Ledger and ACT / EXPERIMENT / ABSTAIN policy. It does not replace the decision engine or introduce a synthetic purchasing-power score.

World-state effects are intended to enter as learned pre-treatment features. No scientific conclusion may rely on a manually chosen rule such as “gas prices change elasticity by 20%.”

## 2. What was inspected

The pass inspected the existing:

- commercial state and world-state schemas;
- continuous discount behavior model;
- Dominick's real-data runner and frozen prediction artifacts;
- continuous DR estimator and support gate;
- model registry and dashboard structure;
- Hillstrom randomized dataset integration;
- dependency configuration for optional causal libraries;
- existing tests and benchmark artifact conventions.

The repository was not a Git worktree at inspection time, so the file inventory below is based on the observed filesystem, not a Git diff.

## 3. Official data acquired

The following official-source extracts were cached locally:

| Signal family | Series | Source | Frequency | Geography | Historical-vintage status |
|---|---|---|---|---|---|
| Real disposable income | `DSPIC96` | FRED / BEA | Monthly | US national | Latest revised cache; not accepted for the 1990s backtest |
| Credit-card delinquency | `DRCCLACBS` | FRED / Federal Reserve | Quarterly | US national | Latest revised cache; not accepted for the 1990s backtest |
| Consumer sentiment | `UMCSENT` | FRED / University of Michigan | Monthly | US national | Latest/final delayed cache; not accepted for the 1990s backtest |
| Food-at-home CPI | `CUUR0000SAF11` | BLS | Monthly, NSA | US national | Treated as final and usable with conservative availability dates |
| Regular gasoline | `EMM_EPMR_PTE_NUS_DPG` | EIA | Weekly | US national | Latest revised cache; not accepted for the 1990s backtest |
| Regular gasoline | `EMM_EPMR_PTE_STX_DPG` | EIA | Weekly | Texas | Begins in 2000; unavailable for Dominick's period |

Cached files:

- `data/world_state/raw/fred/DSPIC96.csv`
- `data/world_state/raw/fred/DRCCLACBS.csv`
- `data/world_state/raw/fred/UMCSENT.csv`
- `data/world_state/raw/bls/CUUR0000SAF11_1989_1998.json`
- `data/world_state/raw/bls/CUUR0000SAF11_2017_2026.json`
- `data/world_state/raw/eia/EMM_EPMR_PTE_NUS_DPGw.xls`
- `data/world_state/raw/eia/EMM_EPMR_PTE_NUS_DPGw.xlsx`
- `data/world_state/raw/eia/EMM_EPMR_PTE_STX_DPGw.xls`
- `data/world_state/raw/eia/EMM_EPMR_PTE_STX_DPGw.xlsx`
- `data/world_state/processed/eia_gas_NUS.csv`
- `data/world_state/processed/eia_gas_STX.csv`

The current BLS extract was downloaded at the end of the pass, but the provider has not yet been updated to combine both BLS cache windows. It must therefore not yet be treated as a completed current-state CPI integration.

## 4. World State contracts and provider

### Extended typed contracts

`WorldSignal` was extended to retain point-in-time and provenance fields:

- observation period;
- `available_at`;
- `retrieved_at`;
- source and series ID;
- frequency;
- actual and requested geography;
- geographic fallback level;
- vintage label;
- signal age;
- provenance metadata.

`WorldState` now also carries requested geography, commerce category and explicit unavailable-signal reasons.

### Cached provider

`src/commercial_twin/world_state.py` introduces:

- a `WorldStateProvider` protocol;
- immutable `SeriesDefinition` metadata;
- `CachedWorldStateProvider`;
- category-to-CPI mapping;
- state-to-national fallback when no defensible local series exists;
- point-in-time filtering using `available_at <= as_of`;
- conservative publication timing;
- explicit rejection of latest-revised series in old historical backtests;
- derived level, short-delta, year-over-year delta, trailing z-score and trend-deviation features;
- coverage reporting, staleness metadata and a feature-row interface.

For a historical 1996 Dominick's request, only category CPI is admitted. Income, credit stress, sentiment and gasoline are returned as unavailable with `NOT_TESTABLE_ON_DOMINICKS`; their revised current downloads are not allowed to leak into the historical evaluation.

Consumer sentiment remains national. A request for Texas may fall back to US national and must retain `requested_geography=TX`, actual geography `US` and fallback `NATIONAL`. No fabricated state sentiment was created.

## 5. Historical World State ablation

`src/domains/commerce/world_ablation.py` and `scripts/run_world_state_ablation.py` implement a chronological Dominick's Oatmeal ablation.

The comparison is:

- **Model A:** customer and company features only;
- **Model D:** the same features plus five point-in-time category-CPI features;
- **Model G:** model selected exclusively on the development period and then frozen for the final holdout.

The frozen cutoffs are:

- development cutoff: `1995-12-28 00:00:00+00:00`;
- final cutoff: `1996-02-22 00:00:00+00:00`.

Selection used minimum development factual DR demand MAE. The final holdout was not used for model choice. Models requiring income, credit stress, sentiment or gasoline could not be honestly evaluated for this period and were not silently filled with revised or fabricated values.

### Development results

| Metric | Model A | Model D + CPI | Direction |
|---|---:|---:|---|
| DR factual demand MAE | 15.7213 | 13.8007 | CPI better |
| DR factual demand RMSE | 35.3293 | 31.8564 | CPI better |
| Demand bias | -12.6719 | -8.0441 | CPI better |
| Revenue MAE | 30.4487 | 27.5439 | CPI better |
| Contribution-profit MAE | 6.3781 | 6.3039 | CPI slightly better |
| 90% coverage | 92.58% | 92.97% | Similar |
| Mean interval width | 65.5938 | 66.5080 | CPI wider |
| Single-interval WIS | 170.9090 | 151.6848 | CPI better |

Model D was selected on the development data.

### Frozen final results

| Metric | Model A | Model D / G + CPI | Relative interpretation |
|---|---:|---:|---|
| DR factual demand MAE | 4.4693 | 4.3871 | about 1.84% better |
| DR factual demand RMSE | 5.8232 | 5.6120 | about 3.63% better |
| Demand bias | 0.8785 | 1.0283 | worse |
| Revenue MAE | 12.3961 | 12.2282 | about 1.35% better |
| Contribution-profit MAE | 2.6591 | 2.6220 | about 1.40% better |
| 90% coverage | 100% | 100% | no calibration gain demonstrated |
| Mean interval width | 64.7934 | 65.6382 | CPI wider |
| Single-interval WIS | 64.7934 | 65.6382 | CPI worse |

The final evaluation contains 510 rows. Its action evaluation is explicitly **factual prediction only** at the observed discount dose, binned to the nearest percentage point. It is not proof of counterfactual commercial validity.

### Ablation verdict

**World State V1 factual prediction: MIXED.**

Category CPI produced small out-of-sample improvements in demand, revenue and contribution-profit point error. It did not improve the reported 90% interval calibration: both models over-covered, while the CPI model had wider intervals and worse final WIS. The result supports further evaluation of CPI as a feature; it does not establish that World State broadly improves the Commercial Twin.

## 6. Optional causal challengers

`src/decision_engine/causal/challengers.py` adds optional wrappers for:

- DoWhy binary-treatment identification, estimation and placebo refutation;
- EconML `LinearDML` with random-forest nuisance models for a continuous-treatment challenger.

Both integrations fail closed with a typed `NOT_INSTALLED` result when the optional dependency is absent. Neither library was installed in the inspected environment, so no challenger comparison was run and no claim can be made that a challenger beat—or validated—the repository estimator.

These are challengers and validators only. They do not replace the existing continuous DR estimator.

## 7. Uplift protocol and Hillstrom result

The pass added:

- an `UpliftModel` protocol;
- a two-model/T-learner uplift implementation;
- AUUC and Qini evaluation;
- a Hillstrom Mens-email-versus-control benchmark with a stratified train/test split.

The random split is defensible here because Hillstrom is a cross-sectional randomized experiment; it is not being used as a precedent for randomly splitting retail time series.

| Hillstrom metric | Result |
|---|---:|
| Training rows | 27,698 |
| Test rows | 14,915 |
| AUUC | 0.001708 |
| Qini | 0.000133 |
| Estimated final incremental conversions | 46.994 |

Interpretation: ranking value is positive but very small. This validates only a discrete randomized email-uplift evaluation path. It does not validate discount-dose response, World State, pricing decisions or business uplift in another dataset.

## 8. Presentation contracts

`src/commercial_twin/presentation.py` adds typed, presentation-only contracts:

- `DecisionOpportunity`;
- `WhatIfCard`;
- `CommercialTwinView`;
- `build_commercial_twin_view`.

The mapping is intentionally plain-language:

- `ACT` → `DO THIS`;
- `EXPERIMENT` → `TEST THIS`;
- `ABSTAIN` → `NOT ENOUGH EVIDENCE`.

Cards expose expected demand, revenue and contribution-profit intervals plus support, evidence, uncertainty and assumptions under a “why” payload. These contracts do not change scientific decision logic.

## 9. Files created or materially changed

### Source and scripts

- Modified: `src/commercial_twin/schemas.py`
- Created: `src/commercial_twin/world_state.py`
- Created: `src/domains/commerce/world_ablation.py`
- Created: `scripts/run_world_state_ablation.py`
- Created: `src/decision_engine/causal/challengers.py`
- Created: `src/decision_engine/causal/uplift.py`
- Created: `src/decision_engine/benchmark/uplift.py`
- Created: `src/commercial_twin/presentation.py`

### Generated artifacts

- `artifacts/world_state/dominicks-oatmeal-v1/world_ablation.json`
- `artifacts/world_state/dominicks-oatmeal-v1/world_ablation_results.parquet`
- `artifacts/world_state/hillstrom_uplift.json`

### Data cache

The official cached files listed in section 3 were added under `data/world_state/`.

## 10. Work not completed in this interrupted pass

The following items remain open and must not be reported as complete:

1. Combine the historical and current BLS cache windows in the provider and verify current-state staleness behavior.
2. Remove the old hard-coded `_world_multiplier` from `ContinuousDiscountBehaviorModel`; it still contains manual coefficients and therefore conflicts with the new scientific rule.
3. Feed World State only through model features learned during fitting.
4. Add complete automated tests for availability dates, vintage isolation, geography fallback, staleness, frequency alignment, missing signals and category mapping.
5. Add tests for optional DoWhy/EconML behavior, uplift metrics and presentation contracts.
6. Extend the model registry with the factual/causal/calibration/regret tournament record.
7. Add the requested lightweight COMMERCIAL TWIN dashboard tab without redesigning Streamlit.
8. Generate current snapshot, integration-status and presentation artifacts.
9. Run and record the full `pytest -q`, `ruff check .` and `mypy` gates after all changes.

The last known repository-wide test state before this World State pass was 81 passing tests with Ruff and MyPy green. That is not a validation of the new files. No post-pass all-green claim is made here.

## 11. Scientific conclusions so far

### What the evidence supports

- Real official data can populate a typed World State with explicit provenance and geography.
- Historical evaluation can refuse revised series whose historical vintages are unavailable.
- Category CPI added small factual point-prediction value on the frozen Dominick's final period.
- The Hillstrom path can evaluate heterogeneous uplift on randomized binary treatment data.
- Optional established causal packages can be isolated as challengers rather than silently replacing the engine.

### What remains unproven

- World State does not yet have a demonstrated calibration benefit.
- Income, credit stress, sentiment and gasoline have not been evaluated on Dominick's.
- The CPI result does not prove a causal effect of inflation on demand.
- Counterfactual discount validity on real retail data remains unproven.
- No real-data `ACT` recommendation has been established.
- Hidden confounding has not been ruled out.
- Optional DoWhy/EconML validators have not run in this environment.
- The new implementation has not yet passed the full automated quality gate.

## 12. Bottom line

The initial World State V1 pass produced one honest signal rather than a broad victory: point-in-time category CPI modestly improved factual error on the frozen Dominick's holdout, but did not improve interval calibration. The correct current verdict is therefore **MIXED and incomplete**.

The key architectural direction is sound—official sources, explicit geography, release-time filtering, vintage refusal and learned features—but the legacy manual world multiplier must be removed and the remaining tests and integrations must be completed before this pass can be considered finished.
