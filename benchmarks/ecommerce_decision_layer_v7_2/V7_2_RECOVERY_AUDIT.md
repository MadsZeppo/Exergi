# V7.2 Economic Proof recovery audit

Audit date: 2026-08-28 (Europe/Copenhagen), before V7.2 data acquisition, model development,
validation or sealed-test access.

## Repository state

- Current HEAD and `origin/main`: `2b7f6f895a335ac93e7d32d42cbfe841202c550e`.
- Historical backend implementation: `1b4d880`; V7.1 development source:
  `1ef3bd5d805ddf3d62422cca78918de8d8ebec93`.
- V7 and V7.1 remain immutable historical FAILs. No V7.1 R/S/T outcome or Pack U was opened.
- Existing dirty files are unrelated frontend work: `home.tsx`, `package.json`, and
  `package-lock.json`. V7.2 will not modify, stash, stage or commit them.
- `benchmarks/*` is ignored except explicitly unignored V7/V7.1 namespaces. V7.2 needs a narrow
  unignore rule; raw/processed data remain ignored.
- No repository-root `AGENTS.md` exists. AGENTS files found by search belong to sibling projects or
  dependencies and do not govern this repository.

## Reusable implementation

- V7.1 provides the documented sequential failure fixtures, committed-risk ledger, oracle
  quarantine, disjoint-pack patterns, source/dependency freeze patterns and win-back pilot contracts.
- Existing Hillstrom adapter loads all three randomized arms with pretreatment features.
- Existing Dominick's adapter/data provide store-week revenue/profit fields, but treatment assignment
  and experiment windows still require mechanical verification before Dataset C can qualify.
- Existing Criteo, Open Bandit and X5 adapters remain useful negative authority controls but cannot
  count as V7.2 monetary randomized proof under the frozen mission.

## Dataset recovery status

- **Hillstrom:** local raw file exists; randomized revenue authority is established by the dataset
  documentation. No COGS or observed contribution-profit components exist.
- **Buy Baits:** not present locally at audit time. Official OpenICPSR V1 lists a 36.6 MB
  `data/data.dta` plus code/README. Acquisition, checksum, license, schema and replication audit are
  mandatory before it can qualify.
- **Dataset C:** not selected. Local Dominick's oatmeal files are a candidate only. The official
  Kilts page says randomized experiments occurred across categories and movement files contain weekly
  sales and profit margin, but the local files alone do not yet identify assignment or propensity.
  Zenodo 13993677 is also only a candidate until row-level monetary outcomes and assignment are
  audited.

## Leakage and sealing status

- No V7.2 dataset split, manifest, validation result, source freeze or sealed-test lock exists.
- No V7.2 outcomes have been used for development.
- V7.2 must materialize encrypted/separate outcome files and make ordinary development/validation
  commands structurally unable to load sealed-test outcomes.
- Pack N, V7.1 R/S/T and U are prohibited inputs.

## Recovery conclusion

V7.2 starts as **THREE-DATASET ECONOMIC PROOF: INCOMPLETE**. The immediate blockers are official
Buy Baits acquisition/audit and identification of a third independent randomized monetary dataset.
No real-data model selection or sealed-test work is authorized until dataset authority and new
preregistered sequential gates are complete. Generic engine implementation and synthetic unit tests
may proceed without consuming any real-data split.
