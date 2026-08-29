"""Integrity, hashing, and split controls for the V9 proof."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
RAW_ROOT = REPOSITORY / "data/raw/concealing_prices/osf"
STUDY1_RAW = RAW_ROOT / "Study 1/S1 Field Online Study.csv"
STUDY3_RAW = RAW_ROOT / "Study 3/S3 Email Field Study.csv"
ACQUISITION_MANIFEST = ROOT / "manifests/OSF_ACQUISITION_MANIFEST.json"
SPLIT_MANIFEST = ROOT / "manifests/V9_SPLIT_MANIFEST.json"
CONFIG = ROOT / "V9_ANALYSIS_CONFIG.json"
FREEZE_MANIFEST = ROOT / "V9_FREEZE_MANIFEST.json"
RESULTS = ROOT / "results"

EXPECTED_RAW_SHA256 = {
    "study1": "05a4238427bd61126c82428828365b7fe25602ec274b81ab83f8bb6978c9b815",
    "study3": "69736e1325c9427045c788c510511ad7d7a8b081fc8bc914aad0940be8a9494d",
}
SPLIT_SEED = "exergi-v9-concealing-prices-split-v1"


class IntegrityError(RuntimeError):
    """Raised when the V9 proof must fail closed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def stable_unit_hash(study: str, raw_id: str) -> str:
    payload = f"{SPLIT_SEED}|{study}|{raw_id}".encode()
    return hashlib.sha256(payload).hexdigest()


def study3_split(unit_hash: str) -> str:
    bucket = int(unit_hash[:15], 16) / float(16**15)
    if bucket < 0.50:
        return "DEVELOPMENT"
    if bucket < 0.75:
        return "VALIDATION"
    return "SEALED_TEST"


def study1_split(date_rank: int) -> str:
    # Exactly one chronological choice, frozen before outcome access.
    return "DEVELOPMENT" if date_rank < 28 else "VALIDATION"


def selected_csv_columns(path: Path, allowed: set[str]) -> Iterator[dict[str, str]]:
    """Yield only explicitly allowed assignment/identifier columns."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not allowed.issubset(reader.fieldnames):
            raise IntegrityError(f"required columns missing from {path.name}")
        for row in reader:
            yield {name: row[name] for name in allowed}


def verify_raw_hashes() -> dict[str, str]:
    observed = {"study1": sha256_file(STUDY1_RAW), "study3": sha256_file(STUDY3_RAW)}
    if observed != EXPECTED_RAW_SHA256:
        raise IntegrityError(f"raw checksum mismatch: {observed}")
    return observed


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def assert_split_integrity() -> dict[str, Any]:
    verify_raw_hashes()
    manifest = load_json(SPLIT_MANIFEST)
    if manifest["split_seed"] != SPLIT_SEED:
        raise IntegrityError("split seed mutation")
    if manifest["raw_sha256"] != EXPECTED_RAW_SHA256:
        raise IntegrityError("split/raw hash mismatch")
    if manifest["study1"]["date_overlap_count"] != 0:
        raise IntegrityError("Study 1 date overlap")
    if manifest["study3"]["hashed_id_overlap_count"] != 0:
        raise IntegrityError("Study 3 recipient overlap")
    return manifest
