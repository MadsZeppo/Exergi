# Exergi V7 assurance report

## Capability verdicts

| Capability | Verdict | Evidence |
|---|---|---|
| Observable/oracle isolation in new V7 DGP | PASS | separate observed/oracle contracts and tests; independent RNG streams |
| Population action viability | PASS on synthetic | cross-fitted AIPW; positive/null/harm fixtures and K/L/M |
| Unsupported action refusal | PASS on evaluated packs | 0 unsupported ACT across 114 development+validation worlds |
| Null/harm false promotion | PASS on evaluated packs | 0% ACT |
| Homogeneous positive action | PASS on synthetic | 100% positive lower-bound rate |
| Personalization beyond best static | FAIL | only 50% of heterogeneous validation worlds had positive increment |
| Committed risk accounting | COMPONENT PASS | property tests enforce merchant/family budgets and delayed release |
| Sequential pathwise safety | UNPROVEN | full p95/p99/CVaR, drawdown and post-observable-loss Monte Carlo not run |
| Dataset claim boundaries | PASS | immutable registry and Criteo ITT/X5 downgrade tests |
| Full external dataset suite | INCOMPLETE | full Criteo/Open Bandit/X5/Hillstrom V7 runs not executed |
| Freeze completeness | FAIL | model/config/manifest hashes frozen, but no source-code commit hash in freeze |
| Real merchant profit | UNPROVEN | no qualifying real contribution-profit RCTs |
| Final generalization | NOT OPENED | validation failed; Pack N remains sealed |

## Risk mechanism assurance

Reservations use assigned units multiplied by the maximum of posterior credible downside,
empirical family floor, merchant-declared worst case and distribution-shift stress. Every accepted
reservation must fit both budgets. An open reservation cannot be released before its actual outcome
maturity and cannot expire before its conservative expiry. Tests exercised repeated simultaneous
requests and confirmed no budget overflow.

This proves implementation invariants, not realized-path safety. Maximum pathwise CP drawdown,
p95/p99, CVaR, pre-observable loss, avoidable post-observable loss, stop latency and safe
reactivation were not estimated over the preregistered DGP grid. That missing sequential evaluation
alone prevents a V7 PASS.

The AIPW implementation gives every row out-of-fold nuisance predictions, but uses ordinary K-fold
splits for the single-shot randomized fixture. It does not yet enforce household-cluster folds.
That is acceptable only for the current independent-row fixture and must be fixed before applying
the estimator to repeated-household evidence.

## Overall verdict

**FAIL.** The layer is materially safer and more honest than V6.2, but it has not earned a final
reveal or a commercial claim.
