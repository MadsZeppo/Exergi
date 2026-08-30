# Exergi V13 JTPA preregistration

Status: `FROZEN_BEFORE_OUTCOME_ACCESS`

Qualification commit: `47f46a3594493dd8febc614d011d9bda0564d64c`

## Question and estimand

Can a policy using only lawful pretreatment BIF fields increase 30-month earnings on unseen randomized
people relative to both BAU/control and the best legal static policy?

The treatment is the randomized offer of JTPA Title II eligibility, not enrollment or service receipt. The
primary estimand is the intention-to-treat expected policy value per randomized person:

`V(pi) = E[Y(pi(X))]`

Primary contrasts are `V(pi)-V(BAU)` and `V(pi)-V(best static)`. Assignment propensity is known and
fixed at 2/3 for offer and 1/3 for control.

## Population, outcome and split

- Population: 15,134 people in both the official 30-month analysis membership and 12-site `SCALEDUI`.
- Outcome: `sum(UIERN01,...,UIERN30)`, nominal USD, months 1-30 after assignment.
- Split: deterministic participant-level SHA-256 split, 60% DEVELOPMENT / 40% VALIDATION, salt
  `EXERGI_V13_JTPA_60_40_V1`.
- No sealed-test split. Validation is one-shot and remains closed unless DEVELOPMENT earns reveal.
- Adult men, adult women, female youths and male youths are reported separately but are not selected
  based on outcome results.

The outcome is official edited/imputed UI earnings scaled to survey levels. It is not contribution profit.
Any missing monthly outcome in the frozen population is a hard implementation stop.

## Policy features

Only the 33 `POLICY_ALLOWED` BIF fields in `V13_VARIABLE_TIMING_DICTIONARY.csv` may enter models.
They cover site, staff-recommended pretreatment service strategy, transport, education and work history.
All are encoded inside each training fold using rare-category-aware one-hot encoding; preprocessing is
never fit on validation.

The following are categorically forbidden: age, sex, race/ethnicity and derived protected groups; names,
SSN, date of birth and contact data; assignment indicators; follow-up response/sample indicators; actual
enrollment, participation, service receipt, completion and placement; all outcome fields.

Protected groups may be used only after policy predictions are frozen for fairness/support reporting.

## Frozen comparators

1. BAU/treat none.
2. Treat all.
3. Best legal static action: DEVELOPMENT-selected better of treat none and treat all.
4. Simple legal segment policy: independent action by the three pretreatment staff-recommended service
   strategies (`TRTMNT`), with unsupported segments mapped to BAU.

No comparator may be redefined after DEVELOPMENT.

## Frozen model tournament

All nuisance and individual-effect predictions are out-of-fold, using five participant-level folds
stratified by site and assignment. Primary seed is 1301; stability seeds are 1301, 1302 and 1303.

- simple segment policy;
- regularized linear T-learner;
- LightGBM T-learner;
- LightGBM X-learner;
- R-learner with cross-fitted outcome nuisance and known propensity;
- doubly robust learner with cross-fitted arm nuisances and known propensity;
- honest causal forest only if an existing dependency is available (none is installed at preregistration);
- depth-2 policy tree fit to out-of-fold DR scores;
- direct policy learner fit to signed, absolute-weighted DR scores;
- cost-sensitive DR policy using the frozen sensitivity costs.

No LLM decision, published JTPA subgroup result or validation outcome may enter selection.

## Policy construction and abstention

Each model outputs an out-of-fold conditional ITT estimate. At primary cost zero, `ACT` requires positive
conservative incremental earnings and in-support preprocessing categories; otherwise the row is `BAU` or
`NOT_ENOUGH_EVIDENCE`. The binary evaluator maps `NOT_ENOUGH_EVIDENCE` to BAU.

For development comparison, policy thresholds are selected only from the fixed grid of treatment-rate
quantiles `[0.05, 0.10, ..., 0.95]` using nested/out-of-fold policy value. No validation threshold tuning.

## Value estimators and uncertainty

Primary policy value estimator: known-propensity Hájek/IPW. Confirmation estimators: cross-fitted DR
policy value and cross-fitted AIPW contrasts. Confidence intervals use a deterministic 1,000-replicate
participant bootstrap for the final DEVELOPMENT candidate; fast model screening may use analytic
influence-function standard errors. Site-cluster and leave-one-site-out results are reported separately.

Report value/person, value versus BAU and best static, total value, treatment rate, standard error, 95%
CI, p-value, IPW ESS, fold/site stability and the four reporting groups.

## Cost sensitivity

There is no reproducible assignment-cost field. Primary evaluation is gross earnings with cost 0.
Sensitivity subtracts these frozen nominal-USD costs per offer:

`[0, 100, 250, 500, 750, 1000, 1500, 2000, 3000]`

Break-even cost is reported. Costs never change the primary earnings claim or qualification authority.

## Materiality and DEVELOPMENT promotion gate

After DEVELOPMENT opens, materiality is numerically frozen as
`max(0.01 * DEVELOPMENT control mean, $100)` before model selection. A personalized candidate earns
validation reveal only if all conditions hold:

- point estimate beats DEVELOPMENT best static;
- 95% conservative lower bound versus best static is positive;
- point estimate versus best static exceeds materiality;
- treatment rate is between 5% and 95%;
- at least two valid value estimators agree on a positive contrast;
- IPW ESS is at least 400 in each observed action arm;
- at least four of five folds have positive value versus best static;
- at least eight of twelve sites are nonnegative and no site is below minus twice materiality;
- all timing, leakage, overlap, placebo and immutable-history tests pass;
- at practically equal value, the less complex policy wins.

If no candidate passes, stop with `V13_DEVELOPMENT_NO_PERSONALIZED_POLICY_EARNED_REVEAL` and do not
open validation.

## Robustness frozen before outcomes

- leave-one-site-out and leave-one-reporting-group-out;
- drop top 1% of outcomes and nonzero winsorization at 99%;
- missing-outcome hard assertion plus worst-case bounds if later needed;
- alternative valid IPW/DR/AIPW estimators;
- 20 treatment-label shuffles and 20 outcome shuffles;
- seeds 1301-1303 and fold sensitivity;
- feature-timing and forbidden-feature assertions;
- policy complexity penalty and support checks.

Robustness cannot redefine the primary estimand or tune a failed gate.

## One-shot validation rule

Only a committed freeze and an outcome-free dry-run may authorize the separate validation runner. The
runner must write reveal-start before access and a permanent consumed lock after access. A second reveal
must fail before outcome access. No fallback policy, group, threshold, feature, cost or estimand is allowed.

Possible final classifications are `PERSONALIZED_VALUE_PASS`, `STATIC_VALUE_PASS`,
`RESPONSIBLE_BAU_PASS`, `INCONCLUSIVE` or `DATASET_NOT_QUALIFIED`. With the current cost authority,
the strongest possible positive claim is `REAL_RANDOMIZED_PERSONALIZED_EARNINGS_POLICY_VALUE`.
