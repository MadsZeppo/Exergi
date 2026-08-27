# Layer 3 Validation — Preregistration

**Locked before outcome generation/evaluation:** 2026-08-25  
**Codebase:** Customer Twin Core V1  
**Status:** thresholds and estimators are immutable after the first benchmark run.

## Objective

Test whether the existing action/uplift layer recovers causal effects when assignment is present,
while preserving fail-closed evidence behavior when identification is absent. Synthetic oracle truth
is evaluation-only. It may not enter fitted features, propensity models, outcome models, evidence
labels, or gates.

## Track A — Synthetic ground truth

### Generator

- Evaluation seeds: integers 0–99.
- Customers per seed and scenario: 20,000.
- Features: two continuous baseline covariates and one three-level segment.
- Baseline purchase probability: nonlinear logistic function of pre-treatment covariates.
- True additive uplift by segment: 0.02, 0.05, and 0.08; probabilities are bounded away from 0/1.
- Randomized assignment: Bernoulli(0.5), independent of covariates.
- Confounded assignment: logistic function of baseline covariates and segment; true propensity is
  not exposed to estimators.
- Placebo: identical randomized generator with true uplift exactly zero.
- One row per pseudonymous customer; all randomness seeded.

### Estimators

1. Naive difference in observed outcome means.
2. Five-fold cross-fitted AIPW/DR estimator using only observed pre-treatment features:
   - logistic treatment propensity;
   - separate logistic treated/control outcome nuisances with a fixed nonlinear basis
     (`x1`, `x2`, interaction, squares, and segment indicators);
   - propensity clipping at 0.02 and 0.98, always reported.
3. Segment effects are means of the cross-fitted orthogonal pseudo-outcome within each segment.
4. The ATE is the mean pseudo-outcome. Its 95% interval uses the influence-function standard error.
5. Individual truth is used only after predictions are frozen to calculate segment-assigned CATE
   RMSE and coverage.

### Primary metrics

- Across-seed ATE bias.
- Across-seed ATE RMSE.
- Segment-effect absolute error and segment-assigned CATE RMSE.
- Empirical coverage of nominal 95% ATE intervals.
- Placebo false-positive rate at two-sided 5%.
- Naive versus adjusted absolute bias under confounding.

### Acceptance thresholds

Track A PASS requires all:

1. Randomized adjusted ATE absolute bias `< 0.005`.
2. Randomized adjusted ATE RMSE `< 0.010`.
3. Mean absolute segment-effect error `< 0.010` in randomized data.
4. Nominal 95% randomized interval coverage between `0.88` and `0.99` inclusive.
5. Placebo adjusted absolute mean estimate `< 0.005` and false-positive rate `<= 0.10`.
6. In confounded data, naive absolute bias `>= 0.010`.
7. Adjusted confounded absolute bias `<= 60%` of naive absolute bias.
8. At least 95 valid seeds per scenario; no result-changing retry of failed seeds.

Evidence labels:

- Randomized scenario: `CAUSAL_RCT`.
- Confounded scenario: `CAUSAL_OBSERVATIONAL`, with ignorability/positivity assumptions.
- Placebo: `CAUSAL_RCT` falsification result.

## Track B — Dunnhumby Complete Journey

### Availability rule

Only authorized, locally supplied Complete Journey files may be used. No download URL or license is
assumed. If files are absent or terms cannot be recorded, ingestion must fail loudly and Track B is
`NOT RUN — DATA UNAVAILABLE`, never synthetic or imputed.

Expected concepts/files are transaction data, product, campaign table, campaign description,
coupon, and coupon redemption. Exact discovered filenames and schemas must be hashed and recorded.

### Frozen action and primary outcome

- Action: household assignment/exposure to the single campaign with the largest eligible treated
  household support, selected without post-exposure outcomes.
- Primary outcome: binary indicator that a household makes at least one valid purchase within 30
  days after its campaign exposure/start.
- Secondary diagnostics: 30-day purchase count and gross spend. Spend is revenue, not profit.
- Evidence: `CAUSAL_OBSERVATIONAL`, never `CAUSAL_RCT`, unless source documentation explicitly proves
  random assignment (not assumed here).

### Temporal split

After schema validation but before outcome aggregation:

1. Order campaigns by observed start date.
2. Set `T` to the first campaign start at or after the 70th percentile of unique campaign starts.
3. Development campaigns start before `T`; frozen backtest campaigns start at/after `T` and have a
   complete 30-day outcome window within transaction coverage.
4. All LivingCustomerState features end strictly before each exposure/start.
5. Model/action selection uses development only. Backtest outcomes are loaded after ledger freeze.

### Estimators and diagnostics

- Naive difference in means.
- Cross-fitted AIPW/DR using pre-exposure LivingCustomerState features.
- Propensity distribution, clipping, overlap fraction, treated/control ESS, covariate balance, and
  sensitivity/limitations.
- Uplift calibration by frozen predicted-uplift groups against doubly robust realized group effects.
- A/A negative control: deterministic 50/50 SHA-256 split among exposed households; SRM must pass
  and the two-sided outcome difference p-value must be `>= 0.05`.

### Acceptance and gating

Track B is scientifically evaluable only if:

- provenance contains source/terms, retrieval or placement time, raw schemas, and SHA-256 per file;
- at least 200 effective observations in both treated and comparison arms;
- at least 80% of evaluated rows have estimated propensity in `[0.05, 0.95]`;
- no unresolved SRM or leakage failure;
- frozen effect is ledgered before backtest outcomes are revealed;
- A/A p-value is `>= 0.05`;
- naive and adjusted estimates plus uncertainty are shown side by side.

Failure of ignorability cannot be statistically disproved. If overlap, balance, temporal support, or
provenance fails, customer-facing evidence is downgraded to `INSUFFICIENT`.

No numerical causal-effect threshold is preregistered because the true effect is unobserved. A
non-significant estimate is a valid result. Backtesting assesses calibration/transport over time,
not oracle causal truth.

## Shared integration invariants

- All answers use the existing EvidenceBoundAnswerRenderer.
- All effect estimates are frozen in the existing Prediction Ledger before outcome reveal.
- Realized outcomes append once; frozen fields are immutable.
- Online Retail II scenario/decision queries remain `NOT ENOUGH EVIDENCE`.
- Dunnhumby answers are observational or insufficient; never silently randomized.
- Revenue is not contribution profit. Missing COGS/action cost keeps profit unavailable.
- No acceptance threshold may be changed after results are observed.
