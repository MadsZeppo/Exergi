# Hillstrom Forensic DEVELOPMENT Audit

## Scope and integrity

This audit used only the existing `DEVELOPMENT` parquet. It did not materialize or read VALIDATION
or SEALED_TEST outcomes. The observed 32,233 development hashes match the immutable manifest exactly
and are disjoint from both closed splits.

Arm mapping is unchanged: `No E-Mail = 0`, `Mens E-Mail = 1`, `Womens E-Mail = 2`. The public file
represents one source row per randomized customer but omits an original stable customer ID. Therefore
the audit can prove 32,233 unique row-derived unit hashes and zero duplicated unit hashes; it cannot
prove that no person occurs in two source rows. There are 3,686 rows belonging to duplicated
non-identifying feature/outcome profiles, which is expected with coarse categorical fields and many
zero outcomes and is not evidence of duplicate customers.

## Assignment and sample reconstruction

| Arm | N | Development spend mean | Spend SD | Positive spend | Zero mass |
|---|---:|---:|---:|---:|---:|
| No E-Mail | 10,856 | $0.843931 | $13.462902 | 77 | 99.2907% |
| Mens E-Mail | 10,655 | $1.582880 | $19.560670 | 133 | 98.7518% |
| Womens E-Mail | 10,722 | $1.167133 | $15.919475 | 99 | 99.0767% |

The equal-allocation sample-ratio check gives chi-square `1.949741`, p=`0.377241`; it passes the
fixed p > 0.001 diagnostic. All 13 development fields have zero missing values. Known conditional
propensity for the Mens-versus-control contrast is 0.5, so maximum IPW is 2 and arm ESS equals the
observed arm counts: 10,655 and 10,856.

Original DEVELOPMENT arm outcomes were reproduced directly from the three author-defined arm
labels. Visit means are 0.110630 (No E-Mail), 0.182825 (Mens), and 0.152770 (Womens). Conversion
means are 0.007093, 0.012482, and 0.009233 respectively. No reconstructed label or inferred arm was
used.

## Spend distribution forensics

Spend is sparse and heavy-tailed. The median, 90th, and 95th percentiles are $0 in all arms. The
99th percentile is $0 for No E-Mail and Womens E-Mail and $29.99 for Mens E-Mail. The 99.9th
percentiles are $203.42, $344.54, and $265.36 respectively; every arm has a maximum of $499.
Variances are 181.25 (No E-Mail), 382.62 (Mens), and 253.43 (Womens). This combination of rare
purchases and large conditional spend explains why small subsamples are volatile.

## Pretreatment balance

All eight legal covariates were audited. Maximum absolute standardized mean difference across both
email arms versus control is `0.020159`; maximum Cramér's V is `0.016773`. Both are far below the
fixed 0.10 diagnostic threshold. The largest numeric imbalance is Womens recency; the largest
categorical association is Womens history segment. Assignment, overlap, and pretreatment balance
all pass.

Allowed features are exactly `recency`, `history_segment`, `history`, `mens`, `womens`, `zip_code`,
`newbie`, and `channel`. Assignment is treatment-only. `visit`, `conversion`, and `spend` are
outcome-only. No post-treatment field enters an estimator.

## Why the previous +0.735009 interval was wide

The prior checkpoint evaluated the static policy on a deterministic 25% internal development
holdout of 8,105 customers, not on all 32,233 development customers. That holdout contained 2,719
No E-Mail, 2,718 Mens, and 2,668 Womens customers. Mens and control spend means were $1.685033 and
$0.909419, with SDs $22.5244 and $14.0291. The known-propensity DR policy contrast gave net
`+$0.735009`, SE `$0.511800`, and 95% CI `[-$0.268100, +$1.738119]`.

There is no arm-mapping reversal. The point direction agrees with the full-development estimate.
The wide interval follows from using roughly one quarter of development, only 55 positive spend
observations across the two relevant holdout arms, and a heavy upper tail. On all development rows,
the raw gross contrast is `+$0.738950`, SE `$0.229359`, 95% CI
`[+$0.289414, +$1.188486]`.

## CI implementation check

The analytic Welch SE is `$0.229359`; the 2,000-replicate within-arm customer bootstrap SE is
`$0.228771`. Their ratio is `1.002572`, inside the preregistered `[0.80, 1.25]` range. The bootstrap
95% percentile interval is `[+$0.292103, +$1.198635]`. Interval ordering, deterministic seed, valid
replicate count, constant propensity, and ESS diagnostics pass.

## Integrity limitation

The previously displayed raw row maps to SEALED_TEST in the original manifest. It was not modeled or
scored, but SEALED_TEST can never again be described as fully untouched. Its split was not moved.
VALIDATION remains closed and is the only possible one-shot confirmation source.
