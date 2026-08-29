# V8 Pre-Reveal Integrity Audit

Status: **PASS — VALIDATION NOT OPENED**.

- Repository base checkpoint `0a089ff1b1a73ba4cf6a1fd96c44a879f53aec3b` is an ancestor.
- Raw Hillstrom SHA-256 is `27bab8c5d3669f26ec08ebb50a0a78317542f29501156f2e2af6781fab4cd7e2`.
- Existing split-manifest SHA-256 is
  `ee3b2050b532c65c323870f8d54ecb8240981f87936ed7ec2c8045960e1e1d0f`.
- Existing row counts are DEVELOPMENT 32,233, VALIDATION 15,928 and SEALED_TEST 15,839.
- The three highest-randomized-unit hash sets are disjoint.
- The validation hashed-ID manifest is unchanged.
- Only `data/processed/hillstrom/v7_2/development.parquet` exists; there is no validation or sealed
  materialization.
- No V8 reveal-start, validation-result or consumed lock existed during the audit.
- Historical row-0 remains in SEALED_TEST only and is explicitly quarantined. SEALED_TEST is not
  fully untouched and cannot be final authority.
- Buy Baits development lock SHA-256 remains
  `0e55fef69dfb9aa740e78f3f423c6adf686a024c6e0564337890e5449f4a44a0`.
- The unrelated untracked product-status Markdown file was preserved and is outside V8.

The V7/V7.1/V7.2/V7.3 artifacts were not modified. This audit used metadata, hashes, the already
consumed DEVELOPMENT materialization, and treatment-only manifest counts. It did not parse Hillstrom
VALIDATION or SEALED_TEST outcomes.
