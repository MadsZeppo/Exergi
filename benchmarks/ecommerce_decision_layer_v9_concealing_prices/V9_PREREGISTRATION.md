# Exergi V9 preregistration

Status: `LOCKED_BEFORE_DEVELOPMENT_OUTCOME_ACCESS`

## Scope and claims

V9 tests a static price-disclosure decision in two contexts from one retailer and one
replication package. It does not test personalization, contribution profit, production
readiness, or general merchant performance. The primary monetary authority is randomized
sales revenue in Argentine pesos (ARS). No action cost is observed, so the result is gross
incremental revenue plus a break-even differential action cost—not net profit.

Published treatment estimates were read only to audit the study documentation. They are not
inputs to the split, estimator, materiality threshold, selection rule, or validation gate. The
rules below are symmetric in effect direction.

## Frozen splits

- Study 1: `date_id` is the split and inferential unit because released data are day×arm
  aggregates. Sort the 56 date IDs once; first 28 are DEVELOPMENT and last 28 are VALIDATION.
  Both arms must exist for every date. No SEALED_TEST is created because 14 dates per held-out
  partition would be scientifically too sparse.
- Study 3: unique randomized recipient `user_id` is hashed with the fixed V9 seed and assigned
  deterministically to 50% DEVELOPMENT, 25% VALIDATION, and 25% SEALED_TEST. Only hashed
  manifest digests are persisted; raw IDs remain in ignored raw data.

No outcome is involved in either split.

## Primary estimands

Study 1 uses the unweighted mean across date blocks of:

`delayed revenue / delayed assigned visitors - immediate revenue / immediate assigned visitors`.

Its interval is a two-sided paired Student-t 95% interval across dates. Randomization occurred
at visitor/cookie level, but visitor IDs are unavailable; individual-level uncertainty and
customer policy learning are prohibited.

Study 3 uses the design-based difference in raw weekly ARS revenue means per randomized
recipient: delayed minus immediate. Its primary interval is the two-sided Neyman 95% interval.
The estimand is ITT by assignment; opens/clicks/purchases are never eligibility or policy
features.

## Static selection rule on DEVELOPMENT

For each study, support and integrity must pass. If delayed-minus-immediate is positive and its
95% upper bound is above zero, freeze `TEST_DELAYED_PRICE`. A positive point estimate is allowed
to enter one-shot confirmation as TEST; it is never labeled ACT on development alone. If the
point estimate is negative, freeze the immediate reference as `AVOID_DELAYED_PRICE`. If the
estimate is zero, non-finite, or integrity fails, choose `NOT_ENOUGH_EVIDENCE` or stop INVALID.

Minimum directional materiality is strictly greater than 0 ARS per randomized analysis unit.
This is not a merchant-specific commercial materiality threshold. Economic importance is
reported in the observed ARS scale and through break-even differential action cost.

Required baselines are immediate/reference for both contexts, delayed/action-all for both,
development-best static, and a simple context-blind rule that keeps immediate disclosure.

## Validation gate

- Frozen TEST delayed: `CONFIRMED_ACTION` only when delayed-minus-immediate is positive and its
  two-sided 95% lower bound is strictly above zero.
- Frozen AVOID delayed: `CONFIRMED_AVOID` only when immediate-minus-delayed is positive and its
  two-sided 95% lower bound is strictly above zero.
- Frozen NOT ENOUGH EVIDENCE can only yield `RESPONSIBLE_ABSTENTION` when validation does not
  strongly support a material action.
- Otherwise the result is `INCONCLUSIVE` or `CONTRADICTED`.

SEALED_TEST is never a fallback.

## Frozen robustness analyses

Secondary-only checks are raw units, purchase probability, log1p revenue, purchaser-rate and
revenue-per-purchaser decomposition, 0.1% leave-top sensitivity, missingness, SRM, treatment
balance, paired-date stability for Study 1, and arm-stratified bootstrap. Randomization
inference is used when the documented assignment can be represented without adding outcome
assumptions. No secondary result may change the primary verdict.

No winsorized estimand replaces the raw-mean primary estimand.
