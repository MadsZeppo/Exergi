# Hillstrom Static Development Audit Preregistration

Fixed before the new forensic estimator run. This protocol does not replace or tune the prior
Hillstrom development checkpoint.

## Population and estimand

- Data: existing Hillstrom `DEVELOPMENT` materialization only.
- Contrast: Mens E-Mail versus No E-Mail; Womens E-Mail remains in assignment/balance audit but is
  outside this static contrast.
- Estimand: intention-to-treat average difference in two-week spend per eligible customer in the
  DEVELOPMENT population.
- Primary economic estimand: gross spend ITT minus the already locked `$0.05` email cost.
- Conditional known propensity inside the Mens/No-Email contrast: `0.5`.

## Estimators

Run the same contrast with raw Welch difference-in-means, predeclared-strata adjustment, ANCOVA with
HC3 uncertainty, CUPED using prior-year `history`, five-fold cross-fitted AIPW,
heteroskedasticity-robust marginal OLS/HC3, and a stratified customer-level bootstrap of the raw
difference.

Strata are fixed as channel × recency (`1–3`, `4–6`, `7–12`). Covariates are the eight author-
documented pre-treatment variables. No post-treatment field is permitted.

## Robustness and stability

- Deterministic five folds from hashed development unit ID.
- Upper-tail winsorization sensitivities: none, 99.9%, 99.5%, and 99.0%. No lower-tail transform
  because spend is nonnegative.
- Bootstrap: 2,000 within-arm customer resamples for the raw estimator and 300 within-arm resamples
  for the Huber outlier sensitivity; fixed seed `72_2031`.
- Analytic/bootstrap implementation check: standard-error ratio must be between `0.80` and `1.25`,
  interval ordering must hold, and observed assignment ESS must equal the arm sample sizes under
  constant known propensity.

## Static freeze gate

A static Mens candidate passes only if all conditions hold:

1. primary net point estimate is positive;
2. the minimum 95% lower bound across ANCOVA, CUPED and AIPW, after subtracting `$0.05`, is positive;
3. at least three valid estimators select Mens over No Email at the locked cost;
4. every core adjusted estimator is net-positive in at least four of five folds, every leave-one-
   fold-out estimate is positive, and no fold has net effect below `-$0.05`;
5. net value is positive at `$0.05`;
6. assignment, leakage, overlap, bootstrap and balance gates pass;
7. the static action remains net-positive under all preregistered winsorization sensitivities.

The conservative lower bound is selected mechanically as the minimum, never the most favorable.
Failure produces `HILLSTROM_INCONCLUSIVE_VALIDATION_REMAINS_CLOSED`; no model freeze is written.

## Estimand correction recorded during implementation QA

The initially named Huber regression was found to target a robust conditional location, not the
preregistered marginal mean-spend ITT, and it degenerates to zero when more than half of outcomes are
zero. It is therefore retained only as a disclosed outlier sensitivity and is not counted as a valid
mean estimator or gate input. Heteroskedasticity-robust marginal OLS/HC3 supplies the requested robust
regression while preserving the mean estimand. This correction was made before any freeze decision;
the independently failing fold and winsorization gates make it incapable of changing the final
status.

## Policy hierarchy

Promotion order is BAU → supported static → supported segment → supported personalized. Segment or
personalized policy additionally requires positive held-out incremental net value over the preceding
level, positive 95% lower bound, at least four of five positive stability folds, no fold below
`-$0.05`, and adequate randomized support. Otherwise the hierarchy retains the simpler level.
