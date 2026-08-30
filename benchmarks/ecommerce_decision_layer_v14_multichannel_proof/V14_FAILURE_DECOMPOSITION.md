# V14 failure decomposition

Status: `V14_DEVELOPMENT_GATE_FAIL_VALIDATION_CLOSED`

Failed preregistered gates: `positive_point_vs_bau`, `lower_95_vs_bau_positive`, `fold_agreement_gte_80pct`, `merchant_seed_agreement_gte_80pct`, `placebos_pass`.

Primary classification: `INSUFFICIENT_POWER_AND_UNSTABLE_PERSONALIZED_VALUE`. The numerically strongest
personalized challenger did not obtain a positive 95% lower bound versus BAU/static. Promoting it would
have exposed customers without earned evidence. The selected BAU fallback captured 0% of the evaluator's
$43,156.7819 supported opportunity, which is the economic cost of the
responsible abstention in this DEVELOPMENT holdout.

If the gate fails, the operational policy is BAU/NOT_ENOUGH_EVIDENCE and VALIDATION remains closed. No
alternative candidate may replace the frozen selected candidate after evaluator metrics are visible.
