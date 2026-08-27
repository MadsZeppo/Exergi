from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
from pydantic import BaseModel, ConfigDict


class FailureComponent(BaseModel):
    model_config = ConfigDict(frozen=True)
    predicted: float
    actual: float
    absolute_error: float
    relative_error: float
    revenue_error_contribution: float


class FailureDecompositionReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    buyers: FailureComponent
    orders_per_buyer: FailureComponent
    revenue_per_order: FailureComponent
    predicted_revenue: float
    actual_revenue: float
    total_revenue_error: float
    breakdowns: dict[str, list[dict[str, Any]]]
    label_findings: tuple[str, ...]


def _component(predicted: float, actual: float, contribution: float) -> FailureComponent:
    return FailureComponent(
        predicted=predicted,
        actual=actual,
        absolute_error=predicted - actual,
        relative_error=(predicted - actual) / max(abs(actual), 1e-12),
        revenue_error_contribution=contribution,
    )


def decompose_revenue(
    *,
    predicted_buyers: float,
    predicted_orders: float,
    predicted_revenue: float,
    actual_buyers: float,
    actual_orders: float,
    actual_revenue: float,
    breakdowns: dict[str, list[dict[str, Any]]] | None = None,
) -> FailureDecompositionReport:
    predicted_opb = predicted_orders / max(predicted_buyers, 1e-12)
    actual_opb = actual_orders / max(actual_buyers, 1e-12)
    predicted_rpo = predicted_revenue / max(predicted_orders, 1e-12)
    actual_rpo = actual_revenue / max(actual_orders, 1e-12)
    buyer_contribution = (predicted_buyers - actual_buyers) * predicted_opb * predicted_rpo
    order_contribution = actual_buyers * (predicted_opb - actual_opb) * predicted_rpo
    value_contribution = actual_buyers * actual_opb * (predicted_rpo - actual_rpo)
    return FailureDecompositionReport(
        buyers=_component(predicted_buyers, actual_buyers, buyer_contribution),
        orders_per_buyer=_component(predicted_opb, actual_opb, order_contribution),
        revenue_per_order=_component(predicted_rpo, actual_rpo, value_contribution),
        predicted_revenue=predicted_revenue,
        actual_revenue=actual_revenue,
        total_revenue_error=predicted_revenue - actual_revenue,
        breakdowns=breakdowns or {},
        label_findings=(
            "purchase events are item/line events; customer-session is the order key",
            "exact duplicate source rows must be removed",
            "new customers were absent from V1 total-population generation",
            "V1 incidence, order count and spend simulations were not generatively coherent",
        ),
    )


@dataclass(frozen=True)
class CosmeticsAggregatePaths:
    customer_month: Path
    orders: Path
    profile: Path


def prepare_cosmetics_aggregates(
    raw_directory: Path = Path("data/raw/rees46/cosmetics"),
    output_directory: Path = Path("data/processed/rees46/cosmetics"),
) -> CosmeticsAggregatePaths:
    """Stream compressed CSVs through DuckDB; never materialize raw multi-million rows."""
    output_directory.mkdir(parents=True, exist_ok=True)
    customer_path = output_directory / "customer_month.parquet"
    order_path = output_directory / "orders.parquet"
    profile_path = output_directory / "profile.json"
    glob = str(raw_directory / "*.csv.gz").replace("'", "''")
    connection = duckdb.connect()
    connection.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW events AS
        SELECT DISTINCT
          strptime(event_time::VARCHAR, '%Y-%m-%d %H:%M:%S')::TIMESTAMPTZ AS event_time,
          event_type,
          product_id::VARCHAR AS product_id,
          category_id::VARCHAR AS category_id,
          brand,
          price::DOUBLE AS price,
          user_id::VARCHAR AS customer_id,
          user_session::VARCHAR AS session_id
        FROM read_csv('{glob}', header=true, union_by_name=true)
        """
    )
    connection.execute(
        f"""
        COPY (
          SELECT date_trunc('month', event_time)::DATE AS month, customer_id,
            count(*) FILTER (WHERE event_type='view') AS views,
            count(*) FILTER (WHERE event_type='cart') AS carts,
            count(*) FILTER (WHERE event_type='remove_from_cart') AS removes,
            count(*) FILTER (WHERE event_type='purchase') AS purchase_items,
            count(DISTINCT session_id) FILTER (WHERE event_type='purchase') AS orders,
            coalesce(sum(price) FILTER (WHERE event_type='purchase'), 0) AS revenue,
            coalesce(avg(price) FILTER (WHERE event_type='purchase'), 0) AS mean_item_price,
            count(DISTINCT category_id) AS categories,
            arg_max(category_id, event_time) AS recent_category,
            min(event_time) AS first_event,
            max(event_time) AS last_event
          FROM events GROUP BY 1, 2
        ) TO '{str(customer_path).replace("'", "''")}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    connection.execute(
        f"""
        COPY (
          SELECT date_trunc('month', event_time)::DATE AS month, customer_id, session_id,
            sum(price) AS order_value, count(*) AS items,
            arg_max(category_id, event_time) AS category_id
          FROM events WHERE event_type='purchase'
          GROUP BY 1, 2, 3
        ) TO '{str(order_path).replace("'", "''")}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    profile_row = connection.execute(
        """
        SELECT count(*) raw_events, count(DISTINCT customer_id) customers,
          min(event_time) history_start, max(event_time) history_end,
          count(*) FILTER (WHERE event_type='purchase') purchase_items,
          count(DISTINCT (customer_id, session_id)) FILTER (WHERE event_type='purchase') orders,
          sum(price) FILTER (WHERE event_type='purchase') revenue
        FROM events
        """
    ).fetchone()
    if profile_row is None:
        raise RuntimeError("cosmetics profile query returned no row")
    profile = {
        "deduplicated_events": int(profile_row[0]),
        "customers": int(profile_row[1]),
        "history_start": str(profile_row[2]),
        "history_end": str(profile_row[3]),
        "purchase_items": int(profile_row[4]),
        "orders": int(profile_row[5]),
        "revenue": float(profile_row[6]),
        "raw_files": sorted(path.name for path in raw_directory.glob("*.csv.gz")),
    }
    profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    connection.close()
    return CosmeticsAggregatePaths(customer_path, order_path, profile_path)


def spend_quantiles(values: np.ndarray) -> dict[str, float]:
    clean = np.asarray(values, dtype=float)
    return {
        "p50": float(np.quantile(clean, 0.50)),
        "p90": float(np.quantile(clean, 0.90)),
        "p95": float(np.quantile(clean, 0.95)),
        "p99": float(np.quantile(clean, 0.99)),
        "max": float(np.max(clean)),
        "top_1pct_share": float(np.sort(clean)[-max(1, int(len(clean) * 0.01)) :].sum())
        / max(float(clean.sum()), 1e-12),
    }
