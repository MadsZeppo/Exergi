# V7.2 Hillstrom Development Checkpoint — 2026-08-28

## Scope and authority

Only the existing Hillstrom DEVELOPMENT split was used. The original three arms remain separate,
known assignment probability is `1/3`, and the outcome is two-week randomized spend/revenue—not
profit. The model matrix uses all eight author-documented pre-treatment fields and no outcome or
assignment feature.

Development contains 32,233 customers: 10,856 No Email, 10,655 Mens Email and 10,722 Womens Email.
The inner split is 24,128 train and 8,105 held-out customers with zero overlap.

## Primary economic result

The preregistered primary scenario charges `$0.05` per emailed customer.

| Policy | Held-out net value/customer | Versus BAU | Versus best static | 95% CI vs best static |
|---|---:|---:|---:|---:|
| BAU / No Email | 0.910178 | 0 | -0.735009 | [-1.738119, 0.268100] |
| Best static / Mens Email | 1.645187 | 0.735009 | 0 | [0, 0] |
| Tweedie T learner | 1.633220 | 0.723042 | -0.011967 | [-0.492335, 0.468401] |
| Ridge T learner | 1.547685 | 0.637507 | -0.097502 | [-0.802772, 0.607767] |
| Two-part hurdle | 1.520270 | 0.610092 | -0.124918 | [-0.819211, 0.569375] |
| Simple RFM/affinity segment | 1.388519 | 0.478341 | -0.256668 | [-0.982996, 0.469659] |
| DR causal forest | 1.147947 | 0.237770 | -0.497240 | [-1.181306, 0.186826] |

Best static versus BAU has 95% CI `[-0.268100, 1.738119]`. Tweedie versus BAU has CI
`[-0.216231, 1.662315]`. Both positive point estimates remain statistically uncertain on the inner
held-out development split.

## Cost and stability

- Static Mens point-estimate break-even email cost: `$0.7850` per recipient.
- Train-development selects Mens Email from `$0` through `$0.50`.
- At `$1.00` and `$2.00`, it selects No Email/BAU.
- Tweedie beats static in four of five stability folds, but its fold increments span `-1.3622` to
  `+0.6104`; one heavy negative fold dominates the aggregate.
- No personalized candidate beats best static, and all personalized incremental intervals cross
  zero.

Verdict: **positive static development signal, incremental personalization FAIL, material observable
heterogeneity = NO**. This is not a validated positive evidence package and no official model is
frozen.

## Evidence contract

Buy Baits supplies the required randomized negative control with responsible BAU abstention.
Sequential assurance remains PASS. Hillstrom currently supplies only an uncertain development-level
static signal, and Dataset C remains missing. The new two-positive-plus-one-negative contract is not
satisfied.

## Integrity accounting

During an initial header diagnostic, the complete first CSV row was accidentally printed. The
existing manifest assigns `row-0` to SEALED_TEST. It was not used for fitting, calibration, policy
choice or scoring, but the Hillstrom sealed set cannot honestly be called fully untouched. All
subsequent materialization parsed DEVELOPMENT rows only. Validation was not opened or scored.

## Verification

- Focused pytest: 46 passed.
- Focused Ruff: passed.
- Focused mypy: passed.
- Tournament runtime: 15.4 seconds.
- Buy Baits immutable lock still verifies and rejects retuning.
- No frontend or raw data is included.
