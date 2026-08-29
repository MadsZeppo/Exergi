# V7.3 Stability-Assurance Preregistration

Fixed before any V7.3 synthetic outcome is generated or analyzed. Source reference:
`3ec80610c1cb990a9440b67ec60b2ab7ad75cc57`; immutable V7.2 forensic checkpoint:
`3ec8061`. Hillstrom is marked `DEVELOPMENT_CONSUMED`. Its VALIDATION is closed, its SEALED_TEST is
not authority, and quarantined `row-0` remains in its original split.

## Scientific question

Does the V7.2 five-fold veto reliably prevent false economic actions, or does it impose an
unacceptably high false-negative rate on genuine positive mean-value actions under ordinary sparse,
heavy-tailed commerce outcomes? Gate choice is based only on independent synthetic gate-development
worlds. Synthetic truth is evaluator-only and structurally absent from deployable gate inputs.

## Disjoint synthetic levels

Three levels use separate deterministic seed roots and 500 independent worlds per family:

| Level | Seed root | Worlds per family | Gate authority |
|---|---:|---:|---|
| Gate development | 7,303,001 | 500 | candidate comparison and mechanical selection |
| Gate validation | 7,303,002 | 500 | one run of frozen selected gate |
| Sealed gate test | 7,303,003 | 500 | opened only after every validation gate passes |

Families are null, globally harmful, materially positive, weak positive, qualitative heterogeneity,
sparse responders, outlier-driven effects, negative contribution margin, effect reversal/common
shock, and integrity/support failure. Sample size is independently drawn from 600, 1,200, and 2,400;
baseline purchase probability from 0.5%–5%; assignment from 35%–65% when supported. Positive
amounts use preregistered lognormal, Pareto, or compound/Tweedie-like shapes. Missingness, maturity,
attrition, corrupted propensity, insufficient overlap, costs, budgets, outliers, and reversals are
generated without access to a candidate gate.

## Common fail-closed prerequisites

Every gate must ABSTAIN unless all are true: known valid propensity; both arm ESS >= 100; propensity
in `[0.10, 0.90]`; assignment integrity; no differential attrition above 5 percentage points; at
least 95% mature outcomes; declared action cost within the per-unit budget; no unsupported action;
no post-treatment feature; and disjoint unique unit IDs. These checks are identical across gates.

## Fixed candidate gates

1. `existing_v72_fold_veto`: global adjusted lower 95% bound > 0; at least 4/5 positive arm-balanced
   folds; every leave-one-fold-out estimate > 0; minimum fold net >= -$0.05.
2. `repeated_stratified`: global lower 95% bound > 0 and at least 80% positive effects across 10
   repetitions × 5 pretreatment-stratified folds.
3. `repeated_arm_balanced`: global lower 95% bound > 0 and at least 80% positive effects across 10
   repetitions × 5 arm-balanced folds.
4. `median_of_means`: 10 arm-balanced blocks; median-effect lower bound using `1.4826 × MAD` > 0.
5. `influence_bounded`: 99.5% pooled upper cap fixed ex ante; capped HC3 lower bound > 0 and largest
   absolute raw influence share <= 35%.
6. `bootstrap_positive_probability`: 200 deterministic within-arm bootstrap replicates; probability
   of positive net value >= 97.5% and percentile lower 95% bound > 0.
7. `simultaneous_lcb`: Bonferroni 97.5% one-sided lower bounds for raw, CUPED, and stratified mean
   estimators are all > 0.
8. `cross_fitted_aipw_lcb`: five-fold cross-fitted linear outcome nuisance, known propensity, HC
   lower 95% bound > 0.
9. `bayesian_positive_probability`: normal-reference posterior probability > 99%; diagnostic only
   and ineligible for final selection.
10. `distributionally_robust`: minimum lower 95% bound across raw, 99.9%-capped, and 99.5%-capped
    mean effects > 0.
11. `combined_economic`: cross-fitted AIPW lower 95% bound > 0; bootstrap probability >= 97.5%; at
    least 75% positive repeated arm-balanced effects; largest influence share <= 35%; all common
    support/economic prerequisites pass.

All confidence bounds concern mean net value. Huber/median location estimates cannot substitute for
the mean estimand. No benchmark-family or oracle branch is permitted inside gate code.

## Development selection rule

A selectable gate must have unsupported ACT = 0, harmful ACT <= 1%, null ACT <= 5%, positive average
policy value, p95 loss = 0, p99 loss <= $0.10/customer, CVaR99 loss <= $0.25/customer, maximum
drawdown <= $1/customer, zero budget/early-release violations, and at least a 10 percentage-point
absolute reduction in false-negative rate versus `existing_v72_fold_veto` on materially positive +
sparse-responder worlds. Seed-decision agreement must be >= 90% and fold-count decision agreement
>= 85%.

Among passing gates, select the lowest harmful ACT rate, then lowest null ACT rate, then lowest ACT
rate, then highest materially-positive power. Bayesian diagnostics are never selectable. If no gate
passes, V7.3 stops before gate validation and Hillstrom reassessment.

## Frozen validation and sealed requirements

The selected definition, thresholds, estimator, costs, seed semantics, source hash, code hash, and
manifests are frozen before gate-validation. Validation must independently satisfy every development
safety bound, retain at least 90% of development materially-positive power, and preserve the
10-point false-negative improvement. Failure closes sealed gate-test. If validation passes, sealed is
opened once and must satisfy the same rules. Any failure stops before Buy Baits/Hillstrom.

## Real-data sequence

Only after synthetic validation and any authorized sealed gate-test pass is the frozen gate applied
to Buy Baits DEVELOPMENT. Any unsupported static/personalized ACT is a safety regression. Only after
that negative control passes may the identical gate reassess Hillstrom DEVELOPMENT. No real-data
threshold, fold, feature, cost, estimator, or policy change is allowed.

Hillstrom authority is capped at `REAL_RANDOMIZED_NET_REVENUE_SCENARIO`; it cannot establish
contribution profit. BAU is always valid. Hillstrom VALIDATION is never opened in this run.
