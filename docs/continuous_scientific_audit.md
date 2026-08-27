# Continuous-treatment scientific audit (pre-change)

Date: 2026-08-25

This note records the behavior observed before the continuous causal repair pass.

## Existing estimation

`ContinuousOutcomeRegression` fits log-sales on discount and optional pre-treatment
features. Its `naive`, `elasticity`, and `flexible` variants are outcome regressions;
none has an orthogonal or inverse-density correction. `GaussianGeneralizedPropensity`
estimates a conditional Gaussian density but is diagnostic-only and is not consumed by
the estimator.

## Existing support and decisions

`continuous_dose_support` counts observations around a candidate dose in the complete
training population. It does not condition on store/SKU/state and therefore answers
whether a dose occurred anywhere, not whether comparable observations received it.
The decision engine refuses only globally out-of-range/weak candidates. In the v3
definitive benchmark this produced zero aggregate abstention in good, weak, and bad
support regimes.

## Existing uncertainty and calibration

There is chronological conformal calibration for forecasts, but no estimator-level
counterfactual bootstrap for continuous treatments. Continuous recommendations expose
point profit only. The benchmark does not calculate counterfactual interval coverage,
width, calibration error, or WIS.

## Existing benchmark

The v3 benchmark uses a chronological 70/30 split over 20 truth-known synthetic worlds
and compares naive, elasticity, and flexible outcome regression. Measured and hidden
confounding are present but pooled in aggregate reporting. Oracle arrays are evaluation
only. The final verdict is FAIL for causal dose response, calibration, and abstention.

## Existing boundaries to preserve

- Truth remains outside the estimator frame.
- Causal estimation produces response estimates; economics transforms them to profit.
- Evidence and support gate decisions rather than being hidden in model scores.
- Benchmark results persist separately from source data through Parquet/JSON/Markdown
  and the model registry.
- The dashboard remains a research view labelled synthetic, not commercial evidence.
