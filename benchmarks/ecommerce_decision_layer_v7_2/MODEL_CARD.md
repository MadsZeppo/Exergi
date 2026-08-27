# V7.2 Economic Policy Engine Model Card

## Intended use

Offline evaluation of randomized multi-arm commerce actions with pretreatment features, known
propensities, continuous monetary outcomes and explicit action costs. It may return BAU, TEST, ACT or
AVOID. It is not an autonomous campaign executor.

## Architecture

Per-arm one-stage or hurdle outcome nuisance models; deterministic K-fold cross-fitting; all-arm net
outcome prediction; cost/governance/support/lower-bound policy gate; IPW/Hájek/DR held-out evaluation.

## Safety boundaries

- BAU is always allowed and is the fallback.
- Prohibited actions are masked before optimization.
- Duplicate randomized units, invalid propensities, immature outcomes and non-finite money fields
  fail closed.
- Claim labels are mechanically capped by observed economic components.
- Real sealed access is one-time and requires three datasets plus exact freeze equality.

## Limitations

There is no real-data selected model or calibrated uncertainty result yet. Current tests establish
software/mechanism behavior only. Heavy tails, rare purchases, subgroup support, SRM and full-pipeline
bootstrap calibration remain unvalidated on the required real evidence packages.
