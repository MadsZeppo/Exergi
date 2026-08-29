# V9 dataset provenance report

## Official source

- OSF node: <https://osf.io/xt42w>
- Project: *Data and Analyses of paper: Affonso et al. (2025), “Concealing
  Prices: How Delayed Price Disclosure Influences Consumer Purchase Decisions,” Journal of
  Consumer Research*
- DOI: <https://doi.org/10.1093/jcr/ucaf051>
- Scope acquired: every file in the official OSF Study 1 and Study 3 folders (40 files;
  13,264,688 bytes)
- Acquisition timestamp: `2026-08-29T15:31:47.768028+00:00`
- Storage: ignored `data/raw/concealing_prices/osf/`, filesystem mode `0444`
- Manifest: `manifests/OSF_ACQUISITION_MANIFEST.json`
- License: the public OSF node states no explicit node license. Public readability is recorded;
  no open or commercial reuse license is inferred.

Every official file was downloaded from its OSF file endpoint and verified against the OSF API
SHA-256 checksum and byte size. The two field-data hashes used by V9 are:

| Study | Official field file | SHA-256 | Bytes |
|---|---|---|---:|
| Study 1 | `S1 Field Online Study.csv` | `05a4238427bd61126c82428828365b7fe25602ec274b81ab83f8bb6978c9b815` | 3,536 |
| Study 3 | `S3 Email Field Study.csv` | `69736e1325c9427045c788c510511ad7d7a8b081fc8bc914aad0940be8a9494d` | 11,619,692 |

## Documents audited

The official field codebooks, the R scripts, the Stata scripts, all filenames, and raw CSV
headers were inspected read-only. The paper was audited from the author-hosted final draft
`PD-Draft-Final.pdf` (SHA-256
`d4701783bc289710ed59494ceb4dfb7a020c57669ea4ec474ab170efcaa46572`).

The OSF node contains no README and no field-study preregistration artifact for Study 1 or
Study 3. The paper describes preregistrations for its laboratory studies, not these field
experiments. The web appendix is referenced by the paper but is not present in the public OSF
folders, and the Oxford Academic supplement is subscriber-restricted. This is recorded as a
documentation availability limitation. It is not essential to the V9 estimands because the
paper, official codebooks, official raw field files, and matching official R/Stata scripts jointly
document assignment, arms, field units, and monetary outcomes.

## Paper/code/data agreement

- Study 1: 112 observations, exactly two arms on each of 56 `date_id` blocks. The official
  scripts use date fixed effects and identify arm 0 as Immediate-PD and arm 1 as Delayed-PD.
- Study 3: 771,583 observations with a unique recipient `user_id`. The official scripts identify
  arm 0 as immediate-PD and arm 1 as delayed-PD and construct purchase/log outcomes from raw
  `units_sold` and `revenues`.
- Field CSV headers exactly match the field codebooks and scripts.

Published aggregate treatment estimates are audit context only. V9 policy selection uses only
its frozen DEVELOPMENT splits and symmetric preregistered rules.
