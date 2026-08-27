from __future__ import annotations

from datetime import datetime

import polars as pl

from commercial_twin.schemas import CustomerState


def build_behavior_cohorts(frame: pl.DataFrame, observed_at: datetime) -> tuple[CustomerState, ...]:
    """Build deterministic, non-PII category cohorts from canonical retail history."""
    summary = (
        frame.group_by("category_id")
        .agg(
            pl.len().alias("rows"),
            pl.col("sku_id").n_unique().alias("entities"),
            pl.col("observed_sales").mean().alias("frequency"),
            (pl.col("observed_sales") * pl.col("price")).sum().alias("monetary"),
            pl.col("price").mean().alias("aov"),
            pl.col("discount").mean().alias("promo_response"),
        )
        .sort("category_id")
    )
    return tuple(
        CustomerState(
            cohort_id=str(row["category_id"]),
            entity_count=max(int(row["entities"]), 1),
            recency_days=0.0,
            frequency=float(row["frequency"]),
            monetary_value=float(row["monetary"]),
            historical_aov=float(row["aov"]),
            category_affinity={str(row["category_id"]): 1.0},
            purchase_frequency=float(row["rows"]) / max(int(row["entities"]), 1),
            promotion_response=float(row["promo_response"]),
            observed_at=observed_at,
        )
        for row in summary.iter_rows(named=True)
    )
