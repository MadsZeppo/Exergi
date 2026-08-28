# V7.2 Buy Baits Development Report

Status: **DEVELOPMENT COMPLETE; NO FREEZE, VALIDATION OR SEALED REVEAL**.

Immutable classification: **REAL_RANDOMIZED_ECONOMIC_NEGATIVE_CONTROL**. Incremental
personalization = **FAIL**. Responsible BAU abstention = **PASS**.

Of 304,416 development cookies, 303,656 have complete policy-level profit. A deterministic inner
development split produced 227,746 train and 75,910 held-out cookies with zero overlap. Known
propensity `1/8` is primary. The only feature is pre-treatment device.

The train-development best static action was arm 1. On held-out development, however, control/BAU
was best among the reported policies:

| Policy | Held-out value/visitor | Increment vs train-selected arm 1 | 95% CI for increment |
|---|---:|---:|---:|
| Control/BAU | 0.019575 | 0.003789 | [-0.002217, 0.009795] |
| Announced 10% reminder, arm 4 | 0.019528 | 0.003742 | [-0.001724, 0.009207] |
| Announced 15% reminder, arm 7 | 0.018310 | 0.002524 | [-0.002634, 0.007682] |
| Huber T learner | 0.017245 | 0.001458 | [-0.002971, 0.005888] |
| Device segment / Ridge / X / R / DR / forest / tree | 0.016745 | 0.000958 | [-0.002300, 0.004216] |
| Train-selected static arm 1 | 0.015787 | 0 | [0, 0] |

The equality across several challengers is substantive: with only three device categories, they
learn the same device-to-arm mapping. The two-part model reached 0.016103. Tweedie was declared
invalid rather than shifted because four observed profit rows are negative.

No personalized candidate has a positive lower 95% bound versus best static, and every personalized
candidate is below held-out BAU. Therefore **material observable personalization = NO**. The
treatment-shuffle placebo increment is 0.000126 with CI [-0.001320, 0.001572]; the outcome-shuffle
placebo also crosses zero. Prohibited action selections are zero and every allowed arm has at least
28,273 train rows. A 0.5%/99.5% winsorization changes the train static winner from arm 1 to arm 7,
confirming tail sensitivity. An additional equal action cost of 0.0025 per exposed visitor changes
the train winner to BAU. These are declared scenarios, not inferred real costs. Runtime was 20.1
seconds.

This is a development diagnostic, not an official winner. The train/held-out reversal is the main
reason not to freeze or open validation.

The result is locked by `BUY_BAITS_DEVELOPMENT_LOCK.json`; further Buy Baits tuning and any reuse of
validation/sealed for tuning are mechanically prohibited.
