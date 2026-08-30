# Exergi V13 failure decomposition

Status: `V13_DEVELOPMENT_NO_PERSONALIZED_POLICY_EARNED_REVEAL`

## Primary failure

`INSUFFICIENT_STABLE_PERSONALIZED_POLICY_EVIDENCE`

The highest-ranked DEVELOPMENT challenger (`lgbm_t_learner`) had a positive DR point estimate of
$269.19 per randomized person, but its 95% lower bound was
$-175.37. Only 3/5 folds and 6/12 sites were nonnegative.
Both preregistered placebo tests also failed to separate the observed value from their finite shuffle
nulls (treatment p=0.238095; outcome
p=0.190476).

## What failed

1. **Uncertainty:** the conservative lower bound was not above zero.
2. **Fold stability:** the candidate missed the frozen 4/5-positive-fold threshold.
3. **Site stability:** site effects were heterogeneous and breached the frozen rule.
4. **Placebos:** neither shuffle test met the frozen one-sided 0.05 threshold.

## What did not fail

- The source remained qualified for randomized earnings analysis.
- Assignment propensity, timing allowlist, outcome isolation and ESS checks passed.
- The system selected BAU rather than promoting an unsupported personalized policy.
- No VALIDATION or sealed outcome was opened.

## Scientific interpretation

This is a responsible DEVELOPMENT stop. It neither proves that all personalization is valueless nor
supports a positive personalized policy claim. A later version may use a different preregistered design
or independent dataset, but V13 thresholds, results and closed VALIDATION cannot be retuned or reused.
