# V7.1 recovery and forensic audit

Audit timestamp: 2026-08-27 (Europe/Copenhagen). This report was written before any V7.1
development, validation, sequential-tournament, real-data or merchant-pilot execution.

## Repository boundary

- Immutable V7 reference commit: `aabda4537542c6aebcb3269c96e1b4e684ed5e59` (`78`).
- Pack N remains closed. V7.1 Pack U remains sealed and unmaterialized.
- No O/P/Q development run has occurred. No R/S/T validation pack has been opened.
- The worktree contains unrelated frontend changes in `next-env.d.ts`, `package.json` and
  `package-lock.json`. They are preserved but excluded from V7.1/backend work and commits.
- `benchmarks/*` is ignored except V7. The new V7.1 tree therefore exists locally but is hidden
  from ordinary `git status`; the ignore rules must be narrowed before a backend commit.

## Recovered completed work

- Read-only H-M heterogeneity decomposition code and generated diagnostic output.
- Explicit 0.10 net-CP materiality rule and preliminary economic-identifiability taxonomy.
- Runtime and AST-based quarantine for invalidated V6-V6.2 oracle-derived source priors.
- A preliminary V7.1 preregistration, independent O-U pack specification, economic DGP,
  development model candidates, outer-holdout evaluator and development-only runner.
- A preliminary committed-risk sequential simulator and focused budget tests.
- A preliminary claim-bounded real-data protocol/runner for Hillstrom, Criteo, Open Bandit and X5.

The focused tests previously executed during recovery passed (27 tests), but that result is not
official benchmark evidence and does not establish that the unfinished implementation is correct.

## Incomplete or scientifically unsafe items

1. The failure-decomposition outputs were written as new untracked files inside the immutable V7
   directory. They must be relocated to V7.1 without changing any tracked V7 result or report.
2. Taxonomy names do not yet match the frozen four-class contract: the code uses
   `UNOBSERVABLE_HETEROGENEITY` and has no explicit `UNSUPPORTED_PERSONALIZATION` classification.
3. The R- and DR-learners fit nuisance models in-sample. They require honest/cross-fitted nuisance
   construction before their names support the intended methodological claims.
4. The population-action and personalization gates are not cleanly separated in all evaluator
   paths. The current policy can evaluate personalization even when population evidence is
   inconclusive, and the performance label is mixed into the oracle taxonomy.
5. The development freeze lacks a complete source-tree/dependency hash and source freeze. The
   runner has no one-time validation command, no FAIL lock preventing final materialization/report,
   and insufficient manifest/hash-overlap assertions.
6. Sequential assurance lacks explicit null, harmful, unsupported, action-cost and switching-cost
   scenarios. Its budget breach metrics partly use realized drawdown rather than the ledger's
   declared committed-risk invariant, and no full 400-path tournament has run.
7. `real_data.py` is unfinished: Polars hash expressions and payload typing fail static checking;
   dataset integrity/claim fields are not yet uniformly represented. No real-data run has occurred.
8. No production-shaped win-back pilot module, versioned data contract, immutable assignment and
   outcome ledger, shadow runner, ITT analysis or pilot integration tests have been implemented.
9. Required V7.1 method, sequential, validation, real-data, pilot-readiness and merchant runbook
   reports do not yet exist (apart from preliminary protocol/preregistration documents).

## Leakage and authority review

- `V71ObservedWorld` does not expose individual effect, truth or oracle fields.
- Evaluator oracle data is generated in a separate evaluation function after deployable policy
  predictions; it is not accepted by the policy evidence type.
- The legacy scanner rejects V6/V6.1/V6.2 policy imports and known oracle-prior symbols.
- Remaining risk: evaluator and runner live in the same benchmark package without a mechanical
  prediction-freeze token. Validation opening and source-freeze checks must enforce ordering.
- Criteo's `exposure` is excluded in the preliminary runner, but this and the other real-data claim
  boundaries still need tests.

## Existing components suitable for reuse

- `CommittedRiskLedger` for immutable risk reservations until maturity/expiry.
- `ActionViabilityEngine` for population randomized economic evidence.
- `SequentialExperimentPlanner` for fixed experiment sizing.
- `commercial_twin.merchant_validation` contracts, economics outcome logic, learning records and
  RCT protocol as inputs to the pilot design; these require audit rather than duplication.
- `PredictionLedger` and V7 lifecycle records as patterns, while the pilot still needs a durable
  append-only assignment/decision/outcome contract with audit hashes.

## Recovery conclusion

Current status is **NOT READY**. V7.1 is an unexecuted research scaffold with useful components,
not a frozen or validated system. The next safe step is to correct contracts and tests, build the
merchant shadow path, commit a clean backend source freeze, and only then run O/P/Q development.
R/S/T and U remain unopened.
