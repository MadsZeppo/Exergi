# Exergi V13 fairness and support audit

Status: `V13_DEVELOPMENT_NO_PERSONALIZED_POLICY_EARNED_REVEAL`

Protected attributes were excluded from policy features and used only after out-of-fold decisions were
frozen for reporting. These DEVELOPMENT subgroup estimates are descriptive and unvalidated.

| Reporting group | n | offer rate | DR value vs BAU |
|---|---:|---:|---:|
| `adult_men` | 2,918 | 32.8% | $390.29 |
| `adult_women` | 3,459 | 41.8% | $379.43 |
| `female_youth` | 1,455 | 45.2% | $-12.25 |
| `male_youth` | 1,193 | 38.1% | $-3.39 |

Known-propensity IPW ESS was 2335 for rows assigned the policy's offer
action and 1830 for rows assigned its control action. ESS passed, but
support alone cannot repair the failed uncertainty and stability gates.
