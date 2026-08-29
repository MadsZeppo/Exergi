# Exergi V8 Preregistration

## One question

Can Exergi select an economic action only from Hillstrom DEVELOPMENT, freeze it before outcome
reveal, and obtain higher net revenue than BAU on the previously unopened Hillstrom VALIDATION?

V8 is a separate offline proof. It does not repair or replace the immutable V7.2 or V7.3
checkpoints. V7.3 asked whether a general gate can repeatedly authorize actions safely across
changing worlds. V8 asks whether one development-selected static action produced positive economic
value in one independent randomized validation sample.

## Frozen decision and estimand

- Population: every randomized validation customer in the `Mens E-Mail` and `No E-Mail` arms.
- Treatment: assignment to `Mens E-Mail`; engagement, visit and conversion are not treatment.
- BAU/control: assignment to `No E-Mail`.
- Policy: `STATIC_MENS_EMAIL_FOR_ALL_ELIGIBLE_CUSTOMERS`.
- Declared email cost: `$0.05` per customer assigned to an email arm.
- Unit outcome: `spend - 0.05 * I(assignment != No E-Mail)`.
- Estimand: randomized intention-to-treat difference in mean net revenue, Mens minus control.
- Zero spend is a valid outcome and remains in the analysis.

The primary estimator is the raw difference in means with Neyman heteroskedastic standard error
`sqrt(s_t^2/n_t + s_c^2/n_c)` and a two-sided 95% confidence interval. PASS requires every integrity
gate, a positive point estimate, and a strictly positive lower endpoint. Otherwise the proof is FAIL,
unless integrity is broken, in which case it is INVALID.

There is one confirmatory hypothesis. Womens Email is secondary and cannot replace Mens Email.

## Frozen corroborating analyses

Secondary analyses cannot change the primary verdict:

1. Lin-style ANCOVA using all eight audited pretreatment fields, centered treatment-blind, with
   treatment interactions and HC3 uncertainty;
2. five-fold cross-fitted AIPW with known conditional propensity `0.5`, fixed Ridge `alpha=10`,
   and influence-function uncertainty;
3. 20,000 fixed-seed assignment permutations preserving treatment group size;
4. purchaser-rate and revenue-per-purchaser decomposition;
5. nonzero-outcome caps fixed from DEVELOPMENT at P99 and P99.5;
6. leave-top-1 and leave-top-5 diagnostics;
7. 5,000-replicate within-arm bootstrap with fixed seed;
8. largest-observation influence diagnostics.

The full-distribution P99 winsorization used historically is prohibited here: more than 99% of many
arms are zero, so that rule mechanically set the cap to zero and changed the mean-economic estimand
into a degenerate statistic. Huber regression may be descriptive only and cannot replace mean value.

## Frozen claim boundary

The only possible authority is
`REAL_RANDOMIZED_NET_REVENUE_AFTER_DECLARED_EMAIL_COST`. Hillstrom lacks observed COGS, shipping,
returns, payment fees and other variable costs. V8 can never issue contribution-profit,
personalization, merchant-generalization, autonomous-safety or production-readiness claims.

## One-shot protocol

Code, config, hashes, tests and the decision are committed before reveal. The runner writes a
reveal-start lock before parsing any validation outcome. That lock permanently consumes validation,
including after a crash. A second reveal, changed config/code/split, SEALED_TEST fallback, subgroup
mining, cost changes, alternative alpha or alternate winner is forbidden.
