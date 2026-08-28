# Hillstrom V7.2 Feature and Assignment Audit

Verdict: **FEATURE TIMING PASS; DEVELOPMENT ISOLATION PASS; SEALED INTEGRITY INCIDENT**.

The original dataset author describes 64,000 customers who purchased in the preceding year, random
assignment in equal thirds to Mens E-Mail, Womens E-Mail or No E-Mail, and outcomes observed for two
weeks after delivery. Source:
https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html

| Field | Original definition | V7.2 timing |
|---|---|---|
| `recency` | months since last purchase | PRETREATMENT_ALLOWED |
| `history_segment` | prior-year spend category | PRETREATMENT_ALLOWED |
| `history` | prior-year actual spend | PRETREATMENT_ALLOWED |
| `mens` | prior-year Mens purchase indicator | PRETREATMENT_ALLOWED |
| `womens` | prior-year Womens purchase indicator | PRETREATMENT_ALLOWED |
| `zip_code` | geographic class | PRETREATMENT_ALLOWED |
| `newbie` | first customer purchase occurred in prior year | PRETREATMENT_ALLOWED |
| `channel` | prior-year purchase channel | PRETREATMENT_ALLOWED |
| `segment` | randomized email assignment | ASSIGNMENT_ONLY |
| `visit` | website visit in following two weeks | OUTCOME_ONLY |
| `conversion` | purchase in following two weeks | OUTCOME_ONLY |
| `spend` | dollars spent in following two weeks | OUTCOME_ONLY |

The three arms remain separate. Primary known propensity is `1/3`; empirical development counts are
10,856 control, 10,655 Mens and 10,722 Womens.

The existing SHA-256 manifest assigns 32,233 rows to DEVELOPMENT, 15,928 to VALIDATION and 15,839 to
SEALED_TEST. The byte-stream materializer determines the split from row index before decoding a row,
parses only DEVELOPMENT rows and persists only hash IDs. A focused test proves that undecodable
nondevelopment bytes are skipped without outcome parsing.

## Integrity incident

Before the byte-stream guard was installed, a diagnostic header command printed the complete first
CSV row. The manifest maps `row-0` to SEALED_TEST, so its zero-valued visit/conversion/spend fields
were exposed. It was never used for fitting, policy choice, calibration or scoring. Nevertheless,
the future Hillstrom sealed set cannot be called entirely untouched and must be treated as
compromised unless a human-approved, outcome-independent replacement protocol is established.

No other validation/sealed Hillstrom outcome was decoded by the V7.2 materializer or development
runner.
