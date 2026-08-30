# V12 qualification stop report

## Verdict

`V12_DATA_NOT_CAUSALLY_QUALIFIED`

The official data and documentation were acquired successfully. The stop is not a provenance
failure and does not say that the Pennsylvania experiment was non-randomized.

The public-use release fails the mission's operational causal contract because the 17,513-row
records file has no persistent claimant ID. Claimant-level uniqueness, one assignment per claimant,
split disjointness, and claimant-level inference cannot be audited. The survey ID is not a records
join key, and survey sampling depended on post-treatment bonus receipt.

A second independent problem is that the records schema does not explicitly document a single
unit-level field for total UI benefits actually paid over the required outcome window. It documents
weeks paid, current benefit amounts, the latest payment, and remaining balance. Any total-dollar
reconstruction would require an economic-contract assumption that was not authorized before the
claimant-ID failure.

## Deliberately not performed

- no DEVELOPMENT or VALIDATION outcome-row access;
- no claimant split or preregistration;
- no timing feature allowlist used for modeling;
- no model tournament or policy selection;
- no freeze, dry run, reveal, consumed lock, ledger entry, or dashboard;
- no USD/DKK conversion;
- no V12 economic or personalization claim.

This is a data-contract stop, not a negative model result.
