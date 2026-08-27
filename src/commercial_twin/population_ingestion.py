from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import polars as pl

from commercial_twin.population_contracts import FieldStatus

CANONICAL_COLUMNS = (
    "event_time",
    "customer_id",
    "session_id",
    "event_type",
    "product_id",
    "category_id",
    "brand",
    "price",
    "quantity",
    "discount",
    "order_id",
    "channel",
    "return_flag",
    "geography",
)


class Rees46EventAdapter:
    source = "REES46_OPEN_CDP_ELECTRONICS"

    @staticmethod
    def field_status() -> dict[str, FieldStatus]:
        observed = {
            "event_time",
            "customer_id",
            "session_id",
            "event_type",
            "product_id",
            "category_id",
            "brand",
            "price",
        }
        return {
            name: FieldStatus.OBSERVED if name in observed else FieldStatus.NOT_AVAILABLE
            for name in CANONICAL_COLUMNS
        }

    @staticmethod
    def map_frame(frame: pl.DataFrame) -> pl.DataFrame:
        required = {
            "event_time",
            "event_type",
            "product_id",
            "category_id",
            "brand",
            "price",
            "user_id",
            "user_session",
        }
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"REES46 fields missing: {sorted(missing)}")
        return frame.select(
            pl.col("event_time")
            .str.strptime(pl.Datetime(time_zone="UTC"), "%Y-%m-%d %H:%M:%S UTC")
            .alias("event_time"),
            pl.col("user_id").cast(pl.String).alias("customer_id"),
            pl.col("user_session").cast(pl.String).alias("session_id"),
            pl.col("event_type").cast(pl.String),
            pl.col("product_id").cast(pl.String),
            pl.col("category_id").cast(pl.String),
            pl.col("brand").cast(pl.String),
            pl.col("price").cast(pl.Float64),
            pl.lit(None, dtype=pl.Float64).alias("quantity"),
            pl.lit(None, dtype=pl.Float64).alias("discount"),
            pl.lit(None, dtype=pl.String).alias("order_id"),
            pl.lit(None, dtype=pl.String).alias("channel"),
            pl.lit(None, dtype=pl.Boolean).alias("return_flag"),
            pl.lit(None, dtype=pl.String).alias("geography"),
        )

    @classmethod
    def read(cls, path: Path) -> pl.DataFrame:
        return cls.map_frame(pl.read_csv(path))

    @classmethod
    def iter_chunks(cls, path: Path, *, batch_size: int = 100_000) -> Iterator[pl.DataFrame]:
        reader = pl.read_csv_batched(path, batch_size=batch_size)
        while batches := reader.next_batches(1):
            yield cls.map_frame(batches[0])


def write_canonical_parquet(source: Path, destination: Path) -> dict[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    frames = list(Rees46EventAdapter.iter_chunks(source))
    canonical = pl.concat(frames, rechunk=False).sort("event_time")
    canonical.write_parquet(destination, compression="zstd")
    return {"events": canonical.height, "customers": canonical["customer_id"].n_unique()}
