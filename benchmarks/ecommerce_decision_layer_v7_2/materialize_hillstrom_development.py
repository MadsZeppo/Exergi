"""Materialize only Hillstrom DEVELOPMENT rows without parsing held-out outcome rows."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from decision_engine.economic_policy_v72.splits import stable_unit_hash

ROOT = Path(__file__).resolve().parent
SOURCE = Path("data/raw/hillstrom/hillstrom.csv")
MANIFEST = ROOT / "manifests/hillstrom_split_manifest.json"
DESTINATION = Path("data/processed/hillstrom/v7_2/development.parquet")
EXPECTED_COLUMNS = (
    "recency",
    "history_segment",
    "history",
    "mens",
    "womens",
    "zip_code",
    "newbie",
    "channel",
    "segment",
    "visit",
    "conversion",
    "spend",
)


def parse_development_lines(
    lines: Iterable[bytes], development_hashes: set[str]
) -> list[dict[str, str]]:
    iterator = iter(lines)
    header_bytes = next(iterator)
    header = next(csv.reader([header_bytes.decode("utf-8")]))
    if tuple(header) != EXPECTED_COLUMNS:
        raise ValueError("unexpected Hillstrom schema")
    records: list[dict[str, str]] = []
    for row_id, raw_line in enumerate(iterator):
        unit_hash = stable_unit_hash("hillstrom", f"row-{row_id}")
        if unit_hash not in development_hashes:
            continue
        values = next(csv.reader(io.StringIO(raw_line.decode("utf-8"))))
        if len(values) != len(header):
            raise ValueError(f"malformed Hillstrom development row: {row_id}")
        record = dict(zip(header, values, strict=True))
        record["unit_hash"] = unit_hash
        records.append(record)
    return records


def materialize() -> Path:
    manifest = json.loads(MANIFEST.read_text())
    development_hashes = set(manifest["unit_hashes"]["DEVELOPMENT"])
    with SOURCE.open("rb") as handle:
        records = parse_development_lines(handle, development_hashes)
    frame = pd.DataFrame.from_records(records)
    if len(frame) != manifest["row_counts"]["DEVELOPMENT"]:
        raise RuntimeError("Hillstrom development count differs from immutable manifest")
    numeric = ("recency", "history", "mens", "womens", "newbie", "visit", "conversion", "spend")
    frame[list(numeric)] = frame[list(numeric)].apply(pd.to_numeric, errors="raise")
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(DESTINATION, index=False)
    return DESTINATION


if __name__ == "__main__":
    print(materialize())
