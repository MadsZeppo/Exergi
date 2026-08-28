# Buy Baits V1 Replication Report

Verdict: **CENTRAL SUPPLIED-CODE STATISTICS REPRODUCED; ONE PACKAGE-DEFINED TABLE UNAVAILABLE**.

The audit recreated `Cleaning.do` treatment indicators and the clustered OLS specifications in
Tables 1 and 2 directly from `data/data.dta`. Coefficients below are decimal units; the Stata table
multiplies them by 100 for display.

## Table 1

Purchase regression (`N=609,468`, control constant 0.017743):

| Term | Coefficient | Cluster SE |
|---|---:|---:|
| automatic 10% | 0.003964 | 0.000736 |
| claim 10% | 0.003055 | 0.000721 |
| 10% reminder | 0.001362 | 0.000774 |
| 10% announcement | -0.001059 | 0.000779 |
| claim 15% | 0.004844 | 0.000740 |
| 15% reminder | 0.001275 | 0.000791 |
| 15% announcement | -0.000243 | 0.000798 |

Conditional redemption has an automatic-arm constant of 0.880363. The 10% and 15% claim effects
are -0.354245 and -0.310351; reminder effects are 0.103579 and 0.121582.

## Table 2

The official code zero-fills non-purchasers, leaves purchaser rows with missing money out, and
normalizes by the control mean. Reproduced control means are 0.015641 for basket value and 0.017678
for package-provided profit.

| Outcome/specification | Automatic | 10% claim | 10% reminder | 15% claim | 15% reminder |
|---|---:|---:|---:|---:|---:|
| Basket, pooled | 0.202023 | 0.199395 | — | 0.324149 | — |
| Basket, reminder | 0.202023 | 0.170052 | 0.044093 | 0.286667 | 0.056067 |
| Profit, pooled | 0.037835 | 0.086818 | — | 0.115115 | — |
| Profit, reminder | 0.037835 | 0.073661 | 0.019771 | 0.110390 | 0.007068 |

The public README contains no numeric expected-output table. An older working-paper version has a
different sample and cannot be used as an exact V1 checksum. Reproduction is therefore against the
official V1 code-defined transformations and regressions, with direct arm-mean identities as a
cross-check.

## Monetary audit

- Demand: complete binary `purchase` outcome.
- Order value/revenue: `purchasevalue`; 1,610 purchaser rows are missing.
- Redemption: `red`, observed for all 13,226 purchaser rows.
- Profit: package-provided `profit`; 1,615 purchaser rows are missing.
- Rebate/discount cost: no separate field.
- COGS, shipping, payments, returns and variable costs: no separate fields.

The policy outcome is the official `profit` field, aggregated within cookie after zero-filling
non-purchasers. Cookies with any purchased row lacking profit are excluded from development policy
learning. No COGS or margin is invented. Consequently this supports randomized short-term retailer
profit/economic-value claims, not verified contribution profit.

Appendix Table D1 cannot be reproduced because the README explicitly says `browsing.dta` is not
public. All other supplied code was inspected; the development tournament does not depend on that
missing browsing table.
