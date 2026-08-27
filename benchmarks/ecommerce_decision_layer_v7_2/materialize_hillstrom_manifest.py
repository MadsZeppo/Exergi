"""Create the Hillstrom split manifest without loading any outcome column."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from decision_engine.economic_policy_v72.splits import (
    build_split_manifest,
    write_manifest_immutable,
)

ROOT = Path(__file__).resolve().parent


def materialize(source_commit: str, source_tree_sha256: str) -> Path:
    source = Path("data/raw/hillstrom/hillstrom.csv")
    units: list[str] = []
    treatments: list[str] = []
    with source.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "segment" not in reader.fieldnames:
            raise ValueError("Hillstrom source is missing the randomized segment column")
        for index, row in enumerate(reader):
            units.append(f"row-{index}")
            treatments.append(row["segment"])
    manifest = build_split_manifest(
        dataset="hillstrom",
        dataset_path=source,
        unit_ids=units,
        treatments=treatments,
        split_seed=72_2001,
        source_commit=source_commit,
        source_tree_sha256=source_tree_sha256,
    )
    destination = ROOT / "manifests" / "hillstrom_split_manifest.json"
    write_manifest_immutable(manifest, destination)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree-sha256", required=True)
    arguments = parser.parse_args()
    print(materialize(arguments.source_commit, arguments.source_tree_sha256))
