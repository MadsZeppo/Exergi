# Exergi V7 method-selection report

## Architecture selected before validation

The implementation separates six questions:

1. `ActionViabilityEngine`: strict cross-fitted AIPW/ANCOVA estimate of average incremental
   contribution profit against BAU.
2. `SegmentPolicyEngine`: honest comparison of a small preregistered segment set.
3. `HeterogeneityGate`: individualized policy only after OOF ranking, multiplicity-adjusted
   shuffle evidence, fold stability, ESS/overlap and positive value over best static.
4. `ValueOfInformationAllocator`: finite-horizon conservative ENBS against the actual current best
   policy, net of direct cost, experiment regret, committed downside and switching cost.
5. `CommittedRiskLedger`: global and family reservations for every immature non-BAU batch.
6. `LifecycleControllerV7`: observable-only, leased state transitions with reason codes and an
   append-only decision ledger.

Claim authority is carried separately. Only `REAL_RANDOMIZED_CONTRIBUTION_PROFIT` can ever support
a real merchant-profit claim.

## Development-only model tournament

| Model | Positive-world mean held-out CP value | Mean all-world value | Unsupported ACT | Selected |
|---|---:|---:|---:|---|
| Ridge T-learner | 1.0116 | 0.6362 | 0 | no |
| Forest T-learner | 1.0218 | 0.6561 | 0 | yes |

The forest winner was frozen in `FROZEN_DEVELOPMENT_CONFIG.json`. Validation outcomes were not
used for selection.

## Honest limitation

The requested comprehensive T/X/R/DR/causal-forest tournament was not completed in the V7 runner.
The repository contains earlier DR and optional EconML components, but only Ridge and forest
T-learners were wired into the new contribution-profit outer-holdout tournament. This is a
scientific completeness failure, not evidence that the forest is globally best.

