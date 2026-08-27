# V7 heterogeneity failure decomposition

H-M are consumed diagnostic-only packs. This report does not rehabilitate V7 and cannot be used as V7.1 validation.

## Frozen economic materiality

Minimum economically relevant personalization increment: **0.10 net CP per eligible customer**. This is inherited from V7's preregistered minimum population effect, not selected from these results. V7 had no separate treatment or switching-cost fields; both are therefore reported as zero rather than retrofitted.

## Classification counts

- MATERIAL_OBSERVABLE_PERSONALIZATION: 6
- NONMATERIAL_PERSONALIZATION: 6
- MATERIAL_UNOBSERVABLE_PERSONALIZATION: 0
- ESTIMATION_OR_POLICY_FAILURE: 0

## World-level decomposition

| World | Class | Full oracle Δ | Observable oracle Δ | Segment oracle Δ | Forest Δ | Forest/observable Δ | Positive subgroup | RATE [lower] | Promoted |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| H-02-sparse_heterogeneity | NONMATERIAL_PERSONALIZATION | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.000 | 6.7% | 0.3584 [0.1656] | yes |
| H-03-qualitative_heterogeneity | MATERIAL_OBSERVABLE_PERSONALIZATION | 0.9613 | 0.9352 | 0.9613 | 0.8000 | 0.855 | 44.4% | 1.1347 [0.9597] | yes |
| I-02-sparse_heterogeneity | NONMATERIAL_PERSONALIZATION | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.000 | 6.5% | 0.2786 [0.1431] | no |
| I-03-qualitative_heterogeneity | MATERIAL_OBSERVABLE_PERSONALIZATION | 0.9460 | 0.9419 | 0.9460 | 0.8545 | 0.907 | 44.2% | 0.9100 [0.7605] | yes |
| J-02-sparse_heterogeneity | NONMATERIAL_PERSONALIZATION | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.000 | 7.3% | 0.2151 [0.1057] | no |
| J-03-qualitative_heterogeneity | MATERIAL_OBSERVABLE_PERSONALIZATION | 0.8787 | 0.8684 | 0.8787 | 0.7668 | 0.883 | 42.4% | 0.9300 [0.7917] | yes |
| K-02-sparse_heterogeneity | NONMATERIAL_PERSONALIZATION | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.000 | 7.0% | 0.2972 [0.1276] | no |
| K-03-qualitative_heterogeneity | MATERIAL_OBSERVABLE_PERSONALIZATION | 0.9149 | 0.9055 | 0.9149 | 0.7756 | 0.857 | 46.1% | 1.1466 [1.0010] | yes |
| L-02-sparse_heterogeneity | NONMATERIAL_PERSONALIZATION | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.000 | 7.7% | 0.3256 [0.1656] | no |
| L-03-qualitative_heterogeneity | MATERIAL_OBSERVABLE_PERSONALIZATION | 0.7967 | 0.7844 | 0.7967 | 0.6871 | 0.876 | 43.5% | 0.8231 [0.6814] | yes |
| M-02-sparse_heterogeneity | NONMATERIAL_PERSONALIZATION | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.000 | 6.2% | 0.4211 [0.2379] | yes |
| M-03-qualitative_heterogeneity | MATERIAL_OBSERVABLE_PERSONALIZATION | 0.7867 | 0.7721 | 0.7867 | 0.7050 | 0.913 | 46.5% | 0.9622 [0.8367] | yes |

## Interpretation

`FULL_ORACLE` uses individual truth only after policy predictions are frozen. `OBSERVABLE_ORACLE` is a separately fitted evaluator-only forest trained on 20,000 independent synthetic rows using legitimate pre-treatment features and oracle labels; it shares no fitted state or predictions with the policy. `SEGMENT_ORACLE` can choose only from the fixed RFM/intent/loyalty segment set.

The old aggregate 80% gate is withdrawn. V7.1 success is conditional on whether material economic personalization is observable in the first place.
