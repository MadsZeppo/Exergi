# Hillstrom V7.2 Development Preregistration

This protocol is fixed before the V7.2 Hillstrom development outcome materialization and run.

## Authority and isolation

- Preserve all three original randomized arms: No E-Mail, Mens E-Mail, Womens E-Mail.
- Known primary assignment propensity: `1/3` for every arm.
- Primary outcome: two-week `spend`, interpreted as randomized revenue/demand, not profit.
- Use only the existing `DEVELOPMENT` hash split. Do not materialize or read validation/sealed rows.
- Every nuisance prediction used on train is five-fold OOF. Evaluation uses an inner 75/25
  development split with models fit only on the inner train portion.

## Features

Allowed pre-treatment features are `recency`, `history_segment`, `history`, `mens`, `womens`,
`zip_code`, `newbie`, and `channel`. Assignment `segment` is treatment-only. `visit`, `conversion`
and `spend` are outcomes and forbidden as features.

## Cost sensitivity

Email cost is not present in Hillstrom. Treat it only as a declared per-recipient scenario. The
fixed grid is `$0`, `$0.01`, `$0.05`, `$0.10`, `$0.25`, `$0.50`, `$1.00`, `$2.00`; primary reporting
uses `$0.05`. No-Email has zero action cost. Break-even email cost is reported from held-out gross
incremental spend divided by email assignment rate.

## Policies and decision rule

Compare BAU, treat-all per arm, best static, a fixed RFM/product-affinity segment policy, one-stage
monetary models, a two-part conversion-times-conditional-spend model, T/X/R/DR learners, DR causal
forest and shallow honest/DR policy tree. Rank only by held-out known-propensity DR net value.

Material observable heterogeneity requires the personalized policy to beat best static on inner
held-out development with a positive 95% lower bound and at least `$0.01` incremental net value per
customer. Otherwise retain best static or BAU. This is development-only and cannot select an
official model or authorize validation.
