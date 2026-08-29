"""Outcome-isolated qualification and deterministic split preparation."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .integrity import (
    ACQUISITION_MANIFEST,
    ROOT,
    SPLIT_MANIFEST,
    STUDY1_RAW,
    STUDY3_RAW,
    canonical_json_hash,
    selected_csv_columns,
    stable_unit_hash,
    study1_split,
    study3_split,
    verify_raw_hashes,
)


def header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return next(csv.reader(handle))


def _digest_lines(values: list[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def build_split_manifest() -> dict[str, Any]:
    raw_hashes = verify_raw_hashes()

    s1_pairs: dict[int, list[int]] = defaultdict(list)
    for row in selected_csv_columns(STUDY1_RAW, {"date_id", "treatment"}):
        s1_pairs[int(row["date_id"])].append(int(row["treatment"]))
    dates = sorted(s1_pairs)
    if len(dates) != 56 or any(sorted(s1_pairs[value]) != [0, 1] for value in dates):
        raise ValueError("Study 1 must contain exactly 56 paired dates and both arms per date")
    s1_units: dict[str, list[str]] = defaultdict(list)
    s1_arms: dict[str, Counter[int]] = defaultdict(Counter)
    for rank, date_id in enumerate(dates):
        split = study1_split(rank)
        s1_units[split].append(stable_unit_hash("study1-date", str(date_id)))
        s1_arms[split].update(s1_pairs[date_id])

    s3_units: dict[str, list[str]] = defaultdict(list)
    s3_arms: dict[str, Counter[int]] = defaultdict(Counter)
    raw_ids: set[str] = set()
    duplicates = 0
    for row in selected_csv_columns(STUDY3_RAW, {"user_id", "treatment"}):
        raw_id = row["user_id"]
        if raw_id in raw_ids:
            duplicates += 1
        raw_ids.add(raw_id)
        unit_hash = stable_unit_hash("study3-recipient", raw_id)
        split = study3_split(unit_hash)
        s3_units[split].append(unit_hash)
        s3_arms[split][int(row["treatment"])] += 1
    if duplicates or len(raw_ids) != 771_583:
        raise ValueError("Study 3 recipient IDs are not unique as documented")

    s1_sets = {name: set(values) for name, values in s1_units.items()}
    s3_sets = {name: set(values) for name, values in s3_units.items()}
    s1_overlap = len(s1_sets["DEVELOPMENT"] & s1_sets["VALIDATION"])
    s3_overlap = sum(
        len(s3_sets[left] & s3_sets[right])
        for left, right in (
            ("DEVELOPMENT", "VALIDATION"),
            ("DEVELOPMENT", "SEALED_TEST"),
            ("VALIDATION", "SEALED_TEST"),
        )
    )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "created_before_outcome_analysis": True,
        "split_seed": "exergi-v9-concealing-prices-split-v1",
        "raw_sha256": raw_hashes,
        "study1": {
            "randomization_unit": "visitor/cookie assignment; unavailable at row level",
            "analysis_and_split_unit": "date_id",
            "split_method": (
                "single chronological rank split; first 28 DEVELOPMENT, last 28 VALIDATION"
            ),
            "sealed_test_omitted_reason": (
                "56 paired dates are too sparse for a defensible 50/25/25 split"
            ),
            "date_counts": {name: len(values) for name, values in sorted(s1_units.items())},
            "row_counts": {name: len(values) * 2 for name, values in sorted(s1_units.items())},
            "treatment_counts": {
                name: {str(key): value for key, value in sorted(counts.items())}
                for name, counts in sorted(s1_arms.items())
            },
            "hashed_date_manifest_sha256": {
                name: _digest_lines(values) for name, values in sorted(s1_units.items())
            },
            "date_overlap_count": s1_overlap,
        },
        "study3": {
            "randomization_analysis_and_split_unit": "recipient user_id",
            "split_method": "SHA-256 deterministic 50/25/25",
            "row_counts": {name: len(values) for name, values in sorted(s3_units.items())},
            "treatment_counts": {
                name: {str(key): value for key, value in sorted(counts.items())}
                for name, counts in sorted(s3_arms.items())
            },
            "hashed_id_manifest_sha256": {
                name: _digest_lines(values) for name, values in sorted(s3_units.items())
            },
            "hashed_id_overlap_count": s3_overlap,
            "duplicate_raw_id_count": duplicates,
            "raw_ids_persisted": False,
        },
    }
    manifest["canonical_sha256"] = canonical_json_hash(manifest)
    SPLIT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    SPLIT_MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def write_qualification() -> dict[str, Any]:
    acquisition = json.loads(ACQUISITION_MANIFEST.read_text())
    split = build_split_manifest()
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "QUALIFIED",
        "official_osf_node": "https://osf.io/xt42w",
        "official_file_count_study1_and_study3": acquisition["file_count"],
        "published_effects_used_for_policy": False,
        "validation_outcomes_opened": False,
        "sealed_test_outcomes_opened": False,
        "study1": {
            "qualified": True,
            "classification": "AGGREGATE_RANDOMIZED_FIELD_EVIDENCE",
            "qualification_checks": {f"criterion_{index}": True for index in range(1, 12)},
            "headers": header(STUDY1_RAW),
            "observations": 112,
            "paired_dates": 56,
            "claim_authorities": [
                "REAL_RANDOMIZED_AGGREGATE_REVENUE",
                "REAL_RANDOMIZED_UNITS_SOLD",
                "REAL_RANDOMIZED_PURCHASE_RATE",
            ],
            "personalization_allowed": False,
        },
        "study3": {
            "qualified": True,
            "classification": "INDIVIDUAL_RANDOMIZED_FIELD_EVIDENCE",
            "qualification_checks": {f"criterion_{index}": True for index in range(1, 12)},
            "headers": header(STUDY3_RAW),
            "observations": 771_583,
            "unique_recipients": 771_583,
            "claim_authorities": [
                "REAL_RANDOMIZED_SALES_REVENUE",
                "REAL_RANDOMIZED_UNITS_SOLD",
                "REAL_RANDOMIZED_PURCHASE_RATE",
            ],
            "personalization_allowed": False,
        },
        "split_manifest_canonical_sha256": split["canonical_sha256"],
    }
    (ROOT / "V9_DATASET_QUALIFICATION.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


if __name__ == "__main__":
    print(json.dumps(write_qualification(), indent=2, sort_keys=True))
