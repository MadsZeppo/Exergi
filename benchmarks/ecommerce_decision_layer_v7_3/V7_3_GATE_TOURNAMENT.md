# V7.3 Gate-Development Tournament

## Verdict

**FAIL — no candidate satisfied the preregistered safety and power contract.** No gate was selected
or frozen. Gate-validation therefore remained closed.

| Gate | Null ACT | Harmful ACT | Material ACT | FNR | FNR improvement | Development result |
|---|---:|---:|---:|---:|---:|---|
| Existing V7.2 fold veto | 1.7% | 0.3% | 10.0% | 90.0% | baseline | FAIL: no improvement |
| Repeated stratified | 2.8% | 0.5% | 16.6% | 83.4% | 6.5 pp | FAIL: improvement <10 pp |
| Repeated arm-balanced | 2.8% | 0.4% | 16.7% | 83.3% | 6.7 pp | FAIL: improvement <10 pp |
| Median of means | 7.6% | 1.5% | 24.3% | 75.7% | 14.3 pp | FAIL: null and harmful safety |
| Influence bounded | 2.5% | 0.3% | 19.1% | 80.9% | 9.1 pp | FAIL: improvement <10 pp |
| Bootstrap probability | 4.5% | 1.1% | 21.8% | 78.2% | 11.8 pp | FAIL: harmful ACT >1% |
| Simultaneous LCB | 1.1% | 0.1% | 8.6% | 91.4% | -1.4 pp | FAIL: worse power |
| Cross-fitted AIPW LCB | 3.1% | 0.4% | 17.1% | 82.9% | 7.1 pp | FAIL: improvement <10 pp |
| Bayesian probability | 1.3% | 0.1% | 9.7% | 90.3% | -0.4 pp | Diagnostic; ineligible |
| Distributionally robust | 2.4% | 0.3% | 15.7% | 84.3% | 5.7 pp | FAIL: improvement <10 pp |
| Combined economic | 2.5% | 0.4% | 16.1% | 83.9% | 6.1 pp | FAIL: improvement <10 pp |

All gates had unsupported ACT = 0, zero budget violations, zero early-release violations, and
positive expected policy value. Their p95/p99/CVaR aggregate downside bounds passed. Seed agreement
was at least 98.6%, fold-count agreement at least 96.6%, and drop-top-observation agreement ranged
from 92.2% to 99.0%. These successes cannot override the failed joint safety/power criterion.

The old veto is indeed highly conservative: it misses 90.0% of supported materially-positive
worlds. But the candidates that clear the required ten-point power improvement violate the null or
harmful safety limits. The evidence therefore supports neither retaining the old gate as adequate nor
replacing it with a currently tested challenger.

## Evaluator correction audit trail

The first evaluator pass incorrectly included unsupported, budget-invalid, and immature worlds in
the false-negative denominator even though action is forbidden there. Its file hashes and reason are
recorded in `results/INVALIDATED_DEVELOPMENT_RUN_1.json`. Gate definitions, thresholds, DGP, worlds,
and decisions were unchanged. The corrected power population is restricted mechanically to
supported, budget-valid, mature materially-positive worlds.

Full metrics and all 55,000 frozen candidate decisions are machine-readable in
`results/gate_development_summary.json` and `results/gate_development_worlds.jsonl`.
