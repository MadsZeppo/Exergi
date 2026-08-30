# V12 Pennsylvania Reemployment Bonus dataset provenance

Status: `OFFICIAL_SOURCE_ACQUIRED_AND_VERIFIED`

## Official source

- Publisher: W.E. Upjohn Institute for Employment Research
- Dataset page: <https://www.upjohn.org/data-tools/employment-research-data-center/pennsylvania-reemployment-bonus-demonstration>
- Publisher ZIP: <https://www.upjohn.org/sites/default/files/2019-02/PA_ReempBonus.zip>
- Downloaded: `2026-08-30T10:47:35.615881+00:00`
- Bytes: `38,555,725`
- SHA-256: `9036c9a82a5ab69b580b6646a3749019924442b7c6d10e4224ab0b910a95ef53`
- Archive entries: 19; CRC verification: PASS
- Storage: ignored `data/raw/penn_bonus/`, original ZIP mode `0444`
- Explicit license: none found. The publisher disclaimer is not interpreted as a reuse license.

The archive contains the documented records file (17,513 observations, 189 columns), survey file
(5,678 observations, 641 columns), Stata/SAS/text variants, file contents, variable means, public-use
documentation, executive summary, and final report. Extraction was performed without modifying the
ZIP, and extracted staging files were made read-only.

## Documentation identity finding

The Pennsylvania final report inside the official ZIP is the authoritative report for V12:

- `cd/reports/Final_report.pdf`
- SHA-256 `14ad487814dd70ceecd0e085c87a2ff573c497b2818b59bd8a9ce23b505ff943`
- 274 pages

The separate Upjohn URL named `prbdreport.pdf` unexpectedly serves *The Washington Reemployment
Bonus Experiment Final Report* (369 pages; SHA-256
`a1f8aec0785128154c1cc357a7b921dea9fc6d288f2f08f96a43f70ac4dc5889`). It was excluded from
Pennsylvania evidence. This is a publisher-link identity mismatch, not a raw ZIP mismatch.

## Outcome-isolation boundary

Before qualification, inspection was limited to archive/file metadata, column headers, official
documentation, treatment and identifier schema, and line counts. No records or survey data row was
printed or analyzed. Published aggregate results in the required documentation were not used as V12
outcomes or for policy selection.

Full hashes and access metadata are in `manifests/V12_SOURCE_MANIFEST.json`.
