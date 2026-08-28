# V7.2 Buy Baits Checkpoint — 2026-08-28

## Decision

Buy Baits **does qualify as real randomized short-term economic evidence**. It does not qualify as
verified contribution-profit evidence. The package's own retailer-profit outcome supports current
claim Level 3; missing separate COGS and variable costs mechanically prohibit Level 4.

Frozen evidence classification:
`REAL_RANDOMIZED_ECONOMIC_NEGATIVE_CONTROL`. Incremental personalization is an immutable
development **FAIL**; responsible BAU abstention is a **PASS**.

Replication passed for the central code-defined arm statistics and Tables 1/2. Appendix Table D1 is
not reproducible because its confidential `browsing.dta` is intentionally absent. The exact calendar
period and outcome-maturity horizon are also not disclosed.

## Data findings

- 609,468 rows, 609,137 randomized cookies, eight known-propensity `1/8` arms.
- Zero treatment contamination and exact duplicates; 282 repeated cookies.
- SRM p=0.0922 and device-balance p=0.9015.
- All 12 fields are timing-classified; uncertain timing fails closed.
- 1,615 purchaser rows lack profit and 1,610 lack basket value.
- Development policy excludes cookies with incomplete purchased profit.
- Enterprise policy can choose only arms 1, 4, 7 and control 8.

## Development evidence

The development-only tournament uses 227,746 inner-train and 75,910 untouched inner-heldout
cookies. Candidate families are static/segment policies, one-stage and hurdle outcome models,
T/X/R/DR learners, a DR causal forest and a shallow DR policy tree.

Train development selected static arm 1 at 0.019385 estimated profit/visitor. On inner held-out
development, control/BAU was best at 0.019575; arm 1 fell to 0.015787. The best personalized
challenger, Huber T, reached 0.017245 and its increment versus train-selected static was 0.001458
with 95% CI [-0.002971, 0.005888]. It did not beat held-out BAU.

Conclusion: **no material observable personalization value**. Winsorization changes the static
winner from arm 1 to arm 7, and a declared extra exposure cost of 0.0025 changes it to BAU. The
negative result is primarily limited by one legal pretreatment feature (`device`), sparse purchases,
heavy-tailed profit and no stable held-out policy value over BAU. The largest remaining failure is
therefore static/policy instability—not data acquisition.

## Sequential status

The previously completed V7.2 development assurance remains PASS: immediate mature credible-harm
pause, committed-risk reservation, freshness/revalidation, evidence-required reactivation,
observable-only decisions, zero unsupported ACT and all nine locked gates pass. This does not imply
real validation.

## Freeze recommendation

Safe to propose freezing before any later validation:

- source checksum and cookie-level 50/25/25 split;
- known propensity `1/8`;
- full timing dictionary and fail-closed unknowns;
- scientific/enterprise governance sets;
- Level-3 claim ceiling and explicit Level-4 prohibition;
- sequential gates and development/validation/sealed isolation.

Do **not** freeze a model winner or personalized policy. A human checkpoint is required. Dataset C
is still absent, and no official freeze commit exists.

`BUY_BAITS_DEVELOPMENT_LOCK.json` hashes the audit, manifest and development result. The runner now
supports lock verification but mechanically refuses any development rerun or retuning. Validation
and sealed reveal are permanently prohibited for retuning.

## Outcome access accounting

The complete raw outcome columns were read once in the explicitly requested pre-split forensic
replication audit. This was necessary to reproduce the paper and audit missingness; it was not model
selection. After the split was defined, only the DEVELOPMENT materialization was used for modeling.
No Buy Baits validation or sealed subset was materialized, scored, ranked or revealed. Hillstrom
validation/sealed outcomes, Dataset C, V7/V7.1 packs, R/S/T, U and Pack N remain unopened.

## Verification

- Focused tests: 34 passed.
- Focused Ruff: passed.
- Focused mypy: passed.
- Development tournament runtime: 20.1 seconds.
- Full repository pytest was green at the incoming checkpoint and was not repeated unnecessarily.

Detailed machine-readable results:

- `results/buy_baits_forensic_audit.json`
- `results/buy_baits_development_tournament.json`
- `results/sequential_assurance.json`
