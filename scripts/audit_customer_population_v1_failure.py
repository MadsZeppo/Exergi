from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from commercial_twin.population_models import build_future_outcomes
from commercial_twin.population_state import attach_affinities, build_customer_states
from commercial_twin.population_v2 import decompose_revenue


def _breakdown(frame: pl.DataFrame, column: str) -> list[dict[str, Any]]:
    return list(
        frame.group_by(column)
        .agg(
            pl.len().alias("customers"),
            pl.col("purchase_probability").sum().alias("predicted_buyers"),
            pl.col("purchase").sum().alias("actual_buyers"),
            pl.col("expected_orders").sum().alias("predicted_orders"),
            pl.col("orders").sum().alias("actual_orders"),
            pl.col("expected_spend").sum().alias("predicted_revenue"),
            pl.col("spend").sum().alias("actual_revenue"),
        )
        .with_columns(
            (
                (pl.col("predicted_revenue") - pl.col("actual_revenue"))
                / pl.col("actual_revenue").abs().clip(1, None)
            ).alias("revenue_relative_error")
        )
        .sort("predicted_revenue", descending=True)
        .to_dicts()
    )


def main() -> Path:
    artifact = Path("artifacts/customer_population/rees46-electronics-v1-seed-42")
    events = pl.read_parquet("data/processed/rees46/electronics-events.parquet")
    cutoff = datetime(2021, 2, 1, tzinfo=UTC)
    state = attach_affinities(events, build_customer_states(events, cutoff), cutoff)
    frozen = pl.read_parquet(artifact / "frozen_final_customer_predictions.parquet")
    actual = build_future_outcomes(events, state, cutoff, cutoff + timedelta(days=30))
    joined = (
        state.join(frozen, on="customer_id")
        .join(actual, on="customer_id")
        .with_columns(
            pl.when(pl.col("purchases_180d") == 0)
            .then(pl.lit("0"))
            .when(pl.col("purchases_180d") == 1)
            .then(pl.lit("1"))
            .when(pl.col("purchases_180d") == 2)
            .then(pl.lit("2"))
            .otherwise(pl.lit("3+"))
            .alias("historical_purchase_bucket"),
            pl.when(pl.col("effective_history_days") <= 30)
            .then(pl.lit("0-30d"))
            .when(pl.col("effective_history_days") <= 90)
            .then(pl.lit("31-90d"))
            .otherwise(pl.lit("91d+"))
            .alias("history_bucket"),
        )
    )
    ranked = joined.sort("expected_spend", descending=True).with_row_index("rank")
    ranked = ranked.with_columns(
        pl.when(pl.col("rank") < max(int(ranked.height * 0.01), 1))
        .then(pl.lit("top_1pct"))
        .when(pl.col("rank") < max(int(ranked.height * 0.05), 1))
        .then(pl.lit("next_4pct"))
        .otherwise(pl.lit("bottom_95pct"))
        .alias("predicted_spender_segment")
    )
    future_purchase = events.filter(
        (pl.col("event_time") > cutoff)
        & (pl.col("event_time") <= cutoff + timedelta(days=30))
        & (pl.col("event_type") == "purchase")
    )
    new_purchase = future_purchase.join(state.select("customer_id"), on="customer_id", how="anti")
    new_population = {
        "buyers": new_purchase["customer_id"].n_unique(),
        "orders": new_purchase.select("customer_id", "session_id").unique().height,
        "revenue": float(new_purchase["price"].sum()),
    }
    predicted_buyers = float(joined["purchase_probability"].sum())
    predicted_orders = float(joined["expected_orders"].sum())
    predicted_revenue = float(joined["expected_spend"].sum())
    actual_buyers = float(joined["purchase"].sum())
    actual_orders = float(joined["orders"].sum())
    actual_revenue = float(joined["spend"].sum())
    report = decompose_revenue(
        predicted_buyers=predicted_buyers,
        predicted_orders=predicted_orders,
        predicted_revenue=predicted_revenue,
        actual_buyers=actual_buyers,
        actual_orders=actual_orders,
        actual_revenue=actual_revenue,
        breakdowns={
            "cohort": _breakdown(ranked, "cohort_id"),
            "lifecycle": _breakdown(ranked, "lifecycle"),
            "history_length": _breakdown(ranked, "history_bucket"),
            "historical_purchases": _breakdown(ranked, "historical_purchase_bucket"),
            "predicted_spender_tail": _breakdown(ranked, "predicted_spender_segment"),
            "category": _breakdown(ranked, "dominant_category")[:50],
            "new_vs_existing": [
                {
                    "population": "existing",
                    "predicted_buyers": predicted_buyers,
                    "actual_buyers": actual_buyers,
                    "predicted_orders": predicted_orders,
                    "actual_orders": actual_orders,
                    "predicted_revenue": predicted_revenue,
                    "actual_revenue": actual_revenue,
                },
                {
                    "population": "new",
                    "predicted_buyers": 0,
                    "actual_buyers": new_population["buyers"],
                    "predicted_orders": 0,
                    "actual_orders": new_population["orders"],
                    "predicted_revenue": 0,
                    "actual_revenue": new_population["revenue"],
                },
            ],
        },
    )
    path = artifact / "failure_decomposition.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(path)
    return path


if __name__ == "__main__":
    main()
