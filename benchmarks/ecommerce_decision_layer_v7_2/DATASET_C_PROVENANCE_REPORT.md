# Dataset C Provenance Report

Status: **DATASET_C_NOT_FOUND**.

The best candidate archive was downloaded from Zenodo record 13993677 on 2026-08-28.

- filename: `replication_package.zip`
- size: approximately 195 KiB
- MD5: `52427d22601dd2c29498b6eb2b6772c4` (matches Zenodo)
- SHA-256: `cdd3e3037b7906abb905ad1e10465488d378d0cd648957d819fd34bb588ec768`
- license/use: dataset is publicly open on Zenodo; exact file-level license remains governed by the
  record metadata

The archive contains code, README and `data/survey.csv`. Its own `Cleaning.do` requires
`data/analytics.csv`; `Merge.do` additionally requires `data/product.csv`. Neither is in the archive.
The available survey has 7 columns and is not the row-level transaction/purchase dataset used by the
paper's purchase and quantity analyses. Assignment, monetary outcome, sample support and propensity
therefore cannot be verified mechanically.

Dominick's oatmeal has SHA-256 checksums recorded locally, but the category movement data do not
contain the experimental assignment schedule. Treating observed price variation as randomized would
violate the mission. It is retained as historical scanner data, not Dataset C proof.
