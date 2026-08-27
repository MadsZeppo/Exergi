# Exergi V7 preregistration

Status: frozen before Development Pack H/I/J execution and before Validation Pack K/L/M
execution. Pack N is not materialized.

## Scientific question

Can an observable-only decision layer find population action viability, use personalization only
when it adds held-out value beyond the best supported static policy, and limit all immature action
exposure by committed economic downside?

## Data separation

- H/I/J: development and model selection only.
- K/L/M: one validation execution after development freeze; no retuning.
- N: one-time final reveal only if every development and validation gate passes and no forensic
  stop condition remains.
- Merchant IDs, root seeds, parameter draws, action-family mappings and noise streams are disjoint.
- Oracle individual effects are returned by a separate evaluation object and are unavailable to
  action viability, model fitting, gating and decision construction.

## Frozen candidates and estimands

- BAU, treat-all, a simple RFM rule, Ridge T-learner and random-forest T-learner.
- Population viability: strict cross-fitted AIPW/ANCOVA for incremental contribution profit.
- Primary policy value: outer held-out randomization-based DR value.
- Personalization must beat the best supported static policy with a positive one-sided lower bound,
  supported ranking evidence, multiplicity adjustment, fold stability, ESS and overlap.
- Costs must be identified. Revenue may not substitute for contribution profit.

## Frozen thresholds

- Family alpha: 0.05.
- Minimum economically relevant population effect: 0.10 CP per eligible customer.
- Propensity floor: 0.05.
- Heterogeneity ESS: 200.
- Unsupported ACT tolerance: exactly zero.
- Null/harmful ACT rate: at most 0.05.
- Positive-world positive held-out lower-bound rate: at least 0.60.
- Heterogeneous-world positive oracle increment over best static: at least 0.80 (evaluation only).
- Heterogeneous-world personalization promotion rate: at least 0.50.

Thresholds encode false-promotion control, a merchant-relevant CP floor, and minimum effective
sample support. They were not selected from Pack A-G or validation outcomes.

## Final stop rule

Pack N remains sealed if any forensic oracle leakage, cost-accounting defect, unsupported ACT,
risk-budget breach, failed validation gate or post-validation code/configuration change remains.
The V6 oracle-derived source-prior defect discovered before V7 implementation therefore blocks a
V7 final reveal in this pass, even if isolated V7 component metrics are favorable.

