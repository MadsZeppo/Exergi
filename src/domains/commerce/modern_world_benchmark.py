from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from commercial_twin.world_state import CachedWorldStateProvider
from decision_engine.registry import ModelPerformanceRegistry


@dataclass(frozen=True)
class ModernWorldBenchmarkConfig:
    seed: int = 42
    rows_per_month: int = 120
    development_end: datetime = datetime(2025, 7, 1, tzinfo=UTC)
    final_start: datetime = datetime(2025, 8, 1, tzinfo=UTC)
    output_dir: Path = Path("artifacts/world_state/ablation/modern-synthetic-v1")


def _sample_weights(dates: np.ndarray, half_life_months: int | None) -> np.ndarray:
    if half_life_months is None:
        return np.ones(len(dates))
    latest = dates.max()
    age_days = (latest - dates).astype("timedelta64[D]").astype(float)
    return np.power(0.5, age_days / (half_life_months * 30.4375))


def _monthly_world(provider: CachedWorldStateProvider) -> pl.DataFrame:
    cpi_definition = next(
        item for item in provider.definitions if item.signal_family == "category_cpi"
    )
    gas_definition = next(
        item
        for item in provider.definitions
        if item.signal_family == "gas_price" and item.geography == "US"
    )
    cpi = provider._load(cpi_definition).filter(  # noqa: SLF001
        pl.col("observation_period") >= datetime(2023, 1, 1, tzinfo=UTC)
    )
    gas = (
        provider._load(gas_definition)  # noqa: SLF001
        .filter(pl.col("observation_period") >= datetime(2023, 1, 1, tzinfo=UTC))
        .with_columns(pl.col("observation_period").dt.truncate("1mo").alias("month"))
        .group_by("month")
        .agg(pl.col("value").mean().alias("gas_price"))
    )
    return (
        cpi.with_columns(pl.col("observation_period").dt.truncate("1mo").alias("month"))
        .select("month", pl.col("value").alias("category_cpi"))
        .join(gas, on="month", how="inner")
        .sort("month")
    )


def _synthetic_behavior(monthly: pl.DataFrame, rows_per_month: int, seed: int) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    dates = np.repeat(monthly["month"].to_numpy(), rows_per_month)
    cpi = np.repeat(monthly["category_cpi"].to_numpy(), rows_per_month)
    gas = np.repeat(monthly["gas_price"].to_numpy(), rows_per_month)
    customer_value = rng.lognormal(mean=3.4, sigma=0.45, size=len(dates))
    recency = rng.exponential(35, size=len(dates))
    action = rng.integers(0, 2, size=len(dates))
    cpi_z = (cpi - np.mean(cpi)) / np.std(cpi)
    gas_z = (gas - np.mean(gas)) / np.std(gas)
    baseline = 1.5 + 0.035 * customer_value - 0.012 * recency - 0.20 * cpi_z
    treatment_effect = 0.35 - 0.28 * cpi_z + 0.18 * gas_z
    noise = rng.normal(0, 0.45, size=len(dates))
    outcome = baseline + action * treatment_effect + noise
    return pl.DataFrame(
        {
            "date": dates,
            "customer_value": customer_value,
            "recency_days": recency,
            "action": action,
            "category_cpi": cpi,
            "gas_price": gas,
            "outcome": outcome,
            "oracle_y0": baseline,
            "oracle_y1": baseline + treatment_effect,
        }
    ).with_columns(pl.col("date").dt.replace_time_zone("UTC"))


def _evaluate(
    train: pl.DataFrame,
    evaluation: pl.DataFrame,
    features: list[str],
    half_life: int | None,
    seed: int,
) -> dict[str, float]:
    weights = _sample_weights(train["date"].to_numpy(), half_life)
    model = HistGradientBoostingRegressor(
        max_iter=100, max_leaf_nodes=15, min_samples_leaf=30, random_state=seed
    ).fit(train.select(features).to_numpy(), train["outcome"].to_numpy(), sample_weight=weights)
    prediction = model.predict(evaluation.select(features).to_numpy())
    action_index = features.index("action")
    x0 = evaluation.select(features).to_numpy()
    x1 = x0.copy()
    x0[:, action_index] = 0
    x1[:, action_index] = 1
    predicted_policy = (model.predict(x1) > model.predict(x0)).astype(int)
    oracle_policy = (
        evaluation["oracle_y1"].to_numpy() > evaluation["oracle_y0"].to_numpy()
    ).astype(int)
    oracle_best = np.maximum(evaluation["oracle_y0"].to_numpy(), evaluation["oracle_y1"].to_numpy())
    policy_outcome = np.where(
        predicted_policy == 1,
        evaluation["oracle_y1"].to_numpy(),
        evaluation["oracle_y0"].to_numpy(),
    )
    return {
        "mae": float(mean_absolute_error(evaluation["outcome"].to_numpy(), prediction)),
        "rmse": float(root_mean_squared_error(evaluation["outcome"].to_numpy(), prediction)),
        "policy_accuracy": float(np.mean(predicted_policy == oracle_policy)),
        "oracle_policy_regret": float(np.mean(oracle_best - policy_outcome)),
    }


def run_modern_world_benchmark(
    config: ModernWorldBenchmarkConfig | None = None,
) -> dict[str, Any]:
    config = config or ModernWorldBenchmarkConfig()
    monthly = _monthly_world(CachedWorldStateProvider())
    frame = _synthetic_behavior(monthly, config.rows_per_month, config.seed)
    development_train = frame.filter(pl.col("date") < config.development_end)
    development = frame.filter(
        (pl.col("date") >= config.development_end) & (pl.col("date") < config.final_start)
    )
    final = frame.filter(pl.col("date") >= config.final_start)
    base_features = ["customer_value", "recency_days", "action"]
    world_features = base_features + ["category_cpi", "gas_price"]
    policies: tuple[int | None, ...] = (None, 6, 12, 24)
    development_results = {
        str(policy or "no_decay"): _evaluate(
            development_train, development, world_features, policy, config.seed
        )
        for policy in policies
    }
    selected_label = min(development_results, key=lambda label: development_results[label]["mae"])
    selected_half_life = None if selected_label == "no_decay" else int(selected_label)
    final_train = frame.filter(pl.col("date") < config.final_start)
    final_results = {
        "customer_company_only": _evaluate(
            final_train, final, base_features, selected_half_life, config.seed
        ),
        "customer_company_world": _evaluate(
            final_train, final, world_features, selected_half_life, config.seed
        ),
    }
    result: dict[str, Any] = {
        "label": "SYNTHETIC BEHAVIOR — REAL WORLD SIGNALS",
        "commercial_validity": "NOT_ESTABLISHED",
        "world_signal_vintage_warning": (
            "current official caches may be latest-revised; used only as exogenous synthetic inputs"
        ),
        "rows": frame.height,
        "date_start": str(frame["date"].min()),
        "date_end": str(frame["date"].max()),
        "recency_selection_period": "development only",
        "recency_development_results": development_results,
        "selected_half_life_months": selected_half_life,
        "final_results": final_results,
    }
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    monthly.write_parquet(config.output_dir / "real_world_inputs.parquet")
    registry = ModelPerformanceRegistry(config.output_dir / "model_registry.duckdb")
    for model, metrics in final_results.items():
        record_id = f"modern-synthetic-v1:{model}:seed-{config.seed}"
        count_row = registry.connection.execute(
            "SELECT count(*) FROM behavior_model_tournament_v1 WHERE record_id = ?",
            [record_id],
        ).fetchone()
        exists = int(count_row[0]) if count_row is not None else 0
        if not exists:
            registry.append_behavior_model_result(
                record_id=record_id,
                decision_type="binary_coupon",
                data_regime="SYNTHETIC_BEHAVIOR_REAL_WORLD_SIGNALS",
                model=model,
                factual_error={"mae": metrics["mae"], "rmse": metrics["rmse"]},
                causal_error={"policy_accuracy": metrics["policy_accuracy"]},
                calibration={},
                economic_regret=metrics["oracle_policy_regret"],
                metadata={"commercial_validity": "NOT_ESTABLISHED"},
            )
    registry.close()
    return result
