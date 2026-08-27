"""Dominick's scanner-data adapter with an explicit, leak-safe canonical mapping."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import polars as pl
from pydantic import BaseModel, ConfigDict, Field


class CanonicalField(BaseModel):
    model_config = ConfigDict(frozen=True)
    canonical_name: str
    source_fields: tuple[str, ...]
    status: str
    derivation: str | None = None


class CommerceDataValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    dataset: str
    category: str
    source: str
    license_scope: str
    rows_raw: int
    rows_canonical: int
    products: int
    categories: int
    stores: int
    customers: int | None = None
    history_start: date
    history_end: date
    history_weeks: int
    promotion_events: int
    discount_quantiles: dict[str, float]
    missingness: dict[str, float]
    observed_fields: tuple[str, ...]
    inferred_fields: tuple[str, ...]
    unavailable_fields: tuple[str, ...]
    mapping: tuple[CanonicalField, ...]
    warnings: tuple[str, ...] = Field(default_factory=tuple)


class DominicksDataset:
    """Load one authorized category and map it to canonical commerce history.

    Discount is inferred from unit price relative to the maximum unit price observed in the
    preceding 13 weeks for the same store/UPC. Current and future rows never enter the reference.
    This is a reproducible price-promotion proxy, not an observed list price.
    """

    SOURCE_URL = "https://www.chicagobooth.edu/research/kilts/research-data/dominicks"

    def __init__(self, raw_dir: str | Path, category: str = "oatmeal") -> None:
        self.raw_dir = Path(raw_dir)
        self.category = category

    def available_files(self) -> list[Path]:
        return sorted(self.raw_dir.glob("*.csv")) + sorted(self.raw_dir.glob("*.parquet"))

    def inspect_schemas(self) -> dict[str, dict[str, str]]:
        schemas: dict[str, dict[str, str]] = {}
        for path in self.available_files():
            frame = (
                pl.read_csv(path, n_rows=100, infer_schema_length=None)
                if path.suffix == ".csv"
                else pl.read_parquet(path).head(100)
            )
            schemas[path.name] = {name: str(dtype) for name, dtype in frame.schema.items()}
        return schemas

    def _paths(self) -> tuple[Path, Path]:
        code = {"oatmeal": "oat"}.get(self.category)
        if code is None:
            raise ValueError(f"no reviewed mapping for Dominick's category {self.category!r}")
        movement = self.raw_dir / f"w{code}.csv"
        products = self.raw_dir / f"upc{code}.csv"
        missing = [str(path) for path in (movement, products) if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "Dominick's files are not installed. Download authorized movement and UPC CSV "
                f"files from {self.SOURCE_URL} into {self.raw_dir}. Missing: {missing}"
            )
        return movement, products

    def load_canonical(self) -> tuple[pl.DataFrame, CommerceDataValidationReport]:
        movement_path, products_path = self._paths()
        movement = pl.read_csv(movement_path, infer_schema_length=10_000)
        products = pl.read_csv(products_path, infer_schema_length=None)
        raw_rows = movement.height
        movement = movement.with_columns(
            pl.col("PRICE", "QTY", "MOVE", "PROFIT").cast(pl.Float64, strict=False)
        ).filter(
            (pl.col("OK") == 1)
            & (pl.col("PRICE") > 0)
            & (pl.col("QTY") > 0)
            & (pl.col("MOVE") >= 0)
        ).with_columns(
            (pl.col("PRICE") / pl.col("QTY")).alias("unit_price"),
            pl.date(1989, 9, 14)
            .add(pl.duration(weeks=pl.col("WEEK") - 1))
            .alias("event_date"),
        )
        joined = movement.join(products, on="UPC", how="left").sort(
            ["STORE", "UPC", "WEEK"]
        )
        joined = joined.with_columns(
            pl.col("unit_price")
            .shift(1)
            .rolling_max(window_size=13, min_samples=4)
            .over(["STORE", "UPC"])
            .alias("reference_price"),
            pl.col("MOVE")
            .shift(1)
            .rolling_mean(window_size=4, min_samples=2)
            .over(["STORE", "UPC"])
            .alias("lagged_units"),
            pl.col("event_date").min().over("UPC").alias("first_product_date"),
        ).with_columns(
            ((pl.col("reference_price") - pl.col("unit_price")) / pl.col("reference_price"))
            .clip(0, 0.30)
            .alias("inferred_discount"),
            pl.when(pl.col("PROFIT").is_between(0, 100, closed="both"))
            .then(pl.col("unit_price") * (1 - pl.col("PROFIT") / 100))
            .otherwise(None)
            .alias("inferred_unit_cost"),
        )
        usable = joined.filter(
            pl.col("reference_price").is_not_null() & pl.col("lagged_units").is_not_null()
        )
        canonical = usable.select(
            pl.col("event_date").cast(pl.Datetime("us", "UTC")).alias("date"),
            pl.col("event_date").cast(pl.Datetime("us", "UTC")).alias("observed_at"),
            pl.col("STORE").cast(pl.String).alias("store_id"),
            pl.col("COM_CODE").cast(pl.String).alias("category_id"),
            pl.col("UPC").cast(pl.String).alias("sku_id"),
            pl.col("MOVE").cast(pl.Float64).alias("observed_sales"),
            pl.col("unit_price").alias("price"),
            pl.col("reference_price").alias("regular_price"),
            pl.col("inferred_discount").alias("discount"),
            pl.col("inferred_unit_cost").alias("unit_cost"),
            pl.col("lagged_units").alias("lagged_demand"),
            pl.col("event_date").dt.weekday().alias("weekday"),
            (
                (pl.col("event_date") - pl.col("first_product_date")).dt.total_days() / 365
            ).alias("product_age"),
            pl.col("SALE").is_not_null().alias("promotion_indicator"),
            pl.col("SALE").alias("promotion_code"),
            pl.lit("lagged_13_week_store_upc_max").alias("discount_source"),
            pl.lit("documented_gross_margin_AAC").alias("unit_cost_source"),
        )
        return canonical, self._report(canonical, raw_rows)

    def load(self) -> pl.DataFrame:
        return self.load_canonical()[0]

    def _report(
        self, frame: pl.DataFrame, raw_rows: int
    ) -> CommerceDataValidationReport:
        probabilities = (0.0, 0.25, 0.5, 0.75, 0.9, 1.0)
        labels = ("p00", "p25", "p50", "p75", "p90", "p100")
        quantiles = {
            label: cast(float, frame["discount"].quantile(probability))
            for label, probability in zip(labels, probabilities, strict=True)
        }
        missingness = {
            name: frame[name].null_count() / max(frame.height, 1) for name in frame.columns
        }
        mapping = (
            CanonicalField(
                canonical_name="date",
                source_fields=("WEEK",),
                status="OBSERVED",
                derivation="official week 1 start 1989-09-14 plus 7-day increments",
            ),
            CanonicalField(canonical_name="sku_id", source_fields=("UPC",), status="OBSERVED"),
            CanonicalField(
                canonical_name="category_id", source_fields=("COM_CODE",), status="OBSERVED"
            ),
            CanonicalField(
                canonical_name="store_id", source_fields=("STORE",), status="OBSERVED"
            ),
            CanonicalField(
                canonical_name="observed_sales", source_fields=("MOVE",), status="OBSERVED"
            ),
            CanonicalField(
                canonical_name="price",
                source_fields=("PRICE", "QTY"),
                status="DERIVED",
                derivation="PRICE / QTY per official manual",
            ),
            CanonicalField(
                canonical_name="regular_price",
                source_fields=("PRICE", "QTY"),
                status="INFERRED",
                derivation="strictly lagged 13-week store/UPC maximum",
            ),
            CanonicalField(
                canonical_name="discount",
                source_fields=("PRICE", "QTY"),
                status="INFERRED",
                derivation="max(0, 1 - unit_price / lagged reference), capped at 30%",
            ),
            CanonicalField(
                canonical_name="unit_cost",
                source_fields=("PRICE", "QTY", "PROFIT"),
                status="DERIVED",
                derivation="unit price * (1 - gross-margin percentage); AAC caveat applies",
            ),
        )
        return CommerceDataValidationReport(
            dataset="dominicks",
            category=self.category,
            source=self.SOURCE_URL,
            license_scope="academic research; acknowledge Chicago Booth Kilts Center",
            rows_raw=raw_rows,
            rows_canonical=frame.height,
            products=frame["sku_id"].n_unique(),
            categories=frame["category_id"].n_unique(),
            stores=frame["store_id"].n_unique(),
            history_start=cast(datetime, frame["date"].min()).date(),
            history_end=cast(datetime, frame["date"].max()).date(),
            history_weeks=frame["date"].n_unique(),
            promotion_events=frame.filter(pl.col("promotion_indicator")).height,
            discount_quantiles=quantiles,
            missingness=missingness,
            observed_fields=(
                "WEEK", "STORE", "UPC", "MOVE", "PRICE", "QTY", "PROFIT", "SALE", "OK",
                "COM_CODE",
            ),
            inferred_fields=(
                "regular_price", "discount", "unit_cost", "lagged_demand", "product_age"
            ),
            unavailable_fields=(
                "customer_id", "inventory", "stockout", "returns", "campaign",
                "external_world_state",
            ),
            mapping=mapping,
            warnings=(
                "discount is a lagged-price proxy because no list price exists",
                "promotion codes are incomplete according to the data manual",
                "unit cost is average acquisition cost, not replacement cost",
                "counterfactual outcomes are not observed",
            ),
        )

    def profile(self) -> dict[str, Any]:
        _, report = self.load_canonical()
        return report.model_dump(mode="json")
