# Conditional support gate v5 — diagnostic and repair report

Date: 2026-08-25

**SYNTHETIC — NOT COMMERCIAL EVIDENCE**

## Outcome

The repair gained one defensible ACT without introducing an unsupported ACT, but it did
not satisfy the requested good-support progression criterion. Overall operational
abstention therefore remains **FAIL**, and definitive mode was not run.

## Why v4 withheld 100%

The original headline attributed all withholding to support, but the persisted curves
showed two separate mechanisms:

1. Every selected good-world dose was marked `LIMITED`, because any local ESS below the
   `strong_local_ess=60` target caused a support downgrade—even when no minimum-support
   rule failed.
2. The decision layer then treated LIMITED as an automatic experiment trigger. For the
   measured good world, the estimated 8% optimum improved profit by only 0.806 (0.72%)
   versus 0%, below the configured 1% economic-action threshold. For the hidden good
   world, 0% was estimated best, intervals overlapped, and hidden-confounding sensitivity
   downgraded evidence.

Thus v4 withholding was not solely a positivity failure. Moderate ESS was the support
warning; economic advantage, interval overlap, and hidden confounding were separate
evidence reasons.

The implementation also found a real geometry defect: comparable contexts used strict
`weight > median`. Equal context weights selected zero comparables, producing infinite
nearest distance and a false hard failure. It now uses inclusive `>= median`.

## What changed

- Raw density remains reported but no longer controls support through a scale-dependent
  absolute threshold.
- Added density percentile relative to observed treatment densities and ratio to typical
  observed density.
- Added context ESS, kernel ESS, local dose spacing, conditional 1%–99% weighted dose
  region, density clipping, and explicit hard/soft rule records.
- Hard failures and soft warnings are separately typed and persisted.
- One soft warning cannot by itself veto ACT.
- Support reasons, evidence reasons, and the withholding layer are separate.
- Nearby supported projection is allowed only when profit loss is within 1% and dose
  distance is at most 0.04. Distant projection remains forbidden.
- A second parametric/Gaussian DR fit supplies a genuine DR specification-disagreement
  trace.
- Seven support ablations and post-hoc oracle support-quality metrics are persisted.
- No DGP or DR estimator redesign was performed.

## Frozen support rules

| Rule | Threshold | Severity |
|---|---:|---|
| Density percentile | < 1% | HARD |
| Density percentile | < 5% | SOFT |
| Density ratio to typical | < 0.02 | HARD |
| Kernel/local ESS | < 5 | HARD |
| Kernel/local ESS | < 20 | SOFT |
| Kernel/local ESS | < 60 | SOFT (`moderate_ess`) |
| Nearest comparable dose | > 0.04 | HARD |
| Nearest comparable dose | > 0.025 | SOFT |
| Conditional extrapolation | > 2.5 bandwidths | HARD |
| Non-finite/effectively zero density | true | HARD |

These defaults were not tuned against oracle optimal discounts. Oracle information was
used only after frozen decisions to score the quick benchmark. No threshold calibration
was performed, so no development/held-out claim is made.

## Good-world failure trace after repair

### Seed 0 — measured confounding

- Estimated optimum: 8%; constrained optimum: 8%.
- Density percentile: 35.0%; density ratio: 0.746.
- Local/kernel ESS: 9.30.
- Nearest dose distance: 0.00031; extrapolation: 0.
- Hard failures: none.
- Soft warnings, ordered: `local_ess_soft`, `moderate_ess`.
- Bootstrap width: persisted in `support_failure_trace.parquet`.
- Estimated profit advantage: 0.806; interval overlaps the optimum alternatives.
- Final result: `EXPERIMENT`.
- Withholding layer: `SUPPORT`; two soft ESS warnings prevent direct ACT.

### Seed 3 — hidden confounding

- Estimated optimum: 0%; constrained optimum: 0%.
- Density percentile: 35.4%; density ratio: 0.726.
- Local/kernel ESS: 45.52.
- Nearest dose distance: 0; extrapolation: 0.
- Hard failures: none.
- Soft warning: `moderate_ess`.
- Estimated profit advantage: 0.
- Final result: `ABSTAIN`.
- Withholding layer: `EVIDENCE`—profit intervals overlap, hidden-confounding sensitivity
  is active, and no economic advantage over baseline exists.

Neither good-world rejection was caused by raw density or geometric extrapolation.

## Support ablations

These are support-only ablations. ACT means the selected optimum was classified
SUPPORTED; EXPERIMENT means LIMITED; ABSTAIN means no safe candidate/projection. Oracle
support is used only for post-hoc scoring.

| Ablation | Good A/E/B | Weak A/E/B | Bad A/E/B | Unsupported ACT |
|---|---:|---:|---:|---:|
| Density only | 100/0/0% | 100/0/0% | 100/0/0% | 0 |
| Local ESS only | 0/100/0% | 0/100/0% | 50/50/0% | 0 |
| Geometry only | 100/0/0% | 100/0/0% | 100/0/0% | 0 |
| Extrapolation only | 100/0/0% | 100/0/0% | 100/0/0% | 0 |
| Density + ESS | 0/100/0% | 0/100/0% | 50/50/0% | 0 |
| Density + geometry | 100/0/0% | 100/0/0% | 100/0/0% | 0 |
| Full gate | 0/100/0% | 0/100/0% | 50/50/0% | 0 |

Where ACT occurred in an ablation, oracle-supported ACT precision was 100%. The full
gate's supported-ACT recall was 0% in good/weak and 50% in bad. This isolates the main
support downgrade to ESS, not density, distance, or extrapolation. Bad-world support-only
ACTs selected the observed 0% optimum; the full decision layer correctly withheld them
because support alone does not establish an economic treatment advantage.

## Before versus after

| Metric | v4 before | v5 after |
|---|---:|---:|
| ACT / EXPERIMENT / ABSTAIN | 0 / 2 / 4 | 1 / 2 / 3 |
| Good withholding | 100% | 100% |
| Weak withholding | 100% | 50% |
| Bad withholding | 100% | 100% |
| Unsupported ACT | 0 | 0 |
| Coarse false withholding | 100% | 83.3% |
| Measured DR RMSE | 2.314 | 2.314 |
| Measured supported/limited 90% coverage | 94.4% | 100% |
| Mean measured economic regret | 1.979 | 1.979 |
| Runtime | 102.85 s | 175.44 s |

Coverage changed because the support classification changed; the bootstrap estimator did
not. The single ACT was measured weak-support seed 1 at 6%. Its post-hoc oracle economic
regret was 0.683. It had no hard support failures, one soft `moderate_ess` warning, a
10.1th density percentile, 50.55 local ESS, and a 2.779 estimated profit advantage.

## Persisted artifacts

Directory: `artifacts/benchmarks/continuous-retail/quick-support-gate-v5-final/`

- `support_failure_trace.parquet`
- `support_ablation_results.parquet`
- `support_ablation_summary.parquet`
- `support_diagnostics.parquet`
- `treatment_density_diagnostics.parquet`
- `decision_outcomes.parquet`
- `dose_response_curves.parquet`
- estimator, calibration, falsification, configuration, registry, JSON, and Markdown
  artifacts from the existing benchmark contract

## Verification

- `pytest -q`: 64 passed
- `ruff check .`: passed
- `mypy`: passed for 70 source files

## Final answer

The previous gate withheld everything because moderate ESS was treated too much like a
veto, and because economic/evidence withholding was incorrectly summarized as support
failure. v5 fixes the geometry bug, normalizes density, separates hard and soft rules,
separates support from evidence, supports safe near-boundary projection, and produces a
complete failure trace and ablation suite.

We gained one useful, oracle-supported ACT and reduced weak-support withholding without
introducing unsupported ACTs. However, no good-support world became ACT: measured good
remains an appropriate experiment because its advantage is small and ESS has two soft
warnings; hidden good appropriately abstains. Therefore the quick gate criterion is not
fully met, operational abstention remains **FAIL**, and the definitive benchmark must not
run yet.
