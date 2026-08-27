# Exergi V7 Validation Pack K/L/M report

## Verdict: FAIL

K/L/M were opened once with the frozen forest T-learner and unchanged thresholds. Pack N was not
materialized or read.

| Metric | Result | Gate |
|---|---:|---|
| Worlds | 57 | informational |
| Mean held-out policy value | 0.6672 CP/customer | informational |
| Positive-world mean value | 1.0393 CP/customer | positive |
| Positive-world positive lower-bound rate | 100% | PASS (≥60%) |
| Mean positive-world oracle value capture | 98.94% | informational |
| Unsupported ACT | 0 | PASS (=0) |
| Null/harmful ACT rate | 0% | PASS (≤5%) |
| ACT / BAU-or-TEST / AVOID | 36 / 18 / 3 | informational |
| Heterogeneous personalization promotion | 66.67% | PASS (≥50%) |
| Heterogeneous positive increment over best static | 50% | **FAIL** (≥80%) |
| Runtime | 7.37 s | informational |

## By required stress family

- NULL and COMMON_SHOCK: no ACT.
- HOMOGENEOUS_POSITIVE: treat-all selected in all three packs with positive held-out value.
- GLOBALLY_HARMFUL: AVOID in all three packs.
- MISSING_DELAYED_RETURNS: withheld because contribution-profit costs were incomplete.
- ATTRITION: withheld because treatment/control outcome observation differed beyond tolerance.
- PROPENSITY_LOGGING_ERROR and INSUFFICIENT_SUPPORT: withheld; zero unsupported ACT.
- QUALITATIVE_HETEROGENEITY: individualized policies added value.
- SPARSE_HETEROGENEITY: targeting did not consistently add net value over treat-all, so the
  aggregate heterogeneity gate failed.

## Final status

Validation `overall_pass=false`. The legacy forensic oracle-prior defect is also unresolved because
V6 was deliberately left immutable. Therefore Pack N is prohibited by the preregistration.

