# Commercial Twin refactor — implementation report

Date: 2026-08-25

## 1. Outcome

The repository now exposes a typed `CommercialTwin` product layer over the existing scientific
decision engine. The continuous-discount implementation reuses the established chronological
cross-fitted doubly robust estimator, conditional treatment-density model, support gate, and
contribution-profit calculation. No mathematical subsystem was moved or replaced.

The implemented end-to-end path is:

`canonical history → TwinFactory → CommercialState snapshot → DiscountAction → behavior model →`
`SimulationResult → ACT / EXPERIMENT / ABSTAIN → observed outcome → calibration record`

## 2. What was inspected

Before structural changes, the repository tree and the following areas were inspected:

- continuous-treatment outcome and density nuisance models;
- chronological cross-fitting and DR dose-response correction;
- synthetic retail DGP and its evaluation-only oracle arrays;
- conditional support diagnostics and explicit thresholds;
- decision/evidence gating and contribution-profit economics;
- counterfactual bootstrap uncertainty and benchmark runners;
- legacy schemas, Prediction Ledger, and ModelPerformanceRegistry;
- tests, packaging/type-check configuration, dashboard, and README.

The pre-change classification is recorded in
[`commercial_twin_refactor_audit.md`](commercial_twin_refactor_audit.md).

## 3. Audit decisions

- **KEEP:** causal, forecast, uncertainty, support, economics, simulation, benchmark, metric,
  robustness, dataset, and synthetic-world mathematics.
- **KEEP AND EXTEND:** Prediction Ledger and ModelPerformanceRegistry.
- **ADD:** generic decision contracts, commercial state contracts, orchestration, commerce adapter,
  deterministic cohorts, readiness, and synthetic product fixture.
- **RENAME IN PRESENTATION:** research cockpit title to Commercial Twin Research Cockpit.
- **DEPRECATE LATER:** product-specific entry points only after equivalent generic callers exist.
- **DELETE:** nothing. There was no scientifically justified deletion in this pass.

## 4. Architecture after the refactor

Three explicit package boundaries now exist:

1. `decision_engine` — domain-neutral scientific and mathematical core.
2. `commercial_twin` — commercial state, behavior protocol, orchestration, readiness, calibration,
   cohorts, and factory.
3. `domains.commerce` — commerce actions and the first wired behavior model: continuous discount.

This is an additive migration. Existing imports, benchmarks, schemas, tables, and runners remain
available.

## 5. Exact files created

- `src/decision_engine/core/__init__.py`
- `src/decision_engine/core/contracts.py`
- `src/commercial_twin/__init__.py`
- `src/commercial_twin/behavior.py`
- `src/commercial_twin/cohorts.py`
- `src/commercial_twin/factory.py`
- `src/commercial_twin/readiness.py`
- `src/commercial_twin/schemas.py`
- `src/commercial_twin/twin.py`
- `src/commercial_twin/py.typed`
- `src/domains/__init__.py`
- `src/domains/py.typed`
- `src/domains/commerce/__init__.py`
- `src/domains/commerce/actions.py`
- `src/domains/commerce/behavior.py`
- `src/domains/commerce/fixtures.py`
- `tests/test_commercial_twin.py`
- `docs/commercial_twin_refactor_audit.md`
- `docs/commercial_twin_refactor_report.md`

## 6. Exact files modified

- `src/decision_engine/ledger/store.py`
- `src/decision_engine/registry/store.py`
- `apps/research_dashboard.py`
- `pyproject.toml`
- `README.md` (rewritten)

No existing scientific module was deleted, renamed, or physically moved.

## 7. Generic decision contracts

The new frozen Pydantic contracts are:

- `DecisionState`
- `CandidateAction`
- `OutcomeDefinition`
- `UtilityDefinition`
- `ConstraintDefinition`
- `DecisionHorizon`
- `DecisionContext`
- `DecisionProblem`
- `OutcomeDistribution`
- `SimulationResult`
- `DecisionDisposition`

They make state, candidates, outcomes, utility, constraints, horizon, evidence, support,
uncertainty, assumptions, and model versions explicit without embedding commerce logic in the core.
Distribution quantiles are validated as non-crossing.

## 8. Commercial state model

Frozen schemas now represent:

- `CustomerState`: cohort-level RFM, affinities, response, retention, acquisition, geography, age;
- `ProductState`: product/category, current price, unit cost, inventory;
- `CompanyState`: products, promotions, marketing, channels, fulfillment, campaigns, offers;
- `WorldSignal` and `WorldState`: value, observation time, source, geography, confidence, provenance;
- `CommercialState`: customer + company + world state at one explicit `as_of` time;
- `CommercialTwinSnapshot`, `TwinCalibrationRecord`, and readiness reports.

Timestamps are timezone-aware. Action and horizon end times cannot precede their start times.

## 9. Temporal and causal roles

`TemporalCausalMetadata` records observation, decision, and effective times, source, and one of:

- `PRE_TREATMENT`
- `ACTION`
- `MEDIATOR`
- `OUTCOME`
- `UNKNOWN`

The existing DR feature validation remains active and rejects declared post-treatment controls.

## 10. BehaviorModel protocol

The protocol separates the product shell from estimators. A behavior model provides:

- `fit(history)`
- `predict_outcomes(state, action)`
- `diagnostics()`
- `calibration_report()`

`BehaviorPrediction` carries distributions, disposition, evidence, support, uncertainty,
assumptions, model versions, and an optional experiment suggestion.

## 11. Implemented discount behavior

`ContinuousDiscountBehaviorModel` wraps the existing
`ContinuousDRDoseResponseEstimator`. It does not duplicate its mathematics. It:

1. validates that oracle fields are absent;
2. fits outcome and treatment-density nuisances with chronological cross-fitting;
3. evaluates a candidate discount with the existing conditional support gate;
4. predicts demand for the scoped decision rows;
5. applies transparent observed world-state modifiers;
6. converts demand to contribution profit using price and unit cost;
7. emits typed distributions and a support-consistent disposition.

An `UNSUPPORTED` support result always maps to `ABSTAIN`; `LIMITED` maps to `EXPERIMENT`; only
`SUPPORTED` can map to `ACT` in this adapter.

## 12. Causal estimator preserved

The estimator remains the localized continuous-treatment DR/orthogonal construction already in the
repository. In compact form, the response at dose `d` is the plug-in outcome regression plus a
kernel-localized, inverse-density-weighted cross-fitted residual correction:

`mu_hat(d) = mean_x m_hat(d,x) + weighted_mean[K_h(D-d) * (Y-m_hat(D,X)) / f_hat(D|X)]`

The implementation retains chronological expanding folds, density flooring, effective sample-size
diagnostics, clipping reports, and explicit identification assumptions. Oracle truth is not used.

## 13. Treatment support and refusal

The existing `ConditionalSupportGate` remains authoritative. It evaluates conditional density,
local ESS, nearest dose geometry, kernel support, population-relative density, conditional dose
quantiles, extrapolation, spacing, and explicit hard/soft rules.

The Commercial Twin serializes the full typed support report into every simulation result. It does
not infer support from global dose occurrence alone.

## 14. Uncertainty

The commercial adapter currently constructs demand and contribution-profit intervals from
cross-fitted residual scale, with wider uncertainty under LIMITED and UNSUPPORTED support. Metadata
labels this honestly as `cross_fitted_residual_normal_approximation` and states that prospective
calibration is required.

The scientifically heavier blocked/clustered bootstrap and oracle calibration remain in the
benchmark layer. They were preserved rather than silently replaced by this faster product adapter.

## 15. Economics

The causal model produces demand. `contribution_profit(...)` remains a separate economic
transformation using discounted selling price, unit cost, and predicted quantity. The behavior model
does not train directly against an “optimal discount” label.

## 16. Commercial actions

Implemented and wired:

- `DiscountAction`, constrained to `[0, 0.30]`.

Typed interfaces only, deliberately not wired to unsupported behavior models:

- `PriceChangeAction`
- `FreeShippingAction`
- `PromotionAction`

Calls for an unimplemented action type fail explicitly.

## 17. Cohorts

`build_behavior_cohorts` deterministically aggregates canonical history by category. It produces
stable non-PII cohort states containing entity count, frequency, monetary value, average order
value, category affinity, purchase frequency, and observed promotion exposure.

This is a transparent V1 cohort layer, not synthetic individuals or agent simulation.

## 18. TwinFactory

`TwinFactory` validates required canonical columns, discount range, nonempty input, and oracle-field
isolation. It builds products, cohorts, state, discount behavior model, and decomposed readiness.

It exposes:

- `build_twin(...)`
- `validate_twin(...)`
- `update_twin(...)`

## 19. World-state behavior

The fixture uses observed `consumer_confidence`, `seasonal_demand_index`, and optional
`category_demand_index` signals in a bounded, documented multiplier. Tests verify that outcomes
change when world state changes while customer and company state remain identical.

This is intentionally minimal. It is not a learned world model, causal discovery system, or agent
society.

## 20. Synthetic truth isolation

`SyntheticCommercialTwinFixture` keeps three separate objects:

- `twin`
- `canonical_history`
- `oracle`

The twin receives only the canonical frame. Synthetic `baseline_demand`, `beta`, `gamma`, and
`hidden_u` arrays stay on the evaluator-side oracle object. Factory and behavior-model validation
also reject named oracle fields if a caller attempts to add them to input data.

## 21. Readiness

Readiness is capability-specific and decomposed across:

- data volume;
- history length;
- outcome completeness;
- cost quality;
- calibration history;
- world-context coverage;
- action variation;
- treatment support;
- causal identifiability.

Discount can be READY, LIMITED, or NOT_READY from observed evidence. Price change and product launch
are explicitly NOT_READY because no causal behavior model is implemented. No scalar “twin score” is
manufactured.

## 22. Ledger and registry compatibility

Existing `predictions`, `evaluations`, and `model_performance` tables and methods are unchanged.

Additive tables now record:

- immutable simulation snapshots and distributions;
- support, evidence, uncertainty, assumptions, disposition, and model versions;
- later actual outcomes and prediction errors;
- action type, support regime, calibration metadata, error metrics, and optional regret.

`CommercialTwin.update` closes the initial learning loop by producing a `TwinCalibrationRecord` and
writing compatible evaluation/performance rows when stores are configured.

## 23. Dashboard and README

The Streamlit title is now **Commercial Twin Research Cockpit**. A small top section exposes
Customer State, Company State, World State, and Twin Readiness concepts. Existing research tabs were
not redesigned. The prominent `SYNTHETIC — NOT COMMERCIAL EVIDENCE` warning remains.

The README now explains architecture, invariants, state, quick start, example use, persistence,
scope, and scientific limitations.

## 24. Automated tests added

The Commercial Twin suite covers:

- timezone enforcement and action horizon order;
- typed action bounds;
- state/factory construction;
- deterministic cohort ordering;
- oracle isolation and rejection;
- typed distributions and ordered quantiles;
- simulation comparison order;
- world-state-dependent outcomes;
- decomposed readiness;
- unsupported-action refusal invariant;
- simulation ledger persistence;
- outcome calibration updates and registry persistence.

Existing chronological cross-fitting, support, uncertainty, causal, economic, and benchmark tests
remain in the full suite.

## 25. Verification and runtime

Final local verification:

- `pytest -q`: **75 passed**, 5.6 seconds.
- `ruff check .`: **passed**.
- `mypy`: **passed**, 84 source files checked.

One environment-only Joblib warning reported that macOS physical-core detection returned an empty
string; Joblib safely used logical core count. There were no test failures or scientific warnings
suppressed.

## 26. Capability verdict and what remains unproven

| Capability | Verdict | Reason |
|---|---|---|
| Generic decision contracts | PASS | Typed, immutable, validated, tested |
| Commercial state snapshots | PASS | Customer/company/world state implemented and tested |
| Continuous discount simulation | PASS for synthetic integration | Existing DR and support core wired end to end |
| Unsupported-action refusal | PASS | Unsupported support cannot produce ACT |
| World-state variation | PASS for deterministic fixture | Same internal state changes outcome under changed world signals |
| Cohorts | PASS for transparent V1 | Deterministic non-PII category cohorts |
| Ledger/calibration loop | PASS for local persistence | Snapshot and outcome error are append-only |
| Prospective interval calibration | NOT PROVEN | Requires real sequential decisions and outcomes |
| Hidden-confounding robustness | NOT PROVEN | No observational method can establish absence of hidden confounding |
| Real commercial causal validity | NOT PROVEN | Requires canonical retail data, overlap, falsification, and experiments |
| Price/free-shipping/promotion behavior | NOT READY | Contracts only; no causal model wired |
| Production readiness | NOT CLAIMED | Operational, data-contract, monitoring, and prospective evidence remain |

The refactor earns a coherent product abstraction without broadening into integrations, autonomous
execution, LLM agents, a world model, supply-chain optimization, or a new simulator. The next
scientifically justified step is to validate the canonical data contract on real retail histories,
run prospective calibration, and compare supported recommendations with randomized interventions.
