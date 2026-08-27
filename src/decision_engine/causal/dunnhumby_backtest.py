# ruff: noqa: E501
"""Preregistered chronological observational Dunnhumby campaign backtest."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = (
    "recency_days",
    "orders_30d",
    "orders_90d",
    "orders_180d",
    "historical_orders",
    "spend_30d",
    "spend_90d",
    "spend_180d",
    "historical_spend",
    "historical_units",
    "aov",
    "product_diversity",
    "retail_discount",
    "coupon_discount",
    "customer_age_days",
)


@dataclass(frozen=True)
class FrozenDunnhumbyPrediction:
    campaign_id: str
    start_date: datetime
    frame: pd.DataFrame
    propensity: np.ndarray
    m0: np.ndarray
    m1: np.ndarray
    predicted_uplift: np.ndarray
    fraction_clipped: float
    overlap_fraction: float
    treated_ess: float
    control_ess: float
    max_smd_before: float
    max_smd_after: float


def _path(path: Path) -> str:
    return str(path).replace("'", "''")


def campaign_metadata(processed_dir: str | Path) -> tuple[pd.DataFrame, datetime, datetime]:
    root = Path(processed_dir)
    connection = duckdb.connect()
    descriptions = connection.execute(
        f"""
        SELECT CAMPAIGN campaign_id, CAST(START_DATE AS TIMESTAMP) start_date,
          CAST(END_DATE AS TIMESTAMP) end_date
        FROM read_parquet('{_path(root / "campaign_desc.parquet")}')
        ORDER BY start_date, campaign_id
        """
    ).fetchdf()
    bounds = connection.execute(
        f"""
        SELECT min(CAST(TRANSACTION_TIMESTAMP AS TIMESTAMP)),
               max(CAST(TRANSACTION_TIMESTAMP AS TIMESTAMP))
        FROM read_parquet('{_path(root / "transaction_data.parquet")}')
        """
    ).fetchone()
    connection.close()
    if bounds is None:
        raise ValueError("transaction bounds unavailable")
    descriptions["start_date"] = pd.to_datetime(descriptions["start_date"])
    descriptions["end_date"] = pd.to_datetime(descriptions["end_date"])
    return (
        descriptions,
        pd.Timestamp(bounds[0]).to_pydatetime(),
        pd.Timestamp(bounds[1]).to_pydatetime(),
    )


def preregistered_split(
    descriptions: pd.DataFrame, transaction_min: datetime, transaction_max: datetime
) -> tuple[datetime, pd.DataFrame, pd.DataFrame]:
    unique_starts = sorted(pd.to_datetime(descriptions["start_date"]).unique())
    percentile = pd.Series(unique_starts).quantile(0.70, interpolation="linear")
    cutoff = min(value for value in unique_starts if value >= percentile)
    complete = descriptions[
        (descriptions["start_date"] > transaction_min)
        & (descriptions["start_date"] + pd.Timedelta(days=30) <= transaction_max)
    ].copy()
    development = complete[complete["start_date"] < cutoff].copy()
    backtest = complete[complete["start_date"] >= cutoff].copy()
    return pd.Timestamp(cutoff).to_pydatetime(), development, backtest


def campaign_support(processed_dir: str | Path, campaign_ids: list[str]) -> pd.DataFrame:
    root = Path(processed_dir)
    placeholders = ",".join("?" for _ in campaign_ids)
    connection = duckdb.connect()
    frame = connection.execute(
        f"""
        SELECT CAMPAIGN campaign_id, count(distinct HOUSEHOLD_KEY) treated_households
        FROM read_parquet('{_path(root / "campaign_table.parquet")}')
        WHERE CAMPAIGN IN ({placeholders}) GROUP BY 1 ORDER BY treated_households DESC, campaign_id
        """,
        campaign_ids,
    ).fetchdf()
    connection.close()
    return frame


def build_pre_exposure_frame(
    processed_dir: str | Path, campaign_id: str, start_date: datetime
) -> pd.DataFrame:
    root = Path(processed_dir)
    connection = duckdb.connect()
    frame = connection.execute(
        f"""
        WITH transactions AS (
          SELECT CAST(HOUSEHOLD_KEY AS VARCHAR) household_id,
            CAST(BASKET_ID AS VARCHAR) basket_id, CAST(PRODUCT_ID AS VARCHAR) product_id,
            CAST(TRANSACTION_TIMESTAMP AS TIMESTAMP) event_time,
            CAST(QUANTITY AS DOUBLE) quantity, CAST(SALES_VALUE AS DOUBLE) sales_value,
            abs(CAST(RETAIL_DISC AS DOUBLE)) retail_disc,
            abs(CAST(COUPON_DISC AS DOUBLE)) coupon_disc
          FROM read_parquet('{_path(root / "transaction_data.parquet")}')
        ), households AS (SELECT DISTINCT household_id FROM transactions),
        history AS (SELECT * FROM transactions WHERE event_time < ?),
        state AS (
          SELECT h.household_id,
            coalesce(date_diff('day',max(x.event_time),?),999)::DOUBLE recency_days,
            count(distinct x.basket_id) FILTER (WHERE x.event_time>=?-INTERVAL 30 DAY)::DOUBLE orders_30d,
            count(distinct x.basket_id) FILTER (WHERE x.event_time>=?-INTERVAL 90 DAY)::DOUBLE orders_90d,
            count(distinct x.basket_id) FILTER (WHERE x.event_time>=?-INTERVAL 180 DAY)::DOUBLE orders_180d,
            count(distinct x.basket_id)::DOUBLE historical_orders,
            coalesce(sum(x.sales_value) FILTER (WHERE x.event_time>=?-INTERVAL 30 DAY),0)::DOUBLE spend_30d,
            coalesce(sum(x.sales_value) FILTER (WHERE x.event_time>=?-INTERVAL 90 DAY),0)::DOUBLE spend_90d,
            coalesce(sum(x.sales_value) FILTER (WHERE x.event_time>=?-INTERVAL 180 DAY),0)::DOUBLE spend_180d,
            coalesce(sum(x.sales_value),0)::DOUBLE historical_spend,
            coalesce(sum(x.quantity),0)::DOUBLE historical_units,
            coalesce(sum(x.sales_value)/nullif(count(distinct x.basket_id),0),0)::DOUBLE aov,
            count(distinct x.product_id)::DOUBLE product_diversity,
            coalesce(sum(x.retail_disc),0)::DOUBLE retail_discount,
            coalesce(sum(x.coupon_disc),0)::DOUBLE coupon_discount,
            coalesce(date_diff('day',min(x.event_time),?),0)::DOUBLE customer_age_days
          FROM households h LEFT JOIN history x USING(household_id) GROUP BY 1
        ), treated AS (
          SELECT DISTINCT CAST(HOUSEHOLD_KEY AS VARCHAR) household_id
          FROM read_parquet('{_path(root / "campaign_table.parquet")}') WHERE CAMPAIGN=?
        )
        SELECT s.*, (t.household_id IS NOT NULL)::INTEGER treatment
        FROM state s LEFT JOIN treated t USING(household_id) ORDER BY s.household_id
        """,
        [start_date] * 9 + [campaign_id],
    ).fetchdf()
    connection.close()
    return frame


def reveal_outcome(
    processed_dir: str | Path, households: list[str], start_date: datetime
) -> np.ndarray:
    root = Path(processed_dir)
    connection = duckdb.connect()
    outcomes = connection.execute(
        f"""
        SELECT DISTINCT CAST(HOUSEHOLD_KEY AS VARCHAR) household_id
        FROM read_parquet('{_path(root / "transaction_data.parquet")}')
        WHERE CAST(TRANSACTION_TIMESTAMP AS TIMESTAMP)>=?
          AND CAST(TRANSACTION_TIMESTAMP AS TIMESTAMP)<?+INTERVAL 30 DAY
        """,
        [start_date, start_date],
    ).fetchdf()
    connection.close()
    purchased = set(outcomes["household_id"].astype(str))
    return np.array([int(value in purchased) for value in households], dtype=int)


def _ess(weights: np.ndarray) -> float:
    return float(weights.sum() ** 2 / max(float(np.square(weights).sum()), 1e-12))


def _max_smd(x: np.ndarray, treatment: np.ndarray, weights: np.ndarray | None = None) -> float:
    t = treatment == 1
    c = ~t
    if weights is None:
        wt, wc = np.ones(t.sum()), np.ones(c.sum())
    else:
        wt, wc = weights[t], weights[c]
    mean_t = np.average(x[t], axis=0, weights=wt)
    mean_c = np.average(x[c], axis=0, weights=wc)
    var_t = np.average(np.square(x[t] - mean_t), axis=0, weights=wt)
    var_c = np.average(np.square(x[c] - mean_c), axis=0, weights=wc)
    return float(np.max(np.abs(mean_t - mean_c) / np.sqrt((var_t + var_c) / 2 + 1e-12)))


def fit_and_freeze(
    development: pd.DataFrame,
    development_outcome: np.ndarray,
    final: pd.DataFrame,
    *,
    campaign_id: str,
    start_date: datetime,
    seed: int = 42,
) -> FrozenDunnhumbyPrediction:
    x_dev = development[list(FEATURES)].fillna(0).to_numpy(float)
    t_dev = development["treatment"].to_numpy(int)
    x_final = final[list(FEATURES)].fillna(0).to_numpy(float)
    t_final = final["treatment"].to_numpy(int)
    propensity = np.zeros(len(final), dtype=float)
    splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    for train, validation in splitter.split(x_final, t_final):
        propensity_model = make_pipeline(
            StandardScaler(), LogisticRegression(C=0.2, max_iter=2_000, random_state=seed)
        ).fit(x_final[train], t_final[train])
        propensity[validation] = propensity_model.predict_proba(x_final[validation])[:, 1]
    predictions: dict[int, np.ndarray] = {}
    for arm in (0, 1):
        selected = t_dev == arm
        model = make_pipeline(
            StandardScaler(), LogisticRegression(C=0.2, max_iter=2_000, random_state=seed)
        ).fit(x_dev[selected], development_outcome[selected])
        predictions[arm] = model.predict_proba(x_final)[:, 1]
    clipped = np.clip(propensity, 0.02, 0.98)
    weights = t_final / clipped + (1 - t_final) / (1 - clipped)
    return FrozenDunnhumbyPrediction(
        campaign_id=campaign_id,
        start_date=start_date,
        frame=final,
        propensity=propensity,
        m0=predictions[0],
        m1=predictions[1],
        predicted_uplift=predictions[1] - predictions[0],
        fraction_clipped=float(np.mean(propensity != clipped)),
        overlap_fraction=float(np.mean((propensity >= 0.05) & (propensity <= 0.95))),
        treated_ess=_ess(weights[t_final == 1]),
        control_ess=_ess(weights[t_final == 0]),
        max_smd_before=_max_smd(x_final, t_final),
        max_smd_after=_max_smd(x_final, t_final, weights),
    )


def evaluate_frozen(frozen: FrozenDunnhumbyPrediction, outcome: np.ndarray) -> dict[str, object]:
    treatment = frozen.frame["treatment"].to_numpy(int)
    propensity = np.clip(frozen.propensity, 0.02, 0.98)
    pseudo = (
        frozen.m1
        - frozen.m0
        + treatment * (outcome - frozen.m1) / propensity
        - (1 - treatment) * (outcome - frozen.m0) / (1 - propensity)
    )
    ate = float(pseudo.mean())
    standard_error = float(pseudo.std(ddof=1) / np.sqrt(len(pseudo)))
    naive = float(outcome[treatment == 1].mean() - outcome[treatment == 0].mean())
    quantiles = pd.qcut(frozen.predicted_uplift, 5, labels=False, duplicates="drop")
    calibration = [
        {
            "group": int(group) + 1,
            "households": int(np.sum(quantiles == group)),
            "predicted_uplift": float(frozen.predicted_uplift[quantiles == group].mean()),
            "realized_dr_effect": float(pseudo[quantiles == group].mean()),
        }
        for group in sorted(np.unique(quantiles))
    ]
    return {
        "naive_ate": naive,
        "adjusted_ate": ate,
        "standard_error": standard_error,
        "lower": ate - 1.96 * standard_error,
        "upper": ate + 1.96 * standard_error,
        "uplift_calibration": calibration,
    }


def deterministic_aa(
    household_ids: list[str], outcome: np.ndarray, treatment: np.ndarray
) -> dict[str, float | int | bool]:
    selected = treatment == 1
    ids = np.asarray(household_ids)[selected]
    y = outcome[selected]
    assignment = np.array(
        [
            int.from_bytes(hashlib.sha256(f"dunnhumby-aa:{value}".encode()).digest()[:8], "big") % 2
            for value in ids
        ]
    )
    y1, y0 = y[assignment == 1], y[assignment == 0]
    difference = float(y1.mean() - y0.mean())
    variance = y1.var(ddof=1) / len(y1) + y0.var(ddof=1) / len(y0)
    z = difference / np.sqrt(max(variance, 1e-12))
    return {
        "arm_one": int(len(y1)),
        "arm_zero": int(len(y0)),
        "difference": difference,
        "p_value": float(2 * norm.sf(abs(z))),
    }
