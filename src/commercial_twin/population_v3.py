from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import polars as pl


@dataclass(frozen=True)
class ElectronicsPurchasePaths:
    customer_month: Path
    orders: Path
    profile: Path


def prepare_electronics_purchase_aggregates(
    raw_path: Path = Path("data/raw/rees46/electronics-purchases/purchases.csv.gz"),
    output_directory: Path = Path("data/processed/rees46/electronics-purchases"),
) -> ElectronicsPurchasePaths:
    output_directory.mkdir(parents=True, exist_ok=True)
    customer_path = output_directory / "customer_month.parquet"
    order_path = output_directory / "orders.parquet"
    profile_path = output_directory / "profile.json"
    source = str(raw_path).replace("'", "''")
    connection = duckdb.connect()
    connection.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW purchases AS
        WITH lines AS (
          SELECT str_split(line, ',') parts
          FROM read_csv('{source}', columns={{'line':'VARCHAR'}}, delim='|', header=false,
                        skip=1, strict_mode=false, null_padding=true)
        )
        SELECT DISTINCT
          strptime(parts[1], '%Y-%m-%d %H:%M:%S UTC')::TIMESTAMPTZ event_time,
          parts[2] order_id, parts[3] product_id, parts[4] category_id,
          CASE WHEN len(parts) >= 8 THEN parts[5] ELSE parts[4] END category_code,
          CASE WHEN len(parts) >= 8 THEN parts[6] ELSE NULL END brand,
          parts[len(parts)-1]::DOUBLE price, nullif(parts[len(parts)], '') customer_id
        FROM lines WHERE len(parts) >= 6 AND nullif(parts[len(parts)], '') IS NOT NULL
        """
    )
    connection.execute(
        f"""
        COPY (
          SELECT date_trunc('month', event_time)::DATE AS month, customer_id,
            count(DISTINCT order_id) orders, count(*) purchase_items,
            sum(price) revenue, avg(price) mean_item_price,
            count(DISTINCT category_id) categories,
            arg_max(coalesce(category_code, category_id), event_time) recent_category,
            min(event_time) first_event, max(event_time) last_event
          FROM purchases GROUP BY 1,2
        ) TO '{str(customer_path).replace("'", "''")}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    connection.execute(
        f"""
        COPY (
          SELECT date_trunc('month', event_time)::DATE AS month, customer_id, order_id,
            sum(price) order_value, count(*) items,
            arg_max(coalesce(category_code, category_id), event_time) category
          FROM purchases GROUP BY 1,2,3
        ) TO '{str(order_path).replace("'", "''")}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    row = connection.execute(
        """
        SELECT count(*), count(DISTINCT customer_id), count(DISTINCT order_id),
          sum(price), min(event_time), max(event_time) FROM purchases
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("purchase profile returned no row")
    profile = {
        "deduplicated_purchase_items": int(row[0]),
        "customers": int(row[1]),
        "orders": int(row[2]),
        "revenue": float(row[3]),
        "history_start": str(row[4]),
        "history_end": str(row[5]),
    }
    profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    connection.close()
    return ElectronicsPurchasePaths(customer_path, order_path, profile_path)


def logit_intercept_reconcile(
    probabilities: np.ndarray, target_total: float, *, tolerance: float = 1e-8
) -> tuple[np.ndarray, float]:
    probability = np.clip(np.asarray(probabilities, dtype=float), 1e-9, 1 - 1e-9)
    target = float(np.clip(target_total, 0, len(probability)))
    if target <= tolerance:
        return np.zeros_like(probability), float("-inf")
    if target >= len(probability) - tolerance:
        return np.ones_like(probability), float("inf")
    logits = np.log(probability / (1 - probability))
    lower, upper = -40.0, 40.0
    for _ in range(100):
        alpha = (lower + upper) / 2
        calibrated = 1 / (1 + np.exp(-(logits + alpha)))
        if calibrated.sum() < target:
            lower = alpha
        else:
            upper = alpha
        if abs(float(calibrated.sum()) - target) <= tolerance:
            break
    alpha = (lower + upper) / 2
    result = 1 / (1 + np.exp(-(logits + alpha)))
    return result, alpha


def naive_probability_scale(probabilities: np.ndarray, target_total: float) -> np.ndarray:
    probability = np.clip(np.asarray(probabilities, dtype=float), 0, 1)
    if probability.sum() <= 0:
        return np.full(len(probability), target_total / max(len(probability), 1))
    return np.clip(probability * target_total / probability.sum(), 0, 1)


def reconcile_expected_orders(
    purchase_probability: np.ndarray,
    repeat_propensity: np.ndarray,
    target_orders: float,
) -> np.ndarray:
    probability = np.asarray(purchase_probability, dtype=float)
    buyer_total = float(probability.sum())
    target = max(float(target_orders), buyer_total)
    extra = target - buyer_total
    weights = probability * np.clip(np.asarray(repeat_propensity, dtype=float), 0, None)
    if weights.sum() <= 0:
        weights = probability.copy()
    allocation = extra * weights / max(float(weights.sum()), 1e-12)
    result = probability + allocation
    correction = target - float(result.sum())
    if len(result):
        result[int(np.argmax(weights))] += correction
    return np.clip(result, 0, None)


def reconcile_expected_revenue(
    expected_orders: np.ndarray,
    relative_order_value: np.ndarray,
    target_revenue: float,
) -> np.ndarray:
    weights = np.asarray(expected_orders, dtype=float) * np.clip(
        np.asarray(relative_order_value, dtype=float), 0, None
    )
    if weights.sum() <= 0:
        weights = np.asarray(expected_orders, dtype=float)
    result = max(float(target_revenue), 0) * weights / max(float(weights.sum()), 1e-12)
    if len(result):
        result[int(np.argmax(weights))] += max(float(target_revenue), 0) - float(result.sum())
    return np.clip(result, 0, None)


def reconcile_category_revenue(
    customer_categories: np.ndarray,
    customer_revenue: np.ndarray,
    category_targets: dict[str, float],
) -> tuple[np.ndarray, dict[str, float]]:
    categories = np.asarray(customer_categories, dtype=str)
    result = np.asarray(customer_revenue, dtype=float).copy()
    adjustments: dict[str, float] = {}
    for category, target in category_targets.items():
        mask = categories == category
        current = float(result[mask].sum())
        if not mask.any() or current <= 0:
            continue
        factor = max(float(target), 0) / current
        result[mask] *= factor
        adjustments[category] = factor
    return result, adjustments


def calibration_deciles(actual: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    frame = (
        pl.DataFrame(
            {
                "actual": np.asarray(actual, dtype=float),
                "prediction": np.asarray(prediction, dtype=float),
            }
        )
        .sort("prediction")
        .with_row_index("rank")
    )
    frame = frame.with_columns(
        ((pl.col("rank") * 10 / max(frame.height, 1)).floor().clip(0, 9) + 1)
        .cast(pl.Int64)
        .alias("decile")
    )
    table = (
        frame.group_by("decile")
        .agg(
            pl.len().alias("customers"),
            pl.col("prediction").mean().alias("predicted_rate"),
            pl.col("actual").mean().alias("actual_rate"),
        )
        .with_columns(
            (pl.col("predicted_rate") - pl.col("actual_rate")).abs().alias("absolute_error")
        )
        .sort("decile")
    )
    ece = float(cast_number((table["absolute_error"] * table["customers"] / frame.height).sum()))
    return {
        "deciles": table.to_dicts(),
        "ece": ece,
        "mce": float(cast_number(table["absolute_error"].max())),
        "expected_buyers": float(np.asarray(prediction).sum()),
        "actual_buyers": float(np.asarray(actual).sum()),
    }


def simulate_reconciled_aggregates(
    forecast: dict[str, float],
    residuals: dict[str, list[float]],
    *,
    draws: int,
    seed: int,
) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    result: dict[str, list[float]] = {"buyers": [], "orders": [], "revenue": []}
    for _ in range(draws):
        sampled: dict[str, float] = {}
        for metric in result:
            residual = float(rng.choice(residuals[metric]))
            direction = -1 if rng.random() < 0.5 else 1
            sampled[metric] = max(float(forecast[metric]) * (1 + direction * residual), 0)
        sampled["orders"] = max(sampled["orders"], sampled["buyers"])
        for metric in result:
            result[metric].append(sampled[metric])
    return result


def cast_number(value: object) -> float:
    if value is None:
        return 0.0
    return float(value)  # type: ignore[arg-type]
