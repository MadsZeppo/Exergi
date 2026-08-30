# Exergi V13 DEVELOPMENT report

Status: `V13_DEVELOPMENT_NO_PERSONALIZED_POLICY_EARNED_REVEAL`

## Decision

No personalized JTPA offer policy earned a one-shot VALIDATION reveal. DEVELOPMENT selected
`BAU_TREAT_NONE` as the best legal static policy. The numerically highest challenger was
`lgbm_t_learner`, but it failed the frozen uncertainty, fold, site and placebo gates. No model freeze was
created, and VALIDATION remains closed.

## Randomized DEVELOPMENT sample

- Randomized people: 9,025
- Control mean, 30-month earnings: $14,561.96
- Offer mean, 30-month earnings: $14,264.12
- Raw offer-minus-control ITT: $-297.84
- Frozen materiality threshold: $145.62
- Outcome authority: nominal USD earnings over months 1–30, not contribution profit

Treat-all did not beat BAU: the Hájek estimate was
$-297.84 with 95% CI
[$-1,008.57,
$412.89].

## Frozen tournament

| Candidate | Hájek vs static | DR vs static | DR 95% CI | Offer rate | gates passed |
|---|---:|---:|---:|---:|---:|
| `lgbm_t_learner` | $271.22 | $269.19 | [$-175.37, $713.75] | 39.0% | 6/10 |
| `linear_t_learner` | $251.11 | $236.79 | [$-237.09, $710.68] | 43.8% | 6/10 |
| `dr_learner` | $216.64 | $218.50 | [$-211.50, $648.51] | 36.9% | 6/10 |
| `r_learner` | $176.48 | $175.06 | [$-256.26, $606.37] | 37.0% | 7/10 |
| `x_learner` | $190.14 | $173.49 | [$-262.62, $609.60] | 38.2% | 6/10 |
| `policy_tree_depth_2` | $173.83 | $170.94 | [$-283.18, $625.07] | 43.3% | 7/10 |
| `cost_sensitive_dr_500` | $-44.58 | $-49.91 | [$-533.33, $433.51] | 45.5% | 3/10 |
| `direct_dr_policy` | $-168.20 | $-181.25 | [$-681.28, $318.79] | 48.5% | 3/10 |
| `simple_service_strategy_segment` | $-310.45 | $-318.76 | [$-722.64, $85.12] | 30.4% | 3/10 |

The best challenger estimated $269.19 per randomized person by DR and
$271.22 by Hájek/IPW. The corresponding DR 95% CI was
[$-175.37, $713.75], and the deterministic 1,000-replicate bootstrap
CI was [$-181.20, $716.11]. The policy offered treatment
to 39.0% of people. These estimates are exploratory DEVELOPMENT diagnostics,
not validated policy value.

## Promotion-gate outcome

- Positive folds: 3/5; required: at least 4/5
- Nonnegative sites: 6/12; required: at least 8/12 and no site below the harm floor
- Effective sample size, offer action: 2335
- Effective sample size, control action: 1830
- Failed gates: `conservative_lower_bound_positive`, `fold_stability`, `placebo`, `site_stability`
- Treatment-shuffle p-value: 0.238095
- Outcome-shuffle p-value: 0.190476

The positive point estimate is therefore insufficient evidence. It is not a claim that personalization
works, and it does not authorize opening VALIDATION.
