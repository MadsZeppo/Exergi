# Exergi V8 Validation Proof Report

Verdict: **PASS**.

## Frozen business decision

Before VALIDATION was opened, V8 froze `STATIC_MENS_EMAIL_FOR_ALL_ELIGIBLE_CUSTOMERS`
against `No E-Mail` BAU. The declared email cost was `$0.05` per assigned email customer.
The primary unit-level outcome is spend minus that declared assignment cost.

## Randomized validation result

- Analysis population: 10,563 randomized customers
- Mens Email: 5,371
- No Email: 5,192
- Mens mean net revenue: $1.231508
- BAU mean net revenue: $0.512196
- Primary incremental net revenue/customer: $0.719312
- Neyman standard error: $0.254982
- Two-sided 95% CI: [$0.219558, $1.219067]
- Normal-approximation two-sided p-value: 0.00478688026729
- Total incremental value in the primary validation population: $7,598.097023

The primary gate uses only the untransformed difference in randomized arm means and its
two-sided Neyman 95% interval. No secondary analysis can change the verdict.

## Frozen corroborating analyses

- Lin ANCOVA: $0.733109, 95% CI [$0.229314, $1.236903]
- Cross-fitted AIPW: $0.734735, 95% CI [$0.231463, $1.238008]
- Assignment randomization p-value: 0.00554972251387
- Arm-stratified bootstrap: $0.719312, 95% percentile CI [$0.234264, $1.218767]

Purchaser decomposition, preregistered nonzero winsorization, leave-top diagnostics and
largest-observation influence are preserved in the machine-readable result.

## Development versus validation

- DEVELOPMENT raw net uplift: $0.688950
- VALIDATION raw net uplift: $0.719312

## Integrity and one-shot status

- Freeze commit: `6bf1f92ee7ac5d6afb1b7859cf09582266da6ce2`
- Frozen source-tree SHA-256: `8e878fcc6e773f020b71a4202a851ed9b9669be47aa2cbf6b695cadc29bb5350`
- Validation permanently consumed: `true`
- SEALED_TEST: untouched by V8 and still quarantined because historical row-0 was exposed
- Buy Baits: unchanged

## Claim authority and limitations

Authority: `REAL_RANDOMIZED_NET_REVENUE_AFTER_DECLARED_EMAIL_COST`.

On a previously unseen validation sample from a real randomized e-commerce experiment, Exergi's development-selected static action produced statistically supported incremental net revenue over business-as-usual after a preregistered email cost.

Hillstrom records spend/revenue, not contribution profit. It lacks observed COGS,
shipping, returns, payment fees and other variable costs. The `$0.05` cost is declared
rather than an observed merchant ledger. This does not prove personalization, general
merchant performance,
autonomous decision safety or production readiness.
