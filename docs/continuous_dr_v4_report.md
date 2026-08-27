# Continuous DR scientific implementation report (v4)

Date: 2026-08-25

**SYNTHETIC — NOT COMMERCIAL EVIDENCE**

## 1. Inspected before modification

The audit covered continuous outcome regression and GPS diagnostics, the retail DGP and
oracle isolation, global dose support, evidence/confidence gates, contribution-profit
and action optimization, conformal/quantile uncertainty, the v3 continuous runner,
all continuous tests, the Streamlit tab, Prediction Ledger, and ModelPerformanceRegistry.
The frozen pre-change audit is in `docs/continuous_scientific_audit.md`.

## 2. Files created or materially changed

Created:

- `src/decision_engine/causal/continuous_dr.py`
- `src/decision_engine/uncertainty/continuous_bootstrap.py`
- `tests/test_continuous_dr.py`
- `docs/continuous_scientific_audit.md`
- `docs/continuous_dr_v4_report.md`

Changed:

- `src/decision_engine/causal/__init__.py`
- `src/decision_engine/decision/continuous_support.py`
- `src/decision_engine/decision/continuous_engine.py`
- `src/decision_engine/metrics/continuous.py`
- `src/decision_engine/uncertainty/__init__.py`
- `src/decision_engine/benchmark/continuous_retail.py`
- `scripts/run_continuous_retail_benchmark.py`
- `apps/research_dashboard.py`

The existing DGP was not changed.

## 3. Estimator

`ContinuousDRDoseResponseEstimator` estimates a plug-in response plus a localized,
inverse-density residual correction:

\[
\hat\mu(d)=\frac{1}{n}\sum_i \hat m(d,X_i)+
\frac{\sum_{i\in CF} K_h(D_i-d)\{Y_i-\hat m(D_i,X_i)\}/
\max(\hat f(D_i\mid X_i),f_{min})}
{\sum_{i\in CF} K_h(D_i-d)/\max(\hat f(D_i\mid X_i),f_{min})}.
\]

It is not another outcome-regression alias: treatment density participates directly in
the orthogonal correction. Assumptions are consistency, conditional exchangeability,
conditional positivity, and no interference for the single-treatment estimand.

## 4. Cross-fitting

Dates are sorted and divided into an initial block plus expanding validation blocks.
Each validation block receives nuisance predictions from earlier dates only. Initial
rows without earlier training history are excluded from the correction. Fold records
retain train/validation row IDs and date boundaries; tests assert disjoint rows and
strict temporal order.

## 5. Treatment density

Two swappable nuisances are available:

- conditional Gaussian density with a ridge mean model;
- flexible gradient-boosted conditional mean plus residual KDE.

The quick benchmark used residual KDE. Density clipping is explicit at 0.05. Across
the six worlds, mean clipped fraction was 6.38%, mean inverse-density ESS was 109.22,
minimum effective density was 0.05, and maximum inverse weight was 20. Diagnostics and
warnings are persisted; clipping is never silent.

## 6. ConditionalSupportGate

For every state/dose pair the gate reports conditional density, context-local ESS,
nearest comparable dose, kernel-weighted support, population-density ratio,
extrapolation distance, nearest supported region, optional nuisance disagreement,
reasons, and `SUPPORTED`/`LIMITED`/`UNSUPPORTED`.

Thresholds are typed, configurable, visible, and tested. Extreme density below 10% of
the configured minimum is severe. The hard invariant is enforced before constrained
optimization: an unsupported unconstrained optimum can never return ACT.

## 7. Counterfactual uncertainty

The deterministic blocked/clustered bootstrap resamples store-SKU clusters. Every valid
replicate refits cross-fitted outcome and density nuisances, re-estimates the DR curve,
and recomputes contribution profit. It exposes point estimate, bootstrap SE, 50/80/90/95
percentile intervals, valid/requested replicates, demand draws, and profit draws.

The bootstrap interface supports parallel execution, but the benchmark uses one worker:
concurrent HistGradientBoosting fits were empirically slower through CPU oversubscription.

## 8. Benchmark configuration

Artifact: `artifacts/benchmarks/continuous-retail/quick-dr-v4-final2/`

- Mode: quick
- Worlds: 6 (one measured and one hidden world for each good/weak/bad regime)
- Bootstrap replicates: 8 per world
- Chronological split: 70/30
- Dose grid: 0%–30% in two-percentage-point steps
- Estimators: naive, elasticity, flexible outcome regression, continuous DR
- Runtime: 102.85 seconds
- Oracle truth entered only after estimates and decisions were frozen

This is a development/quick benchmark, not a definitive validation. Quick-mode metrics
cannot receive PASS for causal recovery or calibration even when point criteria are met.

## 9. Estimator results

| Confounding | Estimator | RMSE | IAE | ISE | Discount MAE | Regret |
|---|---|---:|---:|---:|---:|---:|
| Measured | Continuous DR | 2.314 | 0.466 | 1.815 | 0.0377 | 1.979 |
| Measured | Naive | 6.393 | 1.368 | 12.760 | 0.0441 | 2.495 |
| Measured | Elasticity | 1.808 | 0.395 | 0.972 | 0.0419 | 2.480 |
| Measured | Flexible | 2.436 | 0.460 | 2.009 | 0.0299 | 1.327 |
| Hidden | Continuous DR | 1.927 | 0.402 | 1.125 | 0.0287 | 2.137 |
| Hidden | Naive | 5.295 | 1.186 | 8.836 | 0.0382 | 2.791 |
| Hidden | Elasticity | 2.339 | 0.512 | 1.609 | 0.0368 | 2.860 |
| Hidden | Flexible | 2.052 | 0.418 | 1.295 | 0.0262 | 1.772 |

## 10. Measured confounding

DR RMSE beat naive in 3/3 worlds, flexible outcome regression in 3/3, and elasticity in
1/3. DR had lower average economic regret than naive and elasticity, but higher regret
than flexible outcome regression. With only three measured worlds this is promising,
not definitive.

## 11. Hidden confounding

Results are separate and never interpreted as proof that DR repaired hidden confounding.
All three hidden worlds were downgraded to EXPERIMENT/ABSTAIN. Hidden-world 90% coverage
on supported/limited doses was only 63.2%, which is a clear failure signal.

## 12. Calibration

Coverage below is only on `SUPPORTED` and `LIMITED` doses; unsupported doses are still
reported in Parquet but excluded from the capability criterion.

| Confounding | Nominal | Coverage | Width | Interval score |
|---|---:|---:|---:|---:|
| Measured | 50% | 61.1% | 0.463 | 0.722 |
| Measured | 80% | 72.2% | 0.915 | 1.047 |
| Measured | 90% | 94.4% | 1.166 | 1.250 |
| Measured | 95% | 94.4% | 1.292 | 1.399 |
| Hidden | 50% | 40.0% | 0.542 | 1.450 |
| Hidden | 80% | 57.9% | 1.033 | 2.401 |
| Hidden | 90% | 63.2% | 1.151 | 3.632 |
| Hidden | 95% | 65.0% | 1.195 | 5.739 |

Measured 90% coverage is near nominal without unlimited width, but eight bootstrap draws
and three measured worlds are insufficient for a PASS claim.

## 13. Support and decisions

| Regime | ACT | EXPERIMENT | ABSTAIN | Withholding |
|---|---:|---:|---:|---:|
| Good | 0 | 0 | 2 | 100% |
| Weak | 0 | 2 | 0 | 100% |
| Bad | 0 | 0 | 2 | 100% |

Unsupported ACT count was exactly zero. However, bad support did not produce materially
more withholding than good support because all worlds withheld. The gate is safe but too
conservative to pass operational abstention.

## 14. Economic decisions and experiments

Estimation remains separate from contribution-profit transformation and constrained
optimization. Each dose has point/lower/upper profit, support, and evidence. Near-optimal
ranges combine an economically meaningful tolerance with bootstrap ranking uncertainty.
EXPERIMENT returns two supported candidate depths and normal-approximation sample sizing.
ABSTAIN now returns no dose or fake robust range.

## 15. Falsification

- Support-boundary stress: 6/6 PASS.
- Chronological holdout invariant: 6/6 PASS.
- Hidden-confounding evidence downgrade: 6/6 PASS.
- Grouped treatment shuffle: 5 PASS, 1 FAIL.
- Nuisance specification disagreement: persisted as decomposed informational evidence.
- Fake promotion dates: `NOT_APPLICABLE`; the static single-dose DGP has no date-defined
  promotion intervention, so a fabricated test would be meaningless.

No scalar “causal confidence percentage” was manufactured.

## 16. Persistence and dashboard

Artifacts include summary JSON, Markdown report, configuration/hash, estimator,
calibration, support, density, decision, falsification, and curve Parquets, plus the
ModelPerformanceRegistry. The Prediction Ledger was not forced into use because its
current public contract describes discrete `DecisionPrediction` action distributions;
inventing a lossy continuous mapping would weaken that contract.

The existing Streamlit continuous tab now shows estimated/oracle curves, 90% bands,
support, profit, decision aggregates, calibration, tournament, and verdict. It remains
labelled synthetic—not commercial evidence.

## 17. Automated verification

- `pytest -q`: 59 passed
- `ruff check .`: passed
- `mypy`: passed, 70 source files

## 18. Capability verdict

| Capability | Verdict | Reason |
|---|---|---|
| Causal dose response | MIXED | Strong quick wins vs naive/flexible; weak vs elasticity; too few worlds |
| Counterfactual calibration | MIXED | Measured supported 90% coverage 94.4%; quick bootstrap only |
| Operational abstention | FAIL | Zero unsupported ACT, but 100% withholding in every regime |
| Hidden-confounding behavior | MIXED | Evidence downgraded, but intervals under-cover strongly |
| Economic policy | MIXED | Regret improves vs some baselines, not flexible outcome regression |
| Overall | FAIL | Operational discrimination is not yet demonstrated |

## 19. What remains scientifically unproven

- Conditional exchangeability cannot be verified from observational data.
- DR does not solve hidden confounding.
- Six worlds/eight bootstraps do not establish interval calibration.
- No real continuous-discount retail benchmark has been run.
- No spillover or dynamic treatment effect is estimated.
- The support gate has not yet shown useful ACT behavior in realistic benchmark worlds.

## 20. Answer to the objective

**Not yet.** The engine now has the right estimator, density participation, uncertainty
pipeline, conditional support report, hard refusal invariant, and decomposed evidence.
On the quick truth-known benchmark it recovers a much better measured-confounding curve
than naive observation and never ACTs on an unsupported optimum. But it withholds in all
six worlds, hidden-confounding intervals under-cover, and the benchmark is too small for
definitive calibration claims. The right to move to real pricing data has therefore not
yet been earned; the next narrow task is to diagnose excessive good-support withholding
without weakening the zero-unsupported-ACT invariant, then run the configured definitive
24-world/100-bootstrap benchmark.
