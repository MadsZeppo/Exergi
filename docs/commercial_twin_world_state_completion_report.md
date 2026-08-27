# Commercial Twin — World State completion report

**Completed:** 2026-08-25  
**Repository:** `/Users/madsflyvholm/Desktop/decision layer`  
**Overall verdict:** Engineering pass complete; scientific product validation remains incomplete

## Executive result

Commercial Twin now has a generic US geography/exposure contract, a current official-source World State snapshot, no manual macro-to-behavior multiplier, learned-feature-only World State injection, a modern synthetic-oracle World State benchmark, a strict MT-LIFT adapter/protocol, a customer-facing product view, a proactive opportunity contract, an expanded registry and a first-customer data contract.

The real randomized MT-LIFT benchmark was **not run**. Its publisher reports 5,541,842 rows, but the data is hosted behind an external Google Drive download and the publisher repository contains no explicit license. The implementation therefore stops at `READY_FOR_DATA` rather than silently downloading or redistributing it.

## 1. Previous incomplete tasks finished

- Historical and current BLS Food-at-Home CPI cache windows are combined and deduplicated.
- Missing/non-numeric BLS observations are rejected.
- `_world_multiplier` was removed.
- World State enters behavior prediction only through columns present during model fitting.
- Point-in-time, geography, fallback, category, frequency, staleness and exposure tests were added.
- Optional DoWhy/EconML absence is tested and fails closed.
- `ModelPerformanceRegistry` gained a behavior-model tournament table.
- A `COMMERCIAL TWIN` research-dashboard tab was added.
- Current World State and product-presentation artifacts were generated.
- The complete test/lint/type quality gate was run.

## 2. Is `_world_multiplier` fully gone?

Yes. No `_world_multiplier` remains in the simulation path. Unknown or untrained World State signals produce no behavior adjustment. A regression test verifies identical predictions when only untrained World State signals change and verifies that no `world_multiplier` evidence field is emitted.

The only allowed path is:

`trained pre-treatment World State feature → fitted nuisance/behavior model → prediction`

## 3. Supported US geographic levels

- `COUNTRY` / US national;
- `REGION` architecture using the four US Census regions;
- `STATE` for all 50 states plus DC;
- `AGGREGATED` for a weighted customer/revenue/order exposure.

County is deliberately not implemented.

## 4. Can any state request resolve generically?

Yes. Full state names and two-letter codes normalize generically. Resolution is:

`STATE → CENSUS REGION → US NATIONAL → NOT_AVAILABLE`

The actual current cache contains a Texas-specific EIA gasoline series. Other state requests currently fall back to national gas because no additional state/regional source extracts are cached. The architecture discovers compatible cached EIA state files; Texas is not special-cased in decision logic.

## 5. Existing World State signals

- Real disposable personal income: FRED/BEA `DSPIC96`;
- credit-card delinquency: FRED/Federal Reserve `DRCCLACBS`;
- category CPI with explicit mapping: BLS;
- consumer sentiment: FRED/University of Michigan `UMCSENT`;
- regular gasoline: EIA.

Each produces level, short change, year-over-year change, trailing z-score and trend-deviation features where history permits.

## 6. National signals

Income, credit stress and sentiment are national. Food-at-Home CPI is national in the current cache. National signals remain labeled `US/NATIONAL`; they are not relabeled as state estimates.

## 7. State/regional signals

The current cache contains Texas state gasoline and national gasoline. The regional resolution layer exists, but no regional EIA extract is presently cached. Apparel (`CUUR0000SAA`) and household furnishings (`CUUR0000SAH3`) mappings exist but are returned as `SERIES_NOT_CACHED`; the system never substitutes Food-at-Home CPI under another category label.

## 8. Customer geographic exposure aggregation

`GeographicExposure` accepts `customer_share`, `revenue_share` or `order_share`; positive weights must sum to one. Geography-aware values are weighted across resolved state/regional/national contributions. Every contribution retains requested geography, weight, resolved geography, fallback level and raw value.

If every exposure resolves to the same national series, it is emitted once rather than duplicated across states. Mixed state/national values are aggregated, while the underlying contribution table remains visible.

## 9. Current US World State example

Snapshot time: `2026-08-25T14:44:32Z`. Example exposure: CA 31%, TX 18%, NY 11%, FL 8%, IL 7%, US/other 25%.

| Signal | Current cached value | Resolution | Age at snapshot |
|---|---:|---|---:|
| Real disposable income | 18,056.1 | US national | 24.6 days |
| Credit-card delinquency | 2.92 | US national | 146.6 days |
| Food-at-Home CPI | 321.631 | US national | 24.6 days |
| Consumer sentiment | 49.5 | US national | 24.6 days |
| Exposure-weighted gasoline | 3.9716 | Mixed/aggregated | 5.6 days |

Values retain source units; they are not collapsed to a synthetic 0–100 score.

## 10. Point-in-time/vintage safety

Every signal retains observation period, availability time, retrieval time, source, series ID, frequency, resolved/requested geography, fallback reason, vintage label and signal age. The hard rule is `available_at <= simulation_time`.

The cached FRED and EIA histories are latest-revised rather than reconstructed real-time vintages. They are accepted for current context but rejected for strict old historical replay. Dominick's therefore admits only conservatively released, non-seasonally adjusted category CPI. Revised income, credit, sentiment and gas are reported `NOT_TESTABLE_ON_DOMINICKS`.

## 11. Dominick's World State ablation

On the frozen 510-row final holdout:

| Metric | Customer + Company | + Category CPI |
|---|---:|---:|
| Factual demand MAE | 4.4693 | 4.3871 |
| Factual demand RMSE | 5.8232 | 5.6120 |
| Revenue MAE | 12.3961 | 12.2282 |
| Contribution-profit MAE | 2.6591 | 2.6220 |
| Demand bias | 0.8785 | 1.0283 |
| 90% coverage | 100% | 100% |
| Mean interval width | 64.7934 | 65.6382 |
| WIS | 64.7934 | 65.6382 |

Verdict: **MIXED**. CPI modestly improved point error but worsened bias, interval width and WIS. This is factual prediction evidence only, not real counterfactual proof.

## 12. Signals that improved performance

Food-at-Home category CPI modestly improved final factual demand, revenue and contribution-profit errors.

## 13. Signals that hurt or remained neutral

CPI harmed final bias, interval width and WIS; coverage was unchanged at an over-wide 100%. Income, credit, sentiment and energy were not testable on Dominick's without unsafe vintages and therefore are not labeled improve/neutral/harm.

## 14. Recency-weighting results

The modern Track A development tournament compared no decay and 6-, 12- and 24-month half-lives. Selection used development factual MAE only:

| Policy | Development MAE |
|---|---:|
| No decay | 0.38666 |
| 6 months | **0.38596** |
| 12 months | 0.38849 |
| 24 months | 0.38966 |

The 6-month half-life was frozen for final evaluation. This result belongs only to the synthetic-behavior Track A world and is not a recommended universal production decay.

## 15. Was MT-LIFT integrated?

The typed `MTLiftAdapter`, schema validation, publisher train/test separation and freeze-before-reveal benchmark pipeline are implemented and fixture-tested. The full publisher data was not downloaded, so the actual MT-LIFT benchmark is not complete.

## 16. MT-LIFT size

Publisher-reported: 5,541,842 observations, 99 anonymized features, five treatment arms, click and conversion outcomes.

## 17–20. MT-LIFT treatment ranking, effect, policy value and calibration

**NOT RUN.** No numeric result is reported. The local artifact states `READY_FOR_DATA`, `dataset_present=false`, `benchmark_run=false` and records the absent explicit repository license.

## 21. Did Commercial Twin beat simple baselines?

On modern Track A—**synthetic behavior with real official World State inputs**—adding World State improved final MAE from 0.5140 to 0.4452, policy accuracy from 45.68% to 65.00%, and oracle policy regret from 0.0771 to 0.0421. This demonstrates plumbing and recoverability in a known synthetic DGP only.

No claim is made that Commercial Twin beat baselines on full MT-LIFT.

## 22. EconML challenger results

`NOT_INSTALLED`. The optional integration returns a typed status and is tested. No numeric challenger result exists.

## 23. DoWhy refutation results

`NOT_INSTALLED`. The optional integration returns a typed status and is tested. No refutation result exists.

## 24. Hillstrom status

Hillstrom remains the fast real randomized regression benchmark. The existing Mens-email versus control uplift run used 27,698 train and 14,915 test rows, with AUUC 0.001708 and Qini 0.000133. Ranking value was positive but very small. It is email evidence, not discount or World State evidence.

## 25. Product demo result

The generated end-to-end view asks about 5%, 10% and 20% discounts for a synthetic modern US brand using the real current World State snapshot:

- 5%: `TEST THIS` / limited support;
- 10%: `TEST THIS` / limited support;
- 20%: `NOT ENOUGH EVIDENCE` / unsupported.

It is labeled **SYNTHETIC BEHAVIOR — REAL WORLD SIGNALS** and `commercial_validity=NOT_ESTABLISHED`.

## 26. Proactive opportunity result

The proactive path flags review of 5% instead of the current 10% synthetic plan. Modeled contribution-profit delta is approximately 2,032.78 in fixture units. Priority is `REVIEW_ONLY`, because the recommended candidate is still `EXPERIMENT`, not `ACT`.

## 27. First real customer data contract

`FIRST_CUSTOMER_DATA_CONTRACT.md` is complete. It specifies required transactions, pseudonymous customer/order IDs, SKU/category, quantity, list/actual price, discount, geography, treatment assignment metadata and COGS requirements; high-value context; temporal/causal rules; quality checks; security; and readiness deliverables.

## 28–30. Quality gate

- `pytest -q`: **PASS — 100 tests**.
- `ruff check .`: **PASS**.
- `mypy`: **PASS — 94 source files**.

One non-failing local joblib warning reported unavailable physical-core detection.

## 31. What remains scientifically unproven

- Real counterfactual discount validity remains unproven.
- Full MT-LIFT action-response performance remains unmeasured.
- World State calibration improvement is not demonstrated on Dominick's.
- Track A is synthetic behavior and cannot establish commercial validity.
- Current FRED/EIA caches are not historical vintage archives.
- Only Texas-specific gasoline is currently cached at state level; regional coverage is architectural, not populated.
- Apparel and home-furnishings CPI mappings are not yet backed by cached extracts.
- DoWhy/EconML challengers have not run.
- Hidden confounding is not ruled out.
- No real-customer `ACT` has been earned.

## 32. Exact next step

Obtain explicit permission/terms and the publisher-provided MT-LIFT train/test files, hash and profile them, then run the frozen multi-arm tournament and register treatment ranking, randomized policy value, calibration and regret. In parallel, onboard one modern US brand using `FIRST_CUSTOMER_DATA_CONTRACT.md` and pre-register a prospective randomized promotion validation. Do not add more product scope before those action-response results exist.

## Files and artifacts

Important new or changed paths include:

- `src/commercial_twin/schemas.py`
- `src/commercial_twin/world_state.py`
- `src/domains/commerce/behavior.py`
- `src/domains/commerce/world_ablation.py`
- `src/domains/commerce/modern_world_benchmark.py`
- `src/decision_engine/datasets/mt_lift.py`
- `src/decision_engine/benchmark/mt_lift.py`
- `src/decision_engine/causal/challengers.py`
- `src/decision_engine/causal/uplift.py`
- `src/decision_engine/registry/store.py`
- `src/commercial_twin/presentation.py`
- `apps/research_dashboard.py`
- `scripts/build_current_commercial_twin_artifacts.py`
- `scripts/run_modern_world_benchmark.py`
- `FIRST_CUSTOMER_DATA_CONTRACT.md`
- `artifacts/world_state/current/`
- `artifacts/world_state/ablation/`
- `artifacts/benchmarks/mt_lift/`
- `artifacts/benchmarks/hillstrom/`
- `artifacts/commercial_twin/product_demo/`
