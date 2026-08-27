# ruff: noqa: E501
"""Leak-safe Online Retail II state, cohort, and predictive benchmark utilities."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    median_absolute_error,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = [
    "recency_days",
    "frequency",
    "monetary_value",
    "orders_30d",
    "orders_90d",
    "orders_180d",
    "revenue_30d",
    "revenue_90d",
    "revenue_180d",
    "units_30d",
    "units_90d",
    "units_180d",
    "aov",
    "median_order_value",
    "customer_age_days",
    "interpurchase_days",
    "cancellation_frequency",
    "cancellation_value",
    "product_diversity",
]


def _quoted(path: str | Path) -> str:
    return str(path).replace("'", "''")


def build_state_frame(  # noqa: E501
    path: str | Path, as_of: datetime, horizon_days: int = 30
) -> pd.DataFrame:
    """Build features strictly before as_of and labels only after as_of."""
    parquet = _quoted(path)
    cutoff = as_of.isoformat()
    connection = duckdb.connect()
    query = f"""
    WITH raw AS (
      SELECT * FROM read_parquet('{parquet}')
    ), valid_lines AS (
      SELECT * FROM raw
      WHERE NOT is_cancellation AND quantity > 0 AND unit_price > 0
        AND customer_id IS NOT NULL
    ), orders AS (
      SELECT customer_id, invoice_no, min(invoice_time) order_time,
             sum(line_value) order_value, sum(quantity) units,
             count(distinct stock_code) products
      FROM valid_lines GROUP BY 1,2
    ), history AS (
      SELECT * FROM orders WHERE order_time < TIMESTAMPTZ '{cutoff}'
    ), ordered AS (
      SELECT *, lag(order_time) OVER (PARTITION BY customer_id ORDER BY order_time) previous_time
      FROM history
    ), states AS (
      SELECT customer_id,
        date_diff('day', max(order_time), TIMESTAMPTZ '{cutoff}')::DOUBLE recency_days,
        count(*)::DOUBLE frequency,
        sum(order_value)::DOUBLE monetary_value,
        count(*) FILTER (WHERE order_time >= TIMESTAMPTZ '{cutoff}' - INTERVAL 30 DAY)::DOUBLE orders_30d,
        count(*) FILTER (WHERE order_time >= TIMESTAMPTZ '{cutoff}' - INTERVAL 90 DAY)::DOUBLE orders_90d,
        count(*) FILTER (WHERE order_time >= TIMESTAMPTZ '{cutoff}' - INTERVAL 180 DAY)::DOUBLE orders_180d,
        coalesce(sum(order_value) FILTER (WHERE order_time >= TIMESTAMPTZ '{cutoff}' - INTERVAL 30 DAY),0)::DOUBLE revenue_30d,
        coalesce(sum(order_value) FILTER (WHERE order_time >= TIMESTAMPTZ '{cutoff}' - INTERVAL 90 DAY),0)::DOUBLE revenue_90d,
        coalesce(sum(order_value) FILTER (WHERE order_time >= TIMESTAMPTZ '{cutoff}' - INTERVAL 180 DAY),0)::DOUBLE revenue_180d,
        coalesce(sum(units) FILTER (WHERE order_time >= TIMESTAMPTZ '{cutoff}' - INTERVAL 30 DAY),0)::DOUBLE units_30d,
        coalesce(sum(units) FILTER (WHERE order_time >= TIMESTAMPTZ '{cutoff}' - INTERVAL 90 DAY),0)::DOUBLE units_90d,
        coalesce(sum(units) FILTER (WHERE order_time >= TIMESTAMPTZ '{cutoff}' - INTERVAL 180 DAY),0)::DOUBLE units_180d,
        avg(order_value)::DOUBLE aov,
        median(order_value)::DOUBLE median_order_value,
        date_diff('day', min(order_time), TIMESTAMPTZ '{cutoff}')::DOUBLE customer_age_days,
        coalesce(avg(date_diff('day', previous_time, order_time)),0)::DOUBLE interpurchase_days,
        sum(products)::DOUBLE product_diversity
      FROM ordered GROUP BY 1
    ), cancels AS (
      SELECT customer_id, count(*)::DOUBLE cancellation_frequency,
             abs(coalesce(sum(line_value),0))::DOUBLE cancellation_value
      FROM raw WHERE (is_cancellation OR quantity < 0) AND customer_id IS NOT NULL
        AND invoice_time < TIMESTAMPTZ '{cutoff}' GROUP BY 1
    ), future AS (
      SELECT customer_id, count(*)::INTEGER future_orders,
             sum(order_value)::DOUBLE future_revenue,
             avg(order_value)::DOUBLE future_order_value
      FROM orders WHERE order_time >= TIMESTAMPTZ '{cutoff}'
        AND order_time < TIMESTAMPTZ '{cutoff}' + INTERVAL {horizon_days} DAY GROUP BY 1
    )
    SELECT s.*, coalesce(c.cancellation_frequency,0) cancellation_frequency,
      coalesce(c.cancellation_value,0) cancellation_value,
      (coalesce(f.future_orders,0)>0)::INTEGER label_purchase,
      coalesce(f.future_orders,0)::INTEGER label_orders,
      coalesce(f.future_revenue,0)::DOUBLE label_revenue,
      coalesce(f.future_order_value,0)::DOUBLE label_order_value,
      CASE WHEN s.customer_age_days <= 30 THEN 'NEW'
           WHEN s.recency_days <= 60 THEN 'ACTIVE'
           WHEN s.recency_days <= 120 THEN 'COOLING'
           ELSE 'DORMANT' END lifecycle
    FROM states s LEFT JOIN cancels c USING(customer_id) LEFT JOIN future f USING(customer_id)
    ORDER BY customer_id
    """
    frame = connection.execute(query).fetchdf()
    connection.close()
    return frame


def calibration_metrics(y: np.ndarray, probability: np.ndarray) -> dict[str, Any]:
    edges = np.quantile(probability, np.linspace(0, 1, 11))
    edges[0], edges[-1] = -np.inf, np.inf
    bins = np.digitize(probability, edges[1:-1], right=True)
    rows: list[dict[str, float | int]] = []
    for index in range(10):
        selected = bins == index
        if not selected.any():
            continue
        rows.append(
            {
                "decile": index + 1,
                "customers": int(selected.sum()),
                "predicted_rate": float(probability[selected].mean()),
                "actual_rate": float(y[selected].mean()),
            }
        )
    errors = [abs(float(row["predicted_rate"]) - float(row["actual_rate"])) for row in rows]
    weights = [int(row["customers"]) / len(y) for row in rows]
    return {
        "ece": float(sum(error * weight for error, weight in zip(errors, weights, strict=True))),
        "mce": float(max(errors, default=0)),
        "deciles": rows,
    }


def _rfm_probability(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    columns = ["recency_days", "frequency", "monetary_value"]
    x_train = train[columns].to_numpy(float)
    x_test = test[columns].to_numpy(float)
    location = np.nanmedian(x_train, axis=0)
    scale = np.nanpercentile(x_train, 75, axis=0) - np.nanpercentile(x_train, 25, axis=0)
    scale[scale == 0] = 1
    train_score = (
        (-1 * (x_train[:, 0] - location[0]) / scale[0])
        + ((x_train[:, 1] - location[1]) / scale[1])
        + ((x_train[:, 2] - location[2]) / scale[2])
    )
    test_score = (
        (-1 * (x_test[:, 0] - location[0]) / scale[0])
        + ((x_test[:, 1] - location[1]) / scale[1])
        + ((x_test[:, 2] - location[2]) / scale[2])
    )
    calibrator = LogisticRegression(C=0.1, random_state=42).fit(
        train_score.reshape(-1, 1), train["label_purchase"]
    )
    return calibrator.predict_proba(test_score.reshape(-1, 1))[:, 1]


def fit_purchase_candidates(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, np.ndarray]:
    x_train = train[FEATURES].fillna(0).to_numpy(float)
    x_test = test[FEATURES].fillna(0).to_numpy(float)
    y = train["label_purchase"].to_numpy(int)
    rate = float(y.mean())
    outputs = {
        "population_rate": np.full(len(test), rate),
        "rfm": _rfm_probability(train, test),
    }
    logistic = make_pipeline(
        StandardScaler(), LogisticRegression(C=0.1, max_iter=2_000, random_state=42)
    ).fit(x_train, y)
    outputs["logistic"] = logistic.predict_proba(x_test)[:, 1]
    boosting = HistGradientBoostingClassifier(
        max_iter=150, max_leaf_nodes=15, learning_rate=0.05, l2_regularization=2, random_state=42
    ).fit(x_train, y)
    outputs["gradient_boosting"] = boosting.predict_proba(x_test)[:, 1]
    # A transparent customer-base rate challenger. It is not mislabeled BG/NBD.
    exposure = np.maximum(train["customer_age_days"].to_numpy(float), 30) / 30
    alpha = float(train["frequency"].sum()) / max(float(exposure.sum()), 1)
    test_exposure = np.maximum(test["customer_age_days"].to_numpy(float), 30) / 30
    posterior_rate = (test["frequency"].to_numpy(float) + alpha) / (test_exposure + 1)
    outputs["empirical_bayes_rate"] = 1 - np.exp(-np.maximum(posterior_rate, 0))
    return outputs


def score_purchase(y: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    clipped = np.clip(probability, 1e-6, 1 - 1e-6)
    return {
        "auc": float(roc_auc_score(y, clipped)),
        "pr_auc": float(average_precision_score(y, clipped)),
        "brier": float(brier_score_loss(y, clipped)),
        "log_loss": float(log_loss(y, clipped)),
        "buyer_count_error": float(abs(clipped.sum() - y.sum()) / max(y.sum(), 1)),
        **{
            key: value for key, value in calibration_metrics(y, clipped).items() if key != "deciles"
        },
    }


def monetary_candidates(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, np.ndarray]:
    buyers = train[train["label_purchase"] == 1]
    global_mean = float(buyers["label_order_value"].mean())
    customer_mean = test["aov"].fillna(global_mean).to_numpy(float)
    shrinkage = (test["frequency"].to_numpy(float) * customer_mean + 5 * global_mean) / (
        test["frequency"].to_numpy(float) + 5
    )
    model = HistGradientBoostingRegressor(
        loss="absolute_error", max_iter=100, max_leaf_nodes=15, random_state=42
    ).fit(buyers[FEATURES].fillna(0), buyers["label_order_value"])
    return {
        "cohort_mean": np.full(len(test), global_mean),
        "customer_mean": customer_mean,
        "shrunk_customer_mean": shrinkage,
        "gradient_boosting": np.maximum(model.predict(test[FEATURES].fillna(0)), 0),
    }


def score_monetary(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "median_ae": float(median_absolute_error(actual, predicted)),
        "aggregate_bias": float((predicted.sum() - actual.sum()) / max(actual.sum(), 1)),
        "p95_prediction": float(np.quantile(predicted, 0.95)),
        "p95_actual": float(np.quantile(actual, 0.95)),
    }
