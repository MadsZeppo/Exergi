# Buy Baits V1 Provenance and Forensic Audit

Verdict: **QUALIFIED REAL RANDOMIZED ECONOMIC EVIDENCE, WITH CLAIM DOWNGRADE**.

## Immutable source

| Item | Value |
|---|---|
| Official project | Data and Code for “Buy Baits and Consumer Sophistication” |
| DOI | `10.3886/E198781V1` |
| V1 publication | 2025-04-15 |
| Raw archive | `data/raw/buy_baits/198781-V1.zip` (ignored, mode `0444`) |
| Archive SHA-256 | `3242238801aa40f5802e356d6a5d8cc108ccce9044be6586709017684a1642bc` |
| `data.dta` SHA-256 | `f60bdb945c08c2cf93d93ebd3680509e6db930fb7204e3b3ba0789e62c0c8907` |
| `README.pdf` SHA-256 | `a03e76bd2e78422b7d684b7021f3e6c2dbffad6a4d69ee7b05e10b2714cf9f01` |

README.pdf was rendered and visually checked on all three pages. All 15 supplied Stata `.do`
files were read. `browsing.dta` is confidential and absent by design, so Appendix Table D1 cannot
be reproduced. The package otherwise contains the main data and code invoked by `Master.do`.

## Design and integrity

- Randomization unit: HTTP cookie / website visitor.
- Assignment: eight equally probable arms, known probability `1/8` per arm.
- Sample: 609,468 transaction/visitor records from 609,137 unique cookies.
- Period: 14 anonymized date codes. Exact calendar dates are not disclosed.
- Outcome window: not precisely documented; no maturity claim is made beyond observed records.
- Repeated cookies: 282 cookies have more than one row; maximum is nine rows.
- Treatment contamination: zero cookies assigned to multiple arms.
- Exact duplicate rows: zero.
- SRM: chi-square 12.263, p=0.0922; no rejection at 5%, but retained as a diagnostic.
- Device balance: chi-square 7.758 on 14 df, p=0.9015.
- Purchase is observed on all rows. Monetary completeness is materially weaker.

Arm unit counts are 76,196; 76,364; 75,628; 76,304; 75,843; 76,728; 76,298; and
75,776 for arms 1 through 8. Empirical propensities range from 12.416% to 12.596%.

## Variable timing dictionary

| Variable | Meaning in package | Timing class |
|---|---|---|
| `id` | cookie/group identifier | EVALUATOR_ONLY |
| `date` | anonymized assignment date code | ASSIGNMENT_ONLY |
| `treatment` | randomized arm | ASSIGNMENT_ONLY |
| `purchase` | purchase indicator | OUTCOME_ONLY |
| `red` | rebate redemption | OUTCOME_ONLY |
| `purchasevalue` | transaction basket/revenue | OUTCOME_ONLY |
| `profit` | package-provided transaction profit | OUTCOME_ONLY |
| `counting` | repeat-purchase count | POST_TREATMENT_FORBIDDEN_FEATURE |
| `device` | first observed device at entry | PRETREATMENT_ALLOWED |
| `sessions` | subsequent session count | POST_TREATMENT_FORBIDDEN_FEATURE |
| `out_num90` | outage-related flag with undocumented causal timing | UNKNOWN_FORBIDDEN |
| `income_cat` | income category with undocumented causal timing | UNKNOWN_FORBIDDEN |

`UNKNOWN_FORBIDDEN` is fail-closed. The development policy uses only one-hot encoded `device`.

## Frozen governance

`SCIENTIFIC_ALL_ARMS = {1,2,3,4,5,6,7,8}`.

`ENTERPRISE_ALLOWED_ARMS = {1,4,7,8}`: automatic rebate, announced reminder variants, and control.
Arms 3 and 6 are RESTRICTED because reminders were not announced at assignment. Arms 2 and 5 are
PROHIBITED because the claim friction has no reminder. This rule was set from mechanics before
policy values were estimated and cannot be changed based on profit.

## Immutable splits

The SHA-256 split uses the cookie as highest randomized unit, seed `72_2001`, and persists only
hashed identifiers.

| Split | Cookies |
|---|---:|
| DEVELOPMENT | 304,416 |
| VALIDATION | 152,097 |
| SEALED_TEST | 152,624 |

Manifest SHA-256: `cad43be571eb9faf0018a93b8517eeb41d0df4566c6b133df990d153da97341a`.
The development materialization contains no raw cookie ID. Validation and sealed outcomes were not
materialized or opened by the development runner.

Machine-readable evidence is in `results/buy_baits_forensic_audit.json`.
