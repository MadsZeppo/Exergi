# V13 JTPA dataset provenance

Status: `OFFICIAL_SOURCE_ACQUIRED_AND_VERIFIED`

## Official source

- Publisher: W.E. Upjohn Institute for Employment Research
- Dataset page: <https://www.upjohn.org/data-tools/employment-research-data-center/national-jtpa-study>
- Publisher ZIP: <https://www.upjohn.org/sites/default/files/2019-02/jtpa_national_evaluation.zip>
- Downloaded: `2026-08-30T11:10:48Z`
- Bytes: `127,676,441`
- SHA-256: `3607617e265ec3eac11436f3f19a25e43e3ecf53ba6de6b98a9dede53cc3a76b`
- HTTP identity: `application/zip`, ETag `618df9ba-79c3019`, last modified
  `Fri, 12 Nov 2021 05:20:58 GMT`
- Archive: 388 entries, 134,935,786 uncompressed bytes, CRC PASS
- Storage: ignored `data/raw/jtpa/`; original ZIP mode `0444`

The source identifies itself as the National JTPA Study Public Use Data CD. The archive includes the
experimental Background Information Form, follow-up and administrative records, official codebooks,
the March 2003 public-use documentation addendum, April 2004 replacement files, and the 1994 final
report. Staging is ignored and derived from the immutable ZIP.

## License and privacy authority

The Upjohn page offers the package for public download and the package labels itself public use. No
explicit reuse-license text was found, so this checkpoint does not infer one. The official documentation
says identifying information is omitted. `RECID` is a six-character public-use join key; released name,
SSN and contact fields are not policy inputs and are marked forbidden even where empty.

## Outcome-isolation boundary

Qualification read official documentation, baseline values, assignment, and only `RECID` membership
from outcome-bearing files. No monthly earnings value, treatment-effect contrast, model, threshold or
policy value was opened or calculated. Published effects in the final report were not used for model
selection or gates.

Full hashes are recorded in `manifests/V13_SOURCE_MANIFEST.json`.
