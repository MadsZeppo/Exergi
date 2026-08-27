from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl


@dataclass(frozen=True)
class CriteoRandomizedDesign:
    assignment_column: str = "treatment"
    outcomes: tuple[str, ...] = ("conversion", "visit")
    exposure_column: str = "exposure"
    assignment: str = "RANDOMIZED_BINARY"
    estimand: str = "INTENTION_TO_TREAT"
    feature_semantics: str = "ANONYMIZED_RANDOM_PROJECTION; DO_NOT_INTERPRET"


class CriteoUpliftAdapter:
    feature_columns = tuple(f"f{index}" for index in range(12))
    required_columns = (*feature_columns, "treatment", "conversion", "visit", "exposure")
    expected_rows = 13_979_592
    expected_sha256 = "2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.design = CriteoRandomizedDesign()

    def sha256(self) -> str:
        digest = hashlib.sha256()
        with self.path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def scan(self) -> pl.LazyFrame:
        if not self.path.exists():
            raise FileNotFoundError(f"official Criteo uplift file not found: {self.path}")
        frame = pl.scan_csv(self.path, row_index_name="row_id")
        missing = set(self.required_columns) - set(frame.collect_schema().names())
        if missing:
            raise ValueError(f"Criteo uplift data is missing columns: {sorted(missing)}")
        return frame.select("row_id", *self.required_columns)

    @staticmethod
    def split(frame: pl.LazyFrame, split: str) -> pl.LazyFrame:
        """Stable pseudo-random 70/10/20 split, independent of outcomes and treatment."""
        bucket = pl.col("row_id").hash(seed=20260825).mod(100).alias("_split_bucket")
        with_bucket = frame.with_columns(bucket)
        if split == "train":
            return with_bucket.filter(pl.col("_split_bucket") < 70).drop("_split_bucket")
        if split == "development":
            return with_bucket.filter(pl.col("_split_bucket").is_between(70, 79)).drop(
                "_split_bucket"
            )
        if split == "test":
            return with_bucket.filter(pl.col("_split_bucket") >= 80).drop("_split_bucket")
        raise ValueError("split must be train, development, or test")

    def validate(self) -> dict[str, Any]:
        frame = self.scan()
        schema = frame.collect_schema()
        invalid_binary = (
            frame.select(
                [
                    (~pl.col(name).is_in([0, 1])).any().alias(name)
                    for name in ("treatment", "conversion", "visit", "exposure")
                ]
            )
            .collect()
            .row(0, named=True)
        )
        if any(invalid_binary.values()):
            raise ValueError(f"non-binary treatment/outcome fields: {invalid_binary}")
        summary = frame.select(
            pl.len().alias("rows"),
            pl.col("treatment").sum().alias("treated"),
            (1 - pl.col("treatment")).sum().alias("control"),
            pl.col("treatment").mean().alias("treatment_rate"),
            pl.col("conversion").mean().alias("conversion_rate"),
            pl.col("visit").mean().alias("visit_rate"),
            pl.col("exposure").mean().alias("exposure_rate"),
            pl.sum_horizontal(pl.all().null_count()).alias("missing_values"),
        ).collect()
        profile = summary.row(0, named=True)
        if profile["rows"] != self.expected_rows:
            raise ValueError(f"expected {self.expected_rows:,} rows, found {profile['rows']:,}")
        return {
            **profile,
            "columns": schema.names(),
            "features": list(self.feature_columns),
            "design": self.design.__dict__,
            "sha256": self.sha256(),
            "hash_matches_official": self.sha256() == self.expected_sha256,
            "exposure_feature_forbidden": True,
        }

    def prepare_parquet(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            self.scan().sink_parquet(target, compression="zstd")
        return target
