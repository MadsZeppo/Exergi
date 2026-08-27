# V7.2 Sequential Assurance

Verdict: **PASS**.

The controller uses mature randomized observations only. Pausing does not release immature committed risk.

| Scenario | Mean value | Active rate | Stop latency | Harmful continuation | Value retained |
|---|---:|---:|---:|---:|---:|
| POSITIVE | 143.87 | 88.9% | 0 | 0 | 99.9% |
| NULL | -0.19 | 0.0% | 0 | 0 | 44.5% |
| HARMFUL | -8.96 | 0.0% | 0 | 0 | 0.0% |
| ABRUPT_REVERSAL | 45.91 | 33.3% | 0 | 0 | 82.0% |
| DRIFT_AFTER_MATURITY | 70.98 | 50.0% | 0 | 0 | 88.7% |
| INSUFFICIENT_SUPPORT | 0.00 | 0.0% | 0 | 0 | 100.0% |
| REACTIVATION | 35.97 | 27.8% | 0 | 0 | 64.2% |

## Locked gates

- budget_violations_zero: PASS
- unsupported_act_zero: PASS
- no_early_risk_release: PASS
- stop_latency: PASS
- post_observable_continuation: PASS
- bounded_revalidation_exposure: PASS
- positive_value_retained: PASS
- null_not_active: PASS
- reactivation_correct: PASS
