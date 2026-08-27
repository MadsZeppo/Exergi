from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl


@dataclass(frozen=True)
class MTLiftDesign:
    treatment_column: str = "treatment"
    outcome_columns: tuple[str, ...] = ("click", "conversion")
    treatment_values: tuple[int, ...] = (0, 1, 2, 3, 4)
    assignment: str = "RANDOMIZED_MULTI_ARM"
    feature_semantics: str = "ANONYMIZED; DO NOT INTERPRET"


class MTLiftAdapter:
    """Strict adapter for the publisher-provided MT-LIFT train/test files."""

    feature_columns = tuple(f"f{index}" for index in range(99))
    required_columns = (*feature_columns, "click", "conversion", "treatment")

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.design = MTLiftDesign()

    def available(self) -> bool:
        return all((self.root / name).exists() for name in ("train.csv", "test.csv"))

    def load_split(self, split: str) -> pl.LazyFrame:
        if split not in {"train", "test"}:
            raise ValueError("split must be train or test")
        path = self.root / f"{split}.csv"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} is absent; obtain MT-LIFT from its publisher under applicable terms"
            )
        frame = pl.scan_csv(path)
        missing = set(self.required_columns) - set(frame.collect_schema().names())
        if missing:
            raise ValueError(f"MT-LIFT is missing required columns: {sorted(missing)}")
        return frame.select(self.required_columns)

    def validate(self, split: str) -> dict[str, object]:
        frame = self.load_split(split)
        summary = frame.select(
            pl.len().alias("rows"),
            pl.col("treatment").n_unique().alias("treatment_arms"),
            pl.col("click").mean().alias("click_rate"),
            pl.col("conversion").mean().alias("conversion_rate"),
        ).collect()
        treatments = sorted(frame.select("treatment").unique().collect()["treatment"].to_list())
        if not set(treatments).issubset(self.design.treatment_values):
            raise ValueError(f"unexpected MT-LIFT treatment labels: {treatments}")
        return {**summary.row(0, named=True), "treatments": treatments, "split": split}
