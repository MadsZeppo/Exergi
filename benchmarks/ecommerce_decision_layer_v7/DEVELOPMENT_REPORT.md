# Exergi V7 Development Pack H/I/J report

## Outcome

Development completed across 57 independent customer-level worlds (19 families × 3 packs). The
forest T-learner won the preregistered development-only selection score and was frozen before K/L/M.

| Metric | Result |
|---|---:|
| Worlds | 57 |
| Mean held-out policy value | 0.6561 CP/customer |
| Positive-world mean value | 1.0218 CP/customer |
| Positive-world positive lower-bound rate | 100% |
| Mean positive-world oracle value capture | 98.88% |
| Unsupported ACT | 0 |
| Null/harmful ACT rate | 0% |
| ACT / BAU-or-TEST / AVOID | 36 / 18 / 3 |
| Heterogeneous personalization promotion | 66.67% |
| Positive oracle increment over best static in heterogeneous worlds | 50% |
| Runtime | 7.26 s |

Population treatment was found in every homogeneous-positive pack. Null/common-shock cases fell
back to BAU-or-TEST; globally harmful cases selected AVOID. Missing returns/costs, differential
attrition, corrupted logged propensity and insufficient support all withheld action.

The 50% heterogeneity-increment result is a material development warning. No post-development
threshold or model retuning was performed.

