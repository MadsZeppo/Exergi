# ruff: noqa: E501
"""Leak-safe H&M merchant day-1 readiness benchmark utilities.

The H&M transaction table has no order identifier.  This module therefore models
transaction lines, active shopping days, and observed transaction value only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import duckdb
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression
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

HORIZON_DAYS = 30
HISTORY_MONTHS = (6, 9, 12)
RANDOM_SEED = 42

FEATURE_COLUMNS = (
    "recency_days",
    "customer_age_days",
    "lines_7d",
    "lines_30d",
    "lines_60d",
    "lines_90d",
    "lines_180d",
    "active_days",
    "active_days_30d",
    "active_days_90d",
    "value_total",
    "value_30d",
    "value_90d",
    "value_180d",
    "mean_line_value",
    "median_line_value",
    "value_per_active_day",
    "unique_articles",
    "product_group_diversity",
    "online_share",
    "mean_gap_days",
    "gap_std_days",
    "recent_line_change",
    "recent_value_change",
    "observation_count",
    "history_depth_days",
    "state_reliability",
    "sparse_history",
    "age",
    "age_missing",
    "club_active",
    "fashion_news_regularly",
)

RFM_COLUMNS = ("recency_days", "lines_90d", "value_90d", "active_days_90d")
RECENCY_COLUMNS = ("recency_days",)
LABEL_COLUMNS = ("label_repeat", "label_lines", "label_value")


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class HMPaths:
    transactions: Path
    customers: Path
    articles: Path


@dataclass(frozen=True)
class HMWindow:
    cutoff: datetime
    history_months: int
    data_min: datetime
    data_max: datetime

    @property
    def history_start(self) -> datetime:
        return self.cutoff - timedelta(days=round(self.history_months * 365.25 / 12))

    @property
    def future_end(self) -> datetime:
        return self.cutoff + timedelta(days=HORIZON_DAYS)

    def validate(self) -> None:
        if self.history_start < self.data_min:
            raise ValueError(
                f"{self.history_months}m history unavailable: "
                f"requires {self.history_start.date()}, data starts {self.data_min.date()}"
            )
        if self.future_end > self.data_max + timedelta(days=1):
            raise ValueError("full 30-day future window is unavailable")


def choose_cutoffs(data_min: datetime, data_max: datetime) -> dict[str, list[str] | str]:
    """Choose three development cutoffs and the latest valid final cutoff.

    Cutoffs are fixed independently of outcomes. The fallback has only enough coverage
    for 6m and 9m histories; feasibility is reported separately for every history length.
    """
    final = data_max + timedelta(days=1) - timedelta(days=HORIZON_DAYS)
    dev = [final - timedelta(days=77), final - timedelta(days=54), final - timedelta(days=30)]
    return {
        "development": [item.date().isoformat() for item in dev],
        "final": final.date().isoformat(),
    }


def audit_hm_data(paths: HMPaths) -> dict[str, Any]:
    connection = duckdb.connect()
    t_path = str(paths.transactions).replace("'", "''")
    c_path = str(paths.customers).replace("'", "''")
    a_path = str(paths.articles).replace("'", "''")
    transaction = connection.execute(
        f"""
        SELECT count(*) row_count, min(t_dat) min_date, max(t_dat) max_date,
               count(DISTINCT customer_id) customers,
               count(DISTINCT article_id) articles,
               count(*) FILTER (WHERE customer_id IS NULL) missing_customer,
               count(*) FILTER (WHERE article_id IS NULL) missing_article,
               count(*) FILTER (WHERE price IS NULL) missing_price,
               count(*) FILTER (WHERE price <= 0) nonpositive_price,
               min(price) min_price, quantile_cont(price, .5) median_price,
               quantile_cont(price, .99) p99_price, max(price) max_price
        FROM read_parquet('{t_path}')
        """
    ).fetchone()
    if transaction is None:
        raise RuntimeError("transaction audit returned no row")
    duplicate_row = connection.execute(
        f"""SELECT coalesce(sum(n - 1), 0) FROM (
        SELECT count(*) n FROM read_parquet('{t_path}')
        GROUP BY t_dat, customer_id, article_id, price, sales_channel_id HAVING count(*) > 1)"""
    ).fetchone()
    if duplicate_row is None:
        raise RuntimeError("duplicate audit returned no row")
    duplicates = duplicate_row[0]
    channels = connection.execute(
        f"SELECT sales_channel_id, count(*) row_count FROM read_parquet('{t_path}') "
        "GROUP BY 1 ORDER BY 1"
    ).fetchdf().to_dict("records")
    customer = connection.execute(
        f"""SELECT count(*) row_count, count(DISTINCT customer_id) customers,
        count(*) FILTER (WHERE age IS NULL) missing_age,
        min(age) min_age, quantile_cont(age,.5) median_age, max(age) max_age,
        count(*) FILTER (WHERE club_member_status IS NULL) missing_club,
        count(*) FILTER (WHERE fashion_news_frequency IS NULL) missing_fashion_news
        FROM read_parquet('{c_path}')"""
    ).fetchone()
    if customer is None:
        raise RuntimeError("customer audit returned no row")
    article = connection.execute(
        f"""SELECT count(*) row_count, count(DISTINCT article_id) articles,
        count(*) FILTER (WHERE product_group_name IS NULL) missing_product_group,
        count(*) FILTER (WHERE detail_desc IS NULL) missing_description
        FROM read_parquet('{a_path}')"""
    ).fetchone()
    if article is None:
        raise RuntimeError("article audit returned no row")
    connection.close()
    return {
        "source": "Stanford RelBench rel-hm fallback derived from H&M Kaggle data",
        "source_scope": "RelBench subset; not byte-identical to full Kaggle files",
        "license": "Non-Commercial Purposes & Academic Research (RelBench publisher label)",
        "files": {
            name: {"path": str(path), "bytes": path.stat().st_size, "sha256": file_sha256(path)}
            for name, path in {
                "transactions": paths.transactions,
                "customers": paths.customers,
                "articles": paths.articles,
            }.items()
        },
        "transactions": {
            "rows": int(transaction[0]),
            "min_date": str(transaction[1]),
            "max_date": str(transaction[2]),
            "unique_customers": int(transaction[3]),
            "unique_articles": int(transaction[4]),
            "missing_customer": int(transaction[5]),
            "missing_article": int(transaction[6]),
            "missing_price": int(transaction[7]),
            "nonpositive_price": int(transaction[8]),
            "price": {
                "min": float(transaction[9]),
                "median": float(transaction[10]),
                "p99": float(transaction[11]),
                "max": float(transaction[12]),
            },
            "exact_duplicate_rows_beyond_first": int(duplicates),
            "sales_channels": channels,
        },
        "customers": {
            "rows": int(customer[0]),
            "unique_customers": int(customer[1]),
            "missing_age": int(customer[2]),
            "age_min": float(customer[3]),
            "age_median": float(customer[4]),
            "age_max": float(customer[5]),
            "missing_club_member_status": int(customer[6]),
            "missing_fashion_news_frequency": int(customer[7]),
        },
        "articles": {
            "rows": int(article[0]),
            "unique_articles": int(article[1]),
            "missing_product_group": int(article[2]),
            "missing_description": int(article[3]),
        },
        "semantics": {
            "t_dat": "observed transaction date",
            "customer_id": "pseudonymous customer key",
            "article_id": "article key",
            "price": "observed transaction value in dataset units; not profit or proven GMV",
            "sales_channel_id": "observed channel code",
            "order_id": "NOT AVAILABLE",
            "geography": "NOT AVAILABLE; postal_code is not geolocated",
        },
    }


def _sql_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def build_state_frame(
    paths: HMPaths,
    *,
    history_start: datetime,
    as_of: datetime,
    include_labels: bool,
    sample_modulus: int | None = None,
) -> pd.DataFrame:
    """Build a customer state from [history_start, as_of), never from the target window."""
    if history_start >= as_of:
        raise ValueError("history_start must precede as_of")
    t_path = str(paths.transactions).replace("'", "''")
    c_path = str(paths.customers).replace("'", "''")
    a_path = str(paths.articles).replace("'", "''")
    start, cutoff = _sql_timestamp(history_start), _sql_timestamp(as_of)
    end = _sql_timestamp(as_of + timedelta(days=HORIZON_DAYS))
    sampling = ""
    if sample_modulus is not None:
        sampling = f"WHERE abs(hash(customer_id)) % {int(sample_modulus)} = 0"
    future = (
        f""", future AS (
        SELECT customer_id, 1 label_repeat, count(*) label_lines, sum(price) label_value
        FROM read_parquet('{t_path}')
        WHERE t_dat >= TIMESTAMP '{cutoff}' AND t_dat < TIMESTAMP '{end}'
        GROUP BY 1)"""
        if include_labels
        else ""
    )
    label_select = (
        ", coalesce(f.label_repeat,0)::INTEGER label_repeat, "
        "coalesce(f.label_lines,0)::BIGINT label_lines, "
        "coalesce(f.label_value,0)::DOUBLE label_value"
        if include_labels
        else ""
    )
    label_join = "LEFT JOIN future f USING(customer_id)" if include_labels else ""
    query = f"""
    WITH history AS (
      SELECT t.t_dat, t.customer_id, t.article_id, t.price, t.sales_channel_id,
             a.product_group_name
      FROM read_parquet('{t_path}') t
      LEFT JOIN read_parquet('{a_path}') a USING(article_id)
      WHERE t.t_dat >= TIMESTAMP '{start}' AND t.t_dat < TIMESTAMP '{cutoff}'
        AND t.customer_id IS NOT NULL AND t.article_id IS NOT NULL AND t.price IS NOT NULL
    ), daily AS (
      SELECT customer_id, t_dat, count(*) lines,
             lag(t_dat) OVER (PARTITION BY customer_id ORDER BY t_dat) previous_day
      FROM history GROUP BY 1,2
    ), cadence AS (
      SELECT customer_id, avg(date_diff('day', previous_day, t_dat)) mean_gap_days,
             stddev_pop(date_diff('day', previous_day, t_dat)) gap_std_days
      FROM daily WHERE previous_day IS NOT NULL GROUP BY 1
    ), states AS (
      SELECT customer_id, min(t_dat) first_seen, max(t_dat) last_seen,
        date_diff('day', max(t_dat), TIMESTAMP '{cutoff}')::DOUBLE recency_days,
        date_diff('day', min(t_dat), TIMESTAMP '{cutoff}')::DOUBLE customer_age_days,
        count(*) FILTER (WHERE t_dat >= TIMESTAMP '{cutoff}' - INTERVAL 7 DAY)::DOUBLE lines_7d,
        count(*) FILTER (WHERE t_dat >= TIMESTAMP '{cutoff}' - INTERVAL 30 DAY)::DOUBLE lines_30d,
        count(*) FILTER (WHERE t_dat >= TIMESTAMP '{cutoff}' - INTERVAL 60 DAY)::DOUBLE lines_60d,
        count(*) FILTER (WHERE t_dat >= TIMESTAMP '{cutoff}' - INTERVAL 90 DAY)::DOUBLE lines_90d,
        count(*) FILTER (WHERE t_dat >= TIMESTAMP '{cutoff}' - INTERVAL 180 DAY)::DOUBLE lines_180d,
        count(DISTINCT t_dat)::DOUBLE active_days,
        count(DISTINCT t_dat) FILTER (WHERE t_dat >= TIMESTAMP '{cutoff}' - INTERVAL 30 DAY)::DOUBLE active_days_30d,
        count(DISTINCT t_dat) FILTER (WHERE t_dat >= TIMESTAMP '{cutoff}' - INTERVAL 90 DAY)::DOUBLE active_days_90d,
        sum(price)::DOUBLE value_total,
        coalesce(sum(price) FILTER (WHERE t_dat >= TIMESTAMP '{cutoff}' - INTERVAL 30 DAY),0)::DOUBLE value_30d,
        coalesce(sum(price) FILTER (WHERE t_dat >= TIMESTAMP '{cutoff}' - INTERVAL 90 DAY),0)::DOUBLE value_90d,
        coalesce(sum(price) FILTER (WHERE t_dat >= TIMESTAMP '{cutoff}' - INTERVAL 180 DAY),0)::DOUBLE value_180d,
        avg(price)::DOUBLE mean_line_value, median(price)::DOUBLE median_line_value,
        (sum(price) / greatest(count(DISTINCT t_dat),1))::DOUBLE value_per_active_day,
        count(DISTINCT article_id)::DOUBLE unique_articles,
        count(DISTINCT product_group_name)::DOUBLE product_group_diversity,
        avg((sales_channel_id=2)::INTEGER)::DOUBLE online_share,
        count(*)::DOUBLE observation_count
      FROM history GROUP BY 1
    ) {future}
    SELECT s.customer_id, s.* EXCLUDE(customer_id),
      coalesce(c.mean_gap_days,0)::DOUBLE mean_gap_days,
      coalesce(c.gap_std_days,0)::DOUBLE gap_std_days,
      (s.lines_30d - (s.lines_90d-s.lines_30d)/2)::DOUBLE recent_line_change,
      (s.value_30d - (s.value_90d-s.value_30d)/2)::DOUBLE recent_value_change,
      least(date_diff('day', TIMESTAMP '{start}', TIMESTAMP '{cutoff}'), s.customer_age_days)::DOUBLE history_depth_days,
      (s.observation_count/(s.observation_count+20))::DOUBLE state_reliability,
      (s.observation_count < 5)::INTEGER sparse_history,
      coalesce(m.age,0)::DOUBLE age, (m.age IS NULL)::INTEGER age_missing,
      (m.club_member_status='ACTIVE')::INTEGER club_active,
      (lower(coalesce(m.fashion_news_frequency,''))='regularly')::INTEGER fashion_news_regularly,
      CASE WHEN s.customer_age_days <= 30 THEN 'NEW'
           WHEN s.recency_days <= 30 THEN 'ACTIVE'
           WHEN s.recency_days <= 90 THEN 'COOLING'
           ELSE 'DORMANT' END lifecycle
      {label_select}
    FROM states s LEFT JOIN cadence c USING(customer_id)
    LEFT JOIN read_parquet('{c_path}') m USING(customer_id)
    {label_join}
    {sampling}
    ORDER BY s.customer_id
    """
    connection = duckdb.connect()
    connection.execute("SET threads TO 4")
    frame = connection.execute(query).fetchdf()
    connection.close()
    return frame


def assert_state_is_leak_safe(
    frame: pd.DataFrame, *, history_start: datetime, as_of: datetime
) -> None:
    if frame.empty:
        raise ValueError("state frame is empty")
    if (pd.to_datetime(frame["first_seen"]) < pd.Timestamp(history_start)).any():
        raise AssertionError("state contains data older than imported history")
    if (pd.to_datetime(frame["last_seen"]) >= pd.Timestamp(as_of)).any():
        raise AssertionError("target-window data entered state")


def calibration_metrics(y: np.ndarray, probability: np.ndarray) -> dict[str, Any]:
    probability = np.clip(np.asarray(probability, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, int)
    order = np.argsort(probability)
    chunks = np.array_split(order, 10)
    rows: list[dict[str, float | int]] = []
    for index, selected in enumerate(chunks, start=1):
        if len(selected) == 0:
            continue
        rows.append(
            {
                "decile": index,
                "customers": int(len(selected)),
                "predicted_rate": float(probability[selected].mean()),
                "actual_rate": float(y[selected].mean()),
            }
        )
    ece = sum(
        row["customers"] / len(y) * abs(row["predicted_rate"] - row["actual_rate"])
        for row in rows
    )
    logits = np.log(probability / (1 - probability)).reshape(-1, 1)
    try:
        calibrator = LogisticRegression(C=1e6, max_iter=500).fit(logits, y)
        intercept = float(calibrator.intercept_[0])
        slope = float(calibrator.coef_[0, 0])
    except ValueError:
        intercept, slope = float("nan"), float("nan")
    fraction_positive, mean_predicted = calibration_curve(y, probability, n_bins=10)
    return {
        "ece": float(ece),
        "mce": float(max(abs(row["predicted_rate"] - row["actual_rate"]) for row in rows)),
        "calibration_intercept": intercept,
        "calibration_slope": slope,
        "deciles": rows,
        "reliability": [
            {"predicted": float(pred), "actual": float(actual)}
            for pred, actual in zip(mean_predicted, fraction_positive, strict=True)
        ],
    }


def prediction_metrics(y: np.ndarray, probability: np.ndarray) -> dict[str, Any]:
    probability = np.clip(np.asarray(probability, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, int)
    actual = int(y.sum())
    predicted = float(probability.sum())
    prevalence = float(y.mean())
    ranked = np.argsort(-probability)
    result: dict[str, Any] = {
        "auroc": float(roc_auc_score(y, probability)),
        "pr_auc": float(average_precision_score(y, probability)),
        "brier": float(brier_score_loss(y, probability)),
        "log_loss": float(log_loss(y, probability)),
        "repeat_buyers_predicted": predicted,
        "repeat_buyers_actual": actual,
        "buyer_count_absolute_error": abs(predicted - actual),
        "buyer_count_error": abs(predicted - actual) / max(actual, 1),
    }
    for fraction in (0.05, 0.10, 0.20):
        count = max(1, int(len(y) * fraction))
        rate = float(y[ranked[:count]].mean())
        result[f"lift_at_{int(fraction * 100)}"] = rate / max(prevalence, 1e-12)
        result[f"precision_at_{int(fraction * 100)}"] = rate
    result.update(calibration_metrics(y, probability))
    return result


class ProbabilityModel(Protocol):
    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray: ...


@dataclass
class ConstantModel:
    rate: float

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        return np.full(len(frame), self.rate)


@dataclass
class SklearnModel:
    estimator: Any
    columns: tuple[str, ...]

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.estimator.predict_proba(frame[list(self.columns)].fillna(0))[:, 1])


@dataclass
class BucketRateModel:
    rates: dict[str, float]
    prior: float

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        return np.asarray([self.rates.get(str(item), self.prior) for item in frame["lifecycle"]])


def fit_candidate(name: str, train: pd.DataFrame) -> ProbabilityModel:
    y = train["label_repeat"].to_numpy(int)
    if name == "population_rate":
        return ConstantModel(float(y.mean()))
    if name == "empirical_bayes_lifecycle":
        totals = train.groupby("lifecycle")["label_repeat"].agg(["sum", "count"])
        prior = float(y.mean())
        rates = {
            str(index): float((row["sum"] + 20 * prior) / (row["count"] + 20))
            for index, row in totals.iterrows()
        }
        return BucketRateModel(rates, prior)
    columns: tuple[str, ...] = RECENCY_COLUMNS if name == "recency_logistic" else RFM_COLUMNS
    if name in {"logistic", "gradient_boosting"}:
        columns = FEATURE_COLUMNS
    if name in {"recency_logistic", "rfm_logistic", "logistic"}:
        estimator = make_pipeline(
            StandardScaler(), LogisticRegression(C=0.1, max_iter=1000, random_state=RANDOM_SEED)
        ).fit(train[list(columns)].fillna(0), y)
    elif name == "gradient_boosting":
        estimator = HistGradientBoostingClassifier(
            max_iter=100, max_leaf_nodes=15, learning_rate=0.06,
            l2_regularization=2.0, random_state=RANDOM_SEED,
        ).fit(train[list(columns)].fillna(0), y)
    else:
        raise ValueError(f"unknown model {name}")
    return SklearnModel(estimator, tuple(columns))


@dataclass
class ProbabilityCalibrator:
    method: str
    model: Any | None = None

    def fit(self, probability: np.ndarray, y: np.ndarray) -> ProbabilityCalibrator:
        probability = np.clip(probability, 1e-6, 1 - 1e-6)
        if self.method == "none":
            return self
        if self.method == "platt":
            score = np.log(probability / (1 - probability)).reshape(-1, 1)
            self.model = LogisticRegression(C=1.0, random_state=RANDOM_SEED).fit(score, y)
        elif self.method == "isotonic":
            self.model = IsotonicRegression(out_of_bounds="clip").fit(probability, y)
        else:
            raise ValueError(f"unknown calibration method {self.method}")
        return self

    def transform(self, probability: np.ndarray) -> np.ndarray:
        probability = np.clip(probability, 1e-6, 1 - 1e-6)
        if self.method == "none":
            return probability
        if self.method == "platt":
            if self.model is None:
                raise RuntimeError("calibrator is not fitted")
            score = np.log(probability / (1 - probability)).reshape(-1, 1)
            return np.asarray(self.model.predict_proba(score)[:, 1])
        if self.model is None:
            raise RuntimeError("calibrator is not fitted")
        return np.asarray(self.model.predict(probability))


def split_training_snapshots(
    frames: list[pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(frames) < 2:
        raise ValueError("at least two chronological training snapshots are required")
    return pd.concat(frames[:-1], ignore_index=True), frames[-1]


def select_model(development: pd.DataFrame) -> dict[str, Any]:
    """Apply the preregistered calibration/aggregate guardrails to dev results only."""
    grouped = development.groupby(["model", "calibration"], as_index=False).agg(
        mean_ece=("ece", "mean"),
        mean_brier=("brier", "mean"),
        mean_buyer_error=("buyer_count_error", "mean"),
        catastrophic_buyer_errors=("buyer_count_error", lambda value: int((value > 0.20).sum())),
        mean_auroc=("auroc", "mean"),
        windows=("cutoff", "nunique"),
    )
    eligible = grouped[
        (grouped["mean_ece"] <= 0.05) & (grouped["catastrophic_buyer_errors"] == 0)
    ]
    fallback = False
    if eligible.empty:
        eligible = grouped[grouped["mean_ece"] <= 0.05]
        fallback = True
    if eligible.empty:
        eligible = grouped
        fallback = True
    winner = eligible.sort_values(
        ["mean_brier", "mean_buyer_error", "mean_auroc"], ascending=[True, True, False]
    ).iloc[0]
    return {
        "model": str(winner["model"]),
        "calibration": str(winner["calibration"]),
        "fallback_used": fallback,
        "development_metrics": {
            key: float(winner[key])
            for key in ("mean_ece", "mean_brier", "mean_buyer_error", "mean_auroc")
        },
        "test_metrics_used_for_selection": False,
    }


def monetary_fit_predict(
    train: pd.DataFrame, test: pd.DataFrame, probability: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]]:
    buyers = train[train["label_repeat"] == 1]
    global_median = float(buyers["label_value"].median())
    estimator = HistGradientBoostingRegressor(
        loss="absolute_error", max_iter=80, max_leaf_nodes=15, random_state=RANDOM_SEED
    ).fit(buyers[list(FEATURE_COLUMNS)].fillna(0), buyers["label_value"])
    conditional = np.maximum(
        estimator.predict(test[list(FEATURE_COLUMNS)].fillna(0)), 0
    )
    expected = probability * conditional
    actual_buyer_value = test.loc[test["label_repeat"] == 1, "label_value"].to_numpy(float)
    predicted_buyer_value = conditional[test["label_repeat"].to_numpy(int) == 1]
    return expected, {
        "conditional_model": "hist_gradient_boosting_absolute_error",
        "global_buyer_median": global_median,
        "buyer_mae": float(mean_absolute_error(actual_buyer_value, predicted_buyer_value)),
        "buyer_median_absolute_error": float(
            median_absolute_error(actual_buyer_value, predicted_buyer_value)
        ),
        "conditional_bias": float((predicted_buyer_value - actual_buyer_value).mean()),
        "transaction_value_predicted": float(expected.sum()),
        "transaction_value_actual": float(test["label_value"].sum()),
        "transaction_value_error": float(
            abs(expected.sum() - test["label_value"].sum())
            / max(float(test["label_value"].sum()), 1e-12)
        ),
    }


def subgroup_metrics(frame: pd.DataFrame, probability: np.ndarray) -> list[dict[str, Any]]:
    working = frame.copy()
    working["probability"] = probability
    working["history_support"] = np.where(working["observation_count"] < 5, "SPARSE", "RICH")
    working["dominant_channel"] = np.where(working["online_share"] >= 0.5, "CHANNEL_2", "CHANNEL_1")
    working["age_band"] = pd.cut(
        working["age"], bins=[-1, 0, 24, 34, 44, 54, 64, 200],
        labels=["MISSING", "16-24", "25-34", "35-44", "45-54", "55-64", "65+"],
    ).astype(str)
    rows: list[dict[str, Any]] = []
    for column in ("lifecycle", "history_support", "dominant_channel", "age_band"):
        for value, group in working.groupby(column):
            if len(group) < 1000 or group["label_repeat"].nunique() < 2:
                continue
            metric = prediction_metrics(group["label_repeat"].to_numpy(), group["probability"].to_numpy())
            rows.append({"subgroup_type": column, "subgroup": str(value), "n": len(group), **metric})
    return rows


def bootstrap_intervals(
    y: np.ndarray, probability: np.ndarray, value: np.ndarray, expected_value: np.ndarray,
    *, replicates: int = 100, seed: int = RANDOM_SEED,
) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    n = len(y)
    buyer_errors, aucs, briers, value_errors = [], [], [], []
    for _ in range(replicates):
        index = rng.integers(0, n, n)
        y_b, p_b = y[index], probability[index]
        actual = max(float(y_b.sum()), 1.0)
        buyer_errors.append(abs(float(p_b.sum()) - actual) / actual)
        if np.unique(y_b).size == 2:
            aucs.append(float(roc_auc_score(y_b, p_b)))
        briers.append(float(brier_score_loss(y_b, p_b)))
        actual_value = max(float(value[index].sum()), 1e-12)
        value_errors.append(abs(float(expected_value[index].sum()) - actual_value) / actual_value)
    def interval(items: list[float]) -> list[float]:
        return [float(np.quantile(items, 0.05)), float(np.quantile(items, 0.95))]
    return {
        "buyer_count_error_90": interval(buyer_errors),
        "auroc_90": interval(aucs),
        "brier_90": interval(briers),
        "transaction_value_error_90": interval(value_errors),
    }


def readiness_verdict(metrics: dict[str, Any], baseline: dict[str, Any]) -> str:
    strong = (
        metrics["auroc"] >= 0.80
        and metrics["auroc"] > baseline["auroc"]
        and metrics["ece"] <= 0.03
        and metrics["brier"] < baseline["brier"]
        and metrics["buyer_count_error"] <= 0.10
        and metrics["lift_at_10"] >= 2.0
    )
    promising = (
        metrics["auroc"] >= 0.75
        and metrics["ece"] <= 0.05
        and metrics["buyer_count_error"] <= 0.15
        and metrics["lift_at_10"] >= 1.5
        and metrics["brier"] < baseline["brier"]
    )
    return "STRONG" if strong else "PROMISING" if promising else "FAIL"
