# V13 economic and outcome contract

Status: `RANDOMIZED_EARNINGS_ONLY`

## Primary outcome

The candidate primary outcome, to be frozen before opening values, is individual earnings in months
1-30 after random assignment:

`Y_i = sum(UIERN01_i, ..., UIERN30_i)`

The source is Upjohn's official `SCALEDUI` analysis file. It contains state unemployment-insurance wage
records, edited/imputed by the original study and scaled to survey earnings levels. The primary population
is the intersection of that 12-site file and the official 30-month analysis membership: 15,134 people.

- Unit: nominal U.S. dollars per randomized person.
- Horizon: calendar months 1-30 after random assignment; month 0 is excluded.
- Price year: no single price year. The final report says earnings are nominal dollars across the
  1987-1991 assignment/follow-up period.
- Maturity: official 30-month analysis membership only.
- Missingness: monthly completeness must be asserted after preregistration and before modeling; failure
  stops development rather than changing the outcome.

This is not contribution profit, merchant profit, net income or an e-commerce outcome.

## Why the pooled `NEWERN` outcome is not primary

The official pooled survey/UI analysis contains 15,981 people, but 199 of 416 male-youth-arrestee rows
lack months 19-30. That subgroup is identified from a follow-up response about a pre-assignment arrest,
so selecting an individual-policy evaluation sample by that post-assignment measurement is not clean.
The 12-site `SCALEDUI` contract gives a common individual outcome construction without using that split.

## Cost authority

The public-use package documents program-cost methodology and group-level benefit-cost results, but no
reproducible person-level or assignment-level cost variable is released in the V13 analytic contract.
Therefore:

- primary policy value is gross randomized earnings value;
- treatment cost is a preregistered sensitivity/break-even grid only;
- no net-economic PASS may be claimed;
- the strongest possible claim is `REAL_RANDOMIZED_PERSONALIZED_EARNINGS_POLICY_VALUE`.

Program participation data (`PPD_DAT`) and service hours are post-treatment and cannot be used as policy
features or as individualized assignment costs.
