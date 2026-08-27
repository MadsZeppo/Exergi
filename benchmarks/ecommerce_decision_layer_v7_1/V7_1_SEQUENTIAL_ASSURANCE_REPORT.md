# V7.1 sequential assurance

Overall verdict: **FAIL**.

| Scenario | Max drawdown | p95 | p99 | CVaR95 | Pre-observable loss | Post-observable loss | Stop latency | Risk utilization | Value retained |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| POSITIVE | 1.26 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 50.0% | 96.8% |
| NULL | 21.68 | 15.97 | 18.55 | 15.18 | 11.76 | 1.67 | 15 | 50.0% | 0.0% |
| HARMFUL | 69.53 | 62.45 | 64.52 | 64.00 | 29.38 | 21.72 | 7 | 33.3% | 0.0% |
| INSUFFICIENT_SUPPORT | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0.0% | 0.0% |
| ACTION_COST | 5.76 | 3.24 | 4.28 | 0.00 | 1.44 | 0.00 | 0 | 50.0% | 97.4% |
| SWITCHING_COST | 3.76 | 1.20 | 2.20 | 0.00 | 0.18 | 0.00 | 0 | 50.0% | 96.9% |
| MATURITY_DELAY | 0.23 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 66.7% | 77.7% |
| CONCURRENT_OPEN_BATCHES | 1.26 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 50.0% | 96.8% |
| ABRUPT_REVERSAL | 107.75 | 94.98 | 100.42 | 55.22 | 59.21 | 24.45 | 6 | 50.0% | 90.3% |
| GRADUAL_DECAY | 39.57 | 29.42 | 36.08 | 0.00 | 20.48 | 0.88 | 3 | 50.0% | 94.5% |
| COMMON_SHOCK | 1.26 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 50.0% | 96.8% |
| CAUSAL_SHIFT | 77.13 | 68.55 | 73.84 | 25.80 | 39.81 | 15.33 | 6 | 50.0% | 91.7% |
| MISSING_RETURNS | 1.23 | 0.00 | 0.36 | 0.00 | 0.01 | 0.00 | 0 | 100.0% | 77.5% |
| ATTRITION | 2.26 | 0.00 | 0.70 | 0.00 | 0.02 | 0.00 | 0 | 50.0% | 96.8% |
| NONCOMPLIANCE | 5.41 | 2.85 | 3.93 | 0.00 | 1.04 | 0.00 | 0 | 50.0% | 53.4% |
| PROPENSITY_CORRUPTION | 1.01 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 16.7% | 5.6% |
| ACTION_FATIGUE | 33.52 | 25.66 | 28.93 | 7.30 | 16.61 | 2.66 | 10 | 50.0% | 98.2% |
| REACTIVATION | 70.31 | 62.29 | 66.94 | 9.82 | 49.67 | 0.00 | 9 | 50.0% | 64.1% |
| DRIFT_BEFORE_MATURITY | 75.81 | 70.05 | 73.84 | 55.73 | 50.18 | 9.89 | 2 | 33.3% | 101.1% |
| DRIFT_AFTER_MATURITY | 87.41 | 77.25 | 81.20 | 21.90 | 47.92 | 15.99 | 5 | 50.0% | 92.7% |

## Gates

- merchant_budget_pathwise: PASS
- family_budget_pathwise: PASS
- no_exposure_over_available_risk: PASS
- stop_latency: FAIL
- avoidable_post_loss: FAIL
- unsupported_never_active: PASS

Every non-BAU batch is reserved before assignment. Decisions use only matured noisy batch outcomes, logged maturity and risk availability; scenario truth is evaluator-only.
