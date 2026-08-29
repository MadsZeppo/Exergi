# V9 validation report

Status: `SECOND_RANDOMIZED_COMMERCE_PROOF_PASS`

Both policies were selected on DEVELOPMENT, hash-frozen in commit `1fd6c27`,
and evaluated once on their untouched VALIDATION split. Reveal-start and permanent consumed
records exist for both studies. Study 3 SEALED_TEST remains unopened; Study 1 had no SEALED_TEST
by preregistration.

## Study 1 — ordinary online store

| Stage | Delayed minus immediate ARS revenue per assigned visitor | 95% CI |
|---|---:|---:|
| DEVELOPMENT | 20.764 | [-32.787, 74.314] |
| VALIDATION | 13.700 | [-36.754, 64.154] |

Frozen policy: `TEST_DELAYED_PRICE`. Validation status: `INCONCLUSIVE`. Final product decision:
`ABSTAIN`. The point direction replicated, but the paired-date interval remains wide and crosses
zero. The action did not satisfy the preregistered ACT/confirmation gate. This is aggregate
date-level evidence and cannot support customer-level uncertainty or personalization.

## Study 3 — discount sales-email flyer

| Stage | Hide/delayed minus show/immediate ARS revenue per recipient | 95% CI |
|---|---:|---:|
| DEVELOPMENT | -106.666 | [-201.290, -12.043] |
| VALIDATION | -237.570 | [-352.533, -122.607] |

Frozen policy: `AVOID_DELAYED_PRICE`. Validation status: `CONFIRMED_AVOID`. Final product decision:
`AVOID`. Equivalently, keeping prices visible improved held-out gross sales revenue by
**237.570 ARS per randomized recipient**, 95% CI
[122.607, 352.533]. Purchase probability, units, log1p revenue,
the development-fixed leave-top sensitivity, bootstrap, and randomization inference agree in
direction. SRM p=0.764.

## Economic interpretation

The package contains sales revenue, not margin, COGS, fulfillment, returns, payment fees, or
action cost. No cost was invented. Study 3's held-out break-even gross harm avoided is
237.570 ARS per recipient. These ARS effects are
not pooled with Hillstrom's USD net-revenue effect.

## Overall

One context produced `CONFIRMED_AVOID`; the other stayed `INCONCLUSIVE`. Therefore V9 earns
`SECOND_RANDOMIZED_COMMERCE_PROOF_PASS`, not `CONTEXTUAL_DECISION_PROOF_PASS`.
