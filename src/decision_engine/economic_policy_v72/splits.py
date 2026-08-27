"""Immutable split manifests and one-time sealed-test access guards."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

SPLITS = ("DEVELOPMENT", "VALIDATION", "SEALED_TEST")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_unit_hash(dataset: str, unit_id: str) -> str:
    return hashlib.sha256(f"{dataset}\0{unit_id}".encode()).hexdigest()


def assigned_split(dataset: str, unit_id: str, seed: int) -> str:
    digest = hashlib.sha256(f"{seed}\0{dataset}\0{unit_id}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") / 2**64
    if bucket < 0.50:
        return "DEVELOPMENT"
    if bucket < 0.75:
        return "VALIDATION"
    return "SEALED_TEST"


@dataclass(frozen=True)
class DatasetSplitManifest:
    schema_version: int
    dataset: str
    dataset_sha256: str
    split_seed: int
    split_algorithm: str
    source_commit: str
    source_tree_sha256: str
    created_at_utc: str
    unit_hashes: Mapping[str, tuple[str, ...]]
    row_counts: Mapping[str, int]
    treatment_counts: Mapping[str, Mapping[str, int]]
    outcomes_mature: Mapping[str, bool]

    @property
    def manifest_sha256(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


def build_split_manifest(
    *,
    dataset: str,
    dataset_path: Path,
    unit_ids: Sequence[str],
    treatments: Sequence[str],
    split_seed: int,
    source_commit: str,
    source_tree_sha256: str,
    outcomes_mature: bool = True,
) -> DatasetSplitManifest:
    if len(unit_ids) != len(treatments) or len(set(unit_ids)) != len(unit_ids):
        raise ValueError("split units and treatments must align and units must be unique")
    unit_hashes: dict[str, list[str]] = {split: [] for split in SPLITS}
    treatment_counts: dict[str, dict[str, int]] = {split: {} for split in SPLITS}
    for unit_id, treatment in zip(unit_ids, treatments, strict=True):
        split = assigned_split(dataset, unit_id, split_seed)
        unit_hashes[split].append(stable_unit_hash(dataset, unit_id))
        treatment_counts[split][treatment] = treatment_counts[split].get(treatment, 0) + 1
    if set.intersection(*(set(unit_hashes[split]) for split in SPLITS)):
        raise RuntimeError("randomized unit leaked across immutable splits")
    return DatasetSplitManifest(
        1,
        dataset,
        sha256_file(dataset_path),
        split_seed,
        "sha256(seed\\0dataset\\0highest_randomized_unit); buckets 50/25/25",
        source_commit,
        source_tree_sha256,
        datetime.now(UTC).isoformat(),
        {split: tuple(sorted(unit_hashes[split])) for split in SPLITS},
        {split: len(unit_hashes[split]) for split in SPLITS},
        treatment_counts,
        {split: outcomes_mature for split in SPLITS},
    )


def write_manifest_immutable(manifest: DatasetSplitManifest, path: Path) -> None:
    payload = json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text() != payload:
        raise RuntimeError(f"immutable manifest changed: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)


@dataclass(frozen=True)
class FreezeManifest:
    source_sha256: str
    dependency_sha256: str
    dataset_manifest_sha256: str
    model_sha256: str
    threshold_sha256: str
    sequential_passed: bool
    validation_passed: bool
    qualified_datasets: int

    @property
    def freeze_sha256(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


class SealedTestGuard:
    """Fail-closed one-time gate. It never reads outcomes itself."""

    def __init__(self, lock_dir: Path) -> None:
        self.lock_dir = lock_dir

    def authorize_once(self, freeze: FreezeManifest, current: FreezeManifest) -> str:
        if freeze != current:
            raise PermissionError("source, dependency, dataset, model or thresholds changed")
        if not freeze.sequential_passed or not freeze.validation_passed:
            raise PermissionError("sequential and validation gates must pass before reveal")
        if freeze.qualified_datasets < 3:
            raise PermissionError("three qualified datasets are required before sealed reveal")
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        marker = self.lock_dir / "SEALED_TEST_CONSUMED.json"
        payload = json.dumps(
            {
                "freeze_sha256": freeze.freeze_sha256,
                "consumed_at_utc": datetime.now(UTC).isoformat(),
            },
            sort_keys=True,
        ) + "\n"
        try:
            descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        except FileExistsError as error:
            raise PermissionError("sealed test was already consumed") from error
        with os.fdopen(descriptor, "w") as handle:
            handle.write(payload)
        return freeze.freeze_sha256
