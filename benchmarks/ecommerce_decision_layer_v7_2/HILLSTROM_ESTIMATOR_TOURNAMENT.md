# Hillstrom DEVELOPMENT Estimator Tournament

## Estimand

Every valid estimator targets the DEVELOPMENT intention-to-treat difference in mean two-week spend
per eligible customer: Mens E-Mail minus No E-Mail. The primary economic transformation subtracts
the locked `$0.05` per emailed customer. Known propensity in this two-arm contrast is 0.5.

## Results

| Estimator | Gross uplift | SE | Gross 95% CI | Net at $0.05 | Net 95% CI | Break-even cost |
|---|---:|---:|---:|---:|---:|---:|
| Raw difference in means | $0.738950 | $0.229359 | [$0.289414, $1.188486] | $0.688950 | [$0.239414, $1.138486] | $0.738950 |
| Stratified difference in means | $0.732452 | $0.228601 | [$0.284402, $1.180502] | $0.682452 | [$0.234402, $1.130502] | $0.732452 |
| ANCOVA, HC3 | $0.725803 | $0.228658 | [$0.277642, $1.173964] | $0.675803 | [$0.227642, $1.123964] | $0.725803 |
| CUPED with prior-year history | $0.737886 | $0.229283 | [$0.288500, $1.187273] | $0.687886 | [$0.238500, $1.137273] | $0.737886 |
| Five-fold cross-fitted AIPW | $0.724586 | $0.228533 | [$0.276670, $1.172502] | $0.674586 | [$0.226670, $1.122502] | $0.724586 |
| Marginal OLS, HC3 robust | $0.738950 | $0.229370 | [$0.289393, $1.188507] | $0.688950 | [$0.239393, $1.138507] | $0.738950 |
| Customer bootstrap | $0.738950 | $0.228771 | [$0.292103, $1.198635] | $0.688950 | [$0.242103, $1.148635] | $0.738950 |

The valid point estimates span only `$0.014364`; at the population-average level they agree strongly
on Mens E-Mail. The conservative adjusted net lower bound is AIPW's `+$0.226670`.

ANCOVA uses all eight legal covariates with HC3 uncertainty. CUPED uses `history`, the prior-year
monetary history field. AIPW uses known p=0.5 and strict hash-based five-fold cross-fitting; no row
receives nuisance predictions from a model trained on that row. Marginal robust OLS uses HC3 and
preserves the mean-spend estimand.

## Robust-location diagnostic

The originally named Huber fit returns approximately zero because a robust conditional-location
loss sees more than 98% zeros. It does not target the marginal mean ITT under this distribution and
is therefore reported only as an outlier sensitivity, not counted as a valid mean estimator or gate
vote. This estimand correction is recorded in the static preregistration amendment.

## Locked cost grid

Using the raw point estimate, net value per customer is `$0.738950`, `$0.728950`, `$0.688950`,
`$0.638950`, `$0.488950`, `$0.238950`, `-$0.261050`, and `-$1.261050` at costs `$0`, `$0.01`,
`$0.05`, `$0.10`, `$0.25`, `$0.50`, `$1.00`, and `$2.00`. The gross point-estimate break-even
email cost is `$0.738950` per recipient. Hillstrom contains revenue, not observed contribution
profit, so every net number is a declared cost scenario rather than Level-4 profit evidence.

## Fold stability

All three adjusted mean estimators and robust marginal OLS are positive in four of five folds and
positive in every leave-one-fold-out estimate. However, the same fold is materially negative:

| Estimator | Minimum fold net | Positive folds | All leave-one-out positive |
|---|---:|---:|---:|
| ANCOVA HC3 | -$0.167528 | 4/5 | yes |
| CUPED | -$0.155238 | 4/5 | yes |
| Cross-fitted AIPW | -$0.138011 | 4/5 | yes |
| Robust marginal OLS | -$0.160274 | 4/5 | yes |

The preregistered requirement was no fold below `-$0.05`; it fails. This is sampling instability,
not estimator disagreement: every method identifies the same adverse fold.

## Winsorization sensitivity

At 99.9% and 99.5% upper caps, all valid mean estimators remain net positive. At 99.0%, the pooled
cap is exactly `$0` because more than 99% of observations are zero, so every capped effect becomes
zero and net value becomes `-$0.05`. This sensitivity is mechanically destructive for this
zero-inflated outcome, but it was preregistered and is reported rather than removed after seeing it.
The sensitivity gate therefore fails.

## Interpretation

Mean uplift evidence in DEVELOPMENT is positive and estimator-consistent. It is not sufficiently
stable under the preregistered freeze contract. This tournament supports an economically promising
static candidate, not a frozen decision or a validation reveal.
