# V10 MT-LIFT dataset provenance

Status: `OFFICIAL_SOURCE_VERIFIED_DATASET_NOT_ACQUIRED`

## Publisher-controlled source

- Official repository: <https://github.com/MTDJDSP/MT-LIFT>
- Repository commit audited: `379b315dc0fcd7e9dedece720477f38823cc4fdc`
- Commit timestamp: `2024-05-20T09:45:21Z`
- Publisher account: `MTDJDSP`
- Paper: Huang et al. (2024), *Entire Chain Uplift Modeling with Context-Enhanced
  Learning for Intelligent Marketing*, DOI `10.1145/3589335.3648320`,
  <https://arxiv.org/abs/2402.03379>
- Explicit repository license: none found. No open-source or commercial-use right is inferred.

The official README at the pinned commit was stored read-only under ignored raw storage. Its
SHA-256 is `1598c913bb2e715c384141ad716794d2c827356b492213bb864369419d5f8ca6`
(3,766 bytes). The official arXiv v1 PDF was stored read-only with SHA-256
`36e0024ebc976c53ab33ac058963581545b13d489cc3ec0ba9d28453fca4abe7`
(1,413,976 bytes).

## Dataset access result

Only links published in the official README were tried.

| Publisher link | Reproducible result |
|---|---|
| Google Drive | Direct download and `gdown` could not resolve a public file; both shell and browser checks reached Google sign-in rather than a dataset payload. |
| Baidu Drive | The publisher URL returned `errno = -7`, with expired/missing-link markers. |

The HTML returned by Google is not the dataset and is never treated as raw evidence. No
`train.csv`, `test.csv`, archive, dataset checksum, or dataset byte count was obtained. The
repository has open issues reporting the same access problems, and no publisher response or
replacement mirror was present at audit time. Unofficial mirrors were deliberately not used.

Raw storage remains covered by the repository's `data/` gitignore rule. Retrieved references
and access-response evidence are read-only (`0444`). Detailed URLs, times, sizes, and hashes are
in `manifests/V10_SOURCE_MANIFEST.json`.

## Provenance conclusion

The source identity is publisher-controlled, so this is not a source-substitution failure.
However, the official dataset itself was unavailable. Its bytes, schema, row count, and
immutability therefore cannot be verified. V10 cannot progress to outcome analysis.
