# Exergi V7 dataset provenance report

The immutable machine-readable source is `datasets/registry.yaml`. Local file checksums were
computed before V7 validation. Dataset evidence is never promoted above its outcome and assignment
authority.

| Dataset | Assignment | Outcome authority | Local integrity | Permitted V7 use |
|---|---|---|---|---|
| Hillstrom | randomized, exact propensity absent | real randomized revenue | SHA-256 verified | multi-arm ITT, spend value and segment checks; profit only as declared scenario |
| Criteo Uplift V2.1 | randomized assignment in `treatment` | real randomized proxy outcome | publisher SHA-256 verified | visit/conversion uplift, ranking and calibration |
| Open Bandit | logged random/Bernoulli-TS policies | real randomized proxy outcome | archive SHA-256 recorded | click OPE with logged propensities |
| X5 RetailHero | `UNKNOWN_ASSIGNMENT` | observational association | three local SHA-256 hashes recorded | ranking and feature robustness only |
| BAUR | unavailable row data | insufficient | no local file | adapter/acquisition contract only |
| V7 synthetic | simulated random assignment | synthetic economic | generated from frozen manifests | mechanism, economic and safety evaluation only |

## Critical semantics

- Criteo `treatment` is assignment and the ITT treatment. `exposure` is post-assignment and is
  explicitly forbidden as treatment or a pre-treatment feature.
- Hillstrom spend is not contribution profit. Campaign cost, discount funding, COGS, shipping and
  transaction cost are absent.
- Open Bandit reward is click/engagement, not revenue or profit.
- X5 upstream randomization could not be established from local or cited documentation, so it
  cannot produce a causal PASS.
- No lawful public row-level BAUR download was verified. V7 neither scraped nor fabricated it.

## Primary sources

- Criteo AI Lab dataset page: https://ailab.criteo.com/ressources/
- Open Bandit upstream documentation: https://github.com/st-tech/zr-obp/blob/master/obd/README.md
- X5 loader documentation: https://www.uplift-modeling.com/en/latest/api/datasets/fetch_x5.html
- BAUR publication: https://doi.org/10.1007/s11573-021-01068-3

## Status

Registry integrity and claim-boundary tests passed. Full 13.9M-row Criteo and full Open Bandit
scalability/OPE reruns were not executed in this pass. Therefore the registry is verified, but the
complete real-dataset V7 evidence suite remains incomplete.

