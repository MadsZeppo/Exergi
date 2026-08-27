"""M5 adapter. Downloading is intentionally separate because dataset terms may change."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from decision_engine.datasets.base import DatasetMetadata, DecisionDataset


class M5Dataset(DecisionDataset):
    metadata = DatasetMetadata("m5", "accuracy-v1", randomized=False)

    def __init__(self, raw_dir: str | Path) -> None:
        self.raw_dir = Path(raw_dir)

    def load(self) -> pl.DataFrame:
        sales_path = self.raw_dir / "sales_train_validation.csv"
        calendar_path = self.raw_dir / "calendar.csv"
        prices_path = self.raw_dir / "sell_prices.csv"
        missing = [str(p) for p in (sales_path, calendar_path, prices_path) if not p.exists()]
        if missing:
            raise FileNotFoundError(
                "M5 files are not bundled. Download the official M5 Forecasting Accuracy files "
                f"and place them in {self.raw_dir}. Missing: {missing}"
            )
        sales = pl.read_csv(sales_path)
        id_columns = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]
        long = sales.unpivot(index=id_columns, variable_name="d", value_name="outcome")
        calendar = pl.read_csv(calendar_path, try_parse_dates=True)
        frame = long.join(calendar.select("d", "date", "wm_yr_wk"), on="d", how="left")
        prices = pl.read_csv(prices_path)
        frame = frame.join(prices, on=["store_id", "item_id", "wm_yr_wk"], how="left")
        frame = frame.with_columns(
            pl.col("date").cast(pl.Datetime).alias("timestamp"),
            pl.col("id").alias("entity_id"),
            pl.col("cat_id").alias("group_id"),
            pl.lit("observed_sales").alias("action"),
            pl.col("date").cast(pl.Datetime).alias("observed_at"),
            pl.col("date").cast(pl.Datetime).alias("effective_at"),
            pl.col("sell_price").alias("price"),
        )
        self.validate(frame)
        return frame
