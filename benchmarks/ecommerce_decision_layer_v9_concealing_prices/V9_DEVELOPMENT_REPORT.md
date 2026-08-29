# V9 development report

Status: `V9_DEVELOPMENT_COMPLETE_VALIDATION_CLOSED`

The procedure was frozen in commit `4638172` before development
outcome access. Validation and SEALED_TEST remain closed.

## Study 1 — ordinary online store

- Evidence: `AGGREGATE_RANDOMIZED_FIELD_EVIDENCE`
- Primary: raw ARS sales revenue per assigned unique daily visitor, paired by date
- Development: 28 paired dates
- Delayed minus immediate: **20.764 ARS**
- 95% CI: [-32.787, 74.314]
- Standard error: 26.099
- Frozen development decision: `TEST_DELAYED_PRICE`
- Break-even differential action cost: 20.764 ARS per assigned visitor

The point estimate is positive, so the preregistered rule permits a TEST freeze. It is not ACT:
the interval crosses zero, the paired randomization p-value is
0.577, and the first/second-half estimates
are 56.058 and
-14.531 ARS. This is unstable development evidence.

## Study 3 — seven-email sales flyer

- Evidence: `REAL_RANDOMIZED_SALES_REVENUE`
- Primary: raw weekly ARS sales revenue per randomized recipient, assignment ITT
- Development: 385,603 recipients
- Delayed/hide minus immediate/show: **-106.666 ARS**
- 95% CI: [-201.290, -12.043]
- Standard error: 48.278
- Frozen development decision: `AVOID_DELAYED_PRICE`
- SRM p-value: 0.476

The raw-revenue bootstrap interval is
[-204.561,
-16.169] ARS. The purchase-rate,
units, log1p-revenue, and leave-top-0.1% checks all point against hiding price. Revenue is highly
sparse and heavy-tailed: 97.6% zeros,
with the top 1% accounting for
82.3% of revenue.

Fold estimates:

- Fold 0: 77.717 ARS [-135.360, 290.793]
- Fold 1: -98.333 ARS [-277.838, 81.171]
- Fold 2: -293.278 ARS [-527.896, -58.660]
- Fold 3: -96.990 ARS [-240.208, 46.228]
- Fold 4: -121.743 ARS [-388.597, 145.110]

Only one fold has a positive point estimate; the pooled primary result and all preregistered
distributional checks support freezing the immediate reference and testing `AVOID_DELAYED_PRICE`
on one-shot validation.

## Policy hierarchy

No personalized candidates were legal because the field files expose no lawful pretreatment
feature set. The development tournament therefore contains only:

1. immediate/reference in both contexts;
2. delayed/action-all in both contexts;
3. best static action selected separately by development;
4. the simple context-blind rule: keep immediate disclosure.

Study 1 advances delayed only as TEST. Study 3 keeps immediate/AVOID. No cost was invented and no
net-profit or contribution-profit claim is issued.
