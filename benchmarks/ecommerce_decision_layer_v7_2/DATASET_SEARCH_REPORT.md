# V7.2 Dataset Search Report

Search date: 2026-08-28. Verdict: **DATASET_C_NOT_FOUND**.

## Mandatory criteria

A candidate must be real-world commerce/retail/subscription/marketing, randomized with known or
mechanically verifiable assignment, row-level, have pretreatment covariates and a continuous
monetary outcome, permit research use, and not require post-treatment features.

## Audited candidates

| Candidate | Randomized authority | Row-level money | Pretreatment X | Propensity | Result |
|---|---|---|---|---|---|
| Dominick's oatmeal | The official page says randomized experiments occurred in the broader research program, but the downloaded oatmeal movement/UPC files contain no assignment manifest or experiment-window mapping | Weekly sales, price and profit-margin fields exist | Store/product history exists | Not reconstructable from installed files | **REJECT**: observational scanner rows cannot be relabeled as the randomized experiment |
| Information Nudges/Subsidies, Zenodo 13993677 | Paper/package describes experimental interventions | Replication code expects transaction files | Only `survey.csv` is present in the downloaded archive | Cannot audit from the incomplete archive | **REJECT**: required `analytics.csv` and `product.csv` referenced by `Cleaning.do`/`Merge.do` are absent |
| Criteo uplift | Randomized marketing experiment | Conversion/visit only | Yes | Known | **REJECT**: no monetary outcome authority |
| Open Bandit | Logged policy | Click reward only | Yes | Logged | **REJECT**: click is not economic value |
| X5/Lenta/MegaFon | Assignment authority insufficient or binary response only | Insufficient | Varies | Insufficient | **REJECT** |
| Starbucks/Udacity | Simulated exercise | Monetary fields exist | Yes | Simulated | **REJECT**: not real-world proof |

## Primary-source observations

- Chicago Booth documents randomized experiments in more than 25 categories, but its public
  movement files are general scanner histories; the installed oatmeal rows do not identify which
  units were assigned to which randomized price condition:
  https://www.chicagobooth.edu/research/kilts/research-data/dominicks
- The official Zenodo package was downloaded from
  https://zenodo.org/records/13993677. Its MD5 matches the published
  `52427d22601dd2c29498b6eb2b6772c4`; local SHA-256 is
  `cdd3e3037b7906abb905ad1e10465488d378d0cd648957d819fd34bb588ec768`.

No candidate was promoted by inference. V7.2 therefore has fewer than three qualified datasets and
must stop before real-world sealed-test access.
