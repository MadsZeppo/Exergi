# V7.1 real-data capability report

## Hillstrom

All 64,000 randomized rows were used. Best static: `MENS_EMAIL`.
Personalized-minus-best-static spend: 0.062131; predefined
segment-minus-best-static: 0.132933. Spend is revenue.
The $0.50 contact-cost result is scenario-only; no contribution-profit claim is permitted.

## Criteo

The full 13,979,592-row file and publisher checksum were verified. The frozen
hash subsample contained 998,521 rows. `treatment` was ITT assignment;
`exposure` was excluded. Authority is visit/conversion proxy outcome, never profit.

## Open Bandit

Random/BTS rows: 10,000/10,000. DR uniform-policy click estimate:
0.002311; ESS 340.4. The local publisher
archive is the 10k quick sample, not the full 26M release. Click authority only.

## X5

Rows/features: 200,039/16. Assignment remains `UNKNOWN_ASSIGNMENT`.
Results have observational-association authority only.

## Claim conclusion

No dataset in this run supports a real merchant contribution-profit claim.
