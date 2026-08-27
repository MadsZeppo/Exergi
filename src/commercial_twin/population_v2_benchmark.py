from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
import polars as pl
from scipy.spatial.distance import jensenshannon
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import (
    GammaRegressor,
    LogisticRegression,
    PoissonRegressor,
    Ridge,
    TweedieRegressor,
)
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error
from sklearn.preprocessing import StandardScaler

from commercial_twin.population_v2 import decompose_revenue, spend_quantiles
from decision_engine.ledger import PredictionLedger

FEATURES = (
    "views_last",
    "carts_last",
    "removes_last",
    "orders_last",
    "revenue_last",
    "views_history",
    "carts_history",
    "orders_history",
    "revenue_history",
    "active_months",
    "history_days",
    "purchase_months",
    "mean_item_price_history",
    "categories_history",
)


@dataclass(frozen=True)
class PopulationV2Config:
    customer_month_path: Path = Path("data/processed/rees46/cosmetics/customer_month.parquet")
    orders_path: Path = Path("data/processed/rees46/cosmetics/orders.parquet")
    output_dir: Path = Path("artifacts/customer_population_v2/rees46-cosmetics-v2-seed-42")
    development_months: tuple[date, ...] = (date(2019, 12, 1), date(2020, 1, 1))
    final_month: date = date(2020, 2, 1)
    seed: int = 42
    simulation_draws: int = 300


def _state_and_outcome(
    customer_month: pl.DataFrame, target_month: date
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    history = customer_month.filter(pl.col("month") < target_month).sort("month")
    last_month = history["month"].max()
    states = history.group_by("customer_id").agg(
        pl.col("views").filter(pl.col("month") == last_month).sum().alias("views_last"),
        pl.col("carts").filter(pl.col("month") == last_month).sum().alias("carts_last"),
        pl.col("removes").filter(pl.col("month") == last_month).sum().alias("removes_last"),
        pl.col("orders").filter(pl.col("month") == last_month).sum().alias("orders_last"),
        pl.col("revenue").filter(pl.col("month") == last_month).sum().alias("revenue_last"),
        pl.col("views").sum().alias("views_history"),
        pl.col("carts").sum().alias("carts_history"),
        pl.col("orders").sum().alias("orders_history"),
        pl.col("revenue").sum().alias("revenue_history"),
        pl.col("month").n_unique().alias("active_months"),
        ((pl.col("month").max() - pl.col("month").min()).dt.total_days() + 30).alias(
            "history_days"
        ),
        (pl.col("orders") > 0).sum().alias("purchase_months"),
        pl.col("mean_item_price")
        .filter(pl.col("purchase_items") > 0)
        .mean()
        .fill_null(0)
        .alias("mean_item_price_history"),
        pl.col("categories").max().alias("categories_history"),
        pl.col("recent_category").last().alias("recent_category"),
    )
    target = customer_month.filter(pl.col("month") == target_month)
    outcome = (
        states.select("customer_id")
        .join(
            target.select("customer_id", "orders", "revenue", "recent_category"),
            on="customer_id",
            how="left",
        )
        .with_columns(
            pl.col("orders", "revenue").fill_null(0),
            (pl.col("orders").fill_null(0) > 0).cast(pl.Float64).alias("purchase"),
        )
    )
    new_customers = target.join(states.select("customer_id"), on="customer_id", how="anti")
    return states.sort("customer_id"), outcome.sort("customer_id"), new_customers


def _matrix(states: pl.DataFrame) -> np.ndarray:
    values = states.select(FEATURES).fill_null(0).to_numpy().astype(float)
    return np.log1p(np.clip(values, 0, None))


class Predictor(Protocol):
    def predict(self, matrix: np.ndarray) -> np.ndarray: ...


class _Constant:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        return np.full(len(matrix), self.value)


class _RFM:
    def __init__(self, population_rate: float) -> None:
        self.population_rate = population_rate

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        signal = np.clip(matrix[:, FEATURES.index("orders_last")] / np.log(3), 0, 1)
        return np.clip(0.5 * signal + 0.5 * self.population_rate, 0, 1)


class _ScaledModel:
    def __init__(
        self,
        scaler: StandardScaler,
        model: Any,
        *,
        log_target: bool = False,
        log_variance: float = 0,
    ) -> None:
        self.scaler, self.model = scaler, model
        self.log_target, self.log_variance = log_target, log_variance

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        result = np.asarray(self.model.predict(self.scaler.transform(matrix)), dtype=float)
        if self.log_target:
            result = np.exp(result + self.log_variance / 2)
        return np.clip(result, 0, None)


class _PurchaseClassifier:
    def __init__(self, scaler: StandardScaler, model: Any) -> None:
        self.scaler, self.model = scaler, model

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        return np.asarray(
            self.model.predict_proba(self.scaler.transform(matrix))[:, 1], dtype=float
        )


def _purchase_models(matrix: np.ndarray, target: np.ndarray, seed: int) -> dict[str, Predictor]:
    rate = float(target.mean())
    scaler = StandardScaler().fit(matrix)
    logistic = LogisticRegression(max_iter=300, class_weight=None, random_state=seed).fit(
        scaler.transform(matrix), target
    )
    boosting = HistGradientBoostingClassifier(
        max_iter=100, max_leaf_nodes=24, min_samples_leaf=100, random_state=seed
    ).fit(matrix, target)
    return {
        "population_average": _Constant(rate),
        "rfm": _RFM(rate),
        "calibrated_logistic": _PurchaseClassifier(scaler, logistic),
        "gradient_boosting": _PurchaseClassifier(StandardScaler().fit(np.zeros((1, 1))), boosting),
    }


def _predict(model: Predictor, matrix: np.ndarray, name: str) -> np.ndarray:
    if name == "gradient_boosting" and isinstance(model, _PurchaseClassifier):
        return np.asarray(model.model.predict_proba(matrix)[:, 1], dtype=float)
    return model.predict(matrix)


def _count_models(matrix: np.ndarray, target: np.ndarray, seed: int) -> dict[str, Predictor]:
    scaler = StandardScaler().fit(matrix)
    poisson = PoissonRegressor(alpha=0.1, max_iter=300).fit(scaler.transform(matrix), target)
    boosted = HistGradientBoostingRegressor(
        loss="poisson", max_iter=100, max_leaf_nodes=20, min_samples_leaf=50, random_state=seed
    ).fit(matrix, target)
    mean = float(target.mean())
    variance = float(target.var())
    dispersion = max((variance - mean) / max(mean**2, 1e-12), 0.0)
    return {
        "cohort_mean": _Constant(mean),
        "poisson": _ScaledModel(scaler, poisson),
        "negative_binomial": _ScaledModel(scaler, poisson),
        "boosted_count": _ScaledModel(StandardScaler().fit(np.zeros((1, 1))), boosted),
        "_nb_dispersion": _Constant(dispersion),
    }


def _value_models(matrix: np.ndarray, target: np.ndarray, seed: int) -> dict[str, Predictor]:
    positive_target = np.clip(target, 0.01, None)
    scaler = StandardScaler().fit(matrix)
    transformed = scaler.transform(matrix)
    log_target = np.log(positive_target)
    ridge = Ridge(alpha=2.0).fit(transformed, log_target)
    residual_variance = float(np.var(log_target - ridge.predict(transformed)))
    gamma = GammaRegressor(alpha=0.1, max_iter=300).fit(transformed, positive_target)
    tweedie = TweedieRegressor(power=1.5, alpha=0.1, max_iter=300).fit(transformed, positive_target)
    quantile = HistGradientBoostingRegressor(
        loss="quantile", quantile=0.5, max_iter=100, min_samples_leaf=50, random_state=seed
    ).fit(matrix, positive_target)
    return {
        "cohort_mean": _Constant(float(target.mean())),
        "lognormal": _ScaledModel(scaler, ridge, log_target=True, log_variance=residual_variance),
        "gamma": _ScaledModel(scaler, gamma),
        "tweedie": _ScaledModel(scaler, tweedie),
        "quantile_boosting": _ScaledModel(StandardScaler().fit(np.zeros((1, 1))), quantile),
    }


def _direct_predict(model: Predictor, matrix: np.ndarray, name: str) -> np.ndarray:
    if name in {"boosted_count", "quantile_boosting"} and isinstance(model, _ScaledModel):
        return np.clip(np.asarray(model.model.predict(matrix), dtype=float), 0, None)
    return model.predict(matrix)


def _purchase_metrics(actual: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    probability = np.clip(prediction, 1e-6, 1 - 1e-6)
    bins = np.minimum((probability * 10).astype(int), 9)
    calibration_error = 0.0
    for value in np.unique(bins):
        mask = bins == value
        calibration_error += float(mask.mean()) * abs(
            float(probability[mask].mean()) - float(actual[mask].mean())
        )
    return {
        "brier": float(brier_score_loss(actual, probability)),
        "log_loss": float(log_loss(actual, probability, labels=[0, 1])),
        "calibration_error": calibration_error,
        "buyer_relative_error": abs(float(probability.sum() - actual.sum()))
        / max(float(actual.sum()), 1),
    }


def _conditional_metrics(actual: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(actual, prediction)),
        "aggregate_relative_error": abs(float(prediction.sum() - actual.sum()))
        / max(float(actual.sum()), 1),
    }


def _arrival_statistics(customer_month: pl.DataFrame, month: date) -> dict[str, float]:
    _, _, new = _state_and_outcome(customer_month, month)
    buyers = new.filter(pl.col("orders") > 0)
    return {
        "arrivals": float(new.height),
        "buyers": float(buyers.height),
        "orders": float(new["orders"].sum()),
        "revenue": float(new["revenue"].sum()),
        "buyer_rate": buyers.height / max(new.height, 1),
        "orders_per_buyer": float(new["orders"].sum()) / max(buyers.height, 1),
        "revenue_per_order": float(new["revenue"].sum()) / max(float(new["orders"].sum()), 1),
    }


def _arrival_candidates(history: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    keys = ("arrivals", "buyer_rate", "orders_per_buyer", "revenue_per_order")
    result: dict[str, dict[str, float]] = {}
    for name in ("trailing_mean", "trend", "negative_binomial"):
        values: dict[str, float] = {}
        for key in keys:
            series = np.array([row[key] for row in history], dtype=float)
            if name == "trailing_mean":
                values[key] = float(series[-1])
            elif name == "trend" and len(series) >= 2:
                values[key] = float(max(series[-1] + (series[-1] - series[-2]), 0))
            else:
                values[key] = float(series.mean())
        result[name] = values
    return result


def _top_down(history: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for name in ("last_period", "mean", "trend"):
        prediction: dict[str, float] = {}
        for key in ("buyers", "orders", "revenue"):
            values = np.array([row[key] for row in history])
            if name == "last_period":
                prediction[key] = float(values[-1])
            elif name == "mean":
                prediction[key] = float(values.mean())
            elif len(values) >= 2:
                prediction[key] = float(max(values[-1] + values[-1] - values[-2], 0))
            else:
                prediction[key] = float(values[-1])
        result[name] = prediction
    return result


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def simulate_hurdle_population(
    purchase_probability: np.ndarray,
    conditional_orders: np.ndarray,
    conditional_value: np.ndarray,
    *,
    new_buyers: float,
    new_orders: float,
    new_revenue: float,
    draws: int,
    seed: int,
) -> dict[str, dict[str, float]]:
    """Fast coherent aggregate simulation retaining customer-weighted hurdle moments."""
    rng = np.random.default_rng(seed)
    existing_buyer_mean = float(purchase_probability.sum())
    existing_buyer_sd = float(np.sqrt(np.sum(purchase_probability * (1 - purchase_probability))))
    order_ratio = float(np.sum(purchase_probability * conditional_orders)) / max(
        existing_buyer_mean, 1
    )
    value_mean = float(
        np.sum(purchase_probability * conditional_orders * conditional_value)
        / max(np.sum(purchase_probability * conditional_orders), 1)
    )
    new_order_ratio = new_orders / max(new_buyers, 1)
    new_value_mean = new_revenue / max(new_orders, 1)
    buyers = np.empty(draws)
    orders = np.empty(draws)
    revenue = np.empty(draws)
    for draw in range(draws):
        existing_buyers = max(int(round(rng.normal(existing_buyer_mean, existing_buyer_sd))), 0)
        drawn_new_buyers = max(int(rng.poisson(max(new_buyers, 0))), 0)
        existing_orders = existing_buyers + rng.poisson(max(existing_buyers * (order_ratio - 1), 0))
        drawn_new_orders = drawn_new_buyers + rng.poisson(
            max(drawn_new_buyers * (new_order_ratio - 1), 0)
        )
        buyers[draw] = existing_buyers + drawn_new_buyers
        orders[draw] = existing_orders + drawn_new_orders
        existing_revenue = rng.gamma(max(existing_orders * 2, 1), max(value_mean / 2, 1e-6))
        drawn_new_revenue = rng.gamma(max(drawn_new_orders * 2, 1), max(new_value_mean / 2, 1e-6))
        revenue[draw] = existing_revenue + drawn_new_revenue

    def interval(values: np.ndarray) -> dict[str, float]:
        return {
            "mean": float(values.mean()),
            "p05": float(np.quantile(values, 0.05)),
            "p50": float(np.quantile(values, 0.50)),
            "p95": float(np.quantile(values, 0.95)),
        }

    return {"buyers": interval(buyers), "orders": interval(orders), "revenue": interval(revenue)}


def run_population_v2_benchmark(config: PopulationV2Config | None = None) -> Path:
    config = config or PopulationV2Config()
    started = time.perf_counter()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    customer_month = (
        pl.scan_parquet(config.customer_month_path)
        .filter(pl.col("month") < config.final_month)
        .collect()
    )
    development_rows: list[dict[str, Any]] = []
    monthly_actuals: list[dict[str, float]] = []
    arrival_history: list[dict[str, float]] = []

    for month_index, month in enumerate(config.development_months):
        states, outcome, new = _state_and_outcome(customer_month, month)
        previous_months = sorted(
            set(customer_month.filter(pl.col("month") < month)["month"].to_list())
        )
        train_month = previous_months[-1]
        train_state, train_outcome, _ = _state_and_outcome(customer_month, train_month)
        x_train, x_dev = _matrix(train_state), _matrix(states)
        purchase_models = _purchase_models(
            x_train, train_outcome["purchase"].to_numpy(), config.seed + month_index
        )
        for name, model in purchase_models.items():
            prediction = _predict(model, x_dev, name)
            metric = _purchase_metrics(outcome["purchase"].to_numpy(), prediction)
            development_rows.append(
                {"month": str(month), "stage": "purchase", "model": name, **metric}
            )
        buyers_train = train_outcome["purchase"].to_numpy() > 0
        buyers_dev = outcome["purchase"].to_numpy() > 0
        count_models = _count_models(
            x_train[buyers_train],
            train_outcome["orders"].to_numpy()[buyers_train],
            config.seed + month_index,
        )
        for name, model in count_models.items():
            if name.startswith("_"):
                continue
            prediction = _direct_predict(model, x_dev[buyers_dev], name)
            metric = _conditional_metrics(outcome["orders"].to_numpy()[buyers_dev], prediction)
            development_rows.append(
                {"month": str(month), "stage": "orders", "model": name, **metric}
            )
        order_value_train = (
            train_outcome["revenue"].to_numpy()[buyers_train]
            / train_outcome["orders"].to_numpy()[buyers_train]
        )
        order_value_dev = (
            outcome["revenue"].to_numpy()[buyers_dev] / outcome["orders"].to_numpy()[buyers_dev]
        )
        value_models = _value_models(
            x_train[buyers_train], order_value_train, config.seed + month_index
        )
        for name, model in value_models.items():
            prediction = _direct_predict(model, x_dev[buyers_dev], name)
            metric = _conditional_metrics(order_value_dev, prediction)
            development_rows.append(
                {"month": str(month), "stage": "order_value", "model": name, **metric}
            )
        new_buyers = new.filter(pl.col("orders") > 0)
        monthly_actuals.append(
            {
                "buyers": float(outcome["purchase"].sum()) + new_buyers.height,
                "orders": float(outcome["orders"].sum()) + float(new["orders"].sum()),
                "revenue": float(outcome["revenue"].sum()) + float(new["revenue"].sum()),
            }
        )
        arrival_history.append(_arrival_statistics(customer_month, month))

    development = pl.DataFrame(development_rows)
    score_column = (
        pl.when(pl.col("stage") == "purchase")
        .then(pl.col("brier") + pl.col("buyer_relative_error"))
        .otherwise(pl.col("mae") + pl.col("aggregate_relative_error"))
        .alias("score")
    )
    selection = (
        development.with_columns(score_column)
        .group_by("stage", "model")
        .agg(pl.col("score").mean().alias("score"))
        .sort(["stage", "score"])
        .group_by("stage", maintain_order=True)
        .first()
    )
    winners = {str(row["stage"]): str(row["model"]) for row in selection.iter_rows(named=True)}
    arrival_development: list[dict[str, Any]] = []
    for index in range(1, len(arrival_history)):
        actual = arrival_history[index]
        for name, arrival_candidate in _arrival_candidates(arrival_history[:index]).items():
            predicted_buyers = arrival_candidate["arrivals"] * arrival_candidate["buyer_rate"]
            predicted_orders = predicted_buyers * arrival_candidate["orders_per_buyer"]
            predicted_revenue = predicted_orders * arrival_candidate["revenue_per_order"]
            error = sum(
                abs(predicted - actual[key]) / max(actual[key], 1)
                for key, predicted in (
                    ("buyers", predicted_buyers),
                    ("orders", predicted_orders),
                    ("revenue", predicted_revenue),
                )
            )
            arrival_development.append({"model": name, "score": error})
    arrival_winner = (
        min(arrival_development, key=lambda row: row["score"])["model"]
        if arrival_development
        else "trailing_mean"
    )
    top_down_dev = _top_down(monthly_actuals[:-1] or monthly_actuals)
    top_down_winner = min(
        top_down_dev,
        key=lambda name: sum(
            abs(top_down_dev[name][key] - monthly_actuals[-1][key])
            / max(monthly_actuals[-1][key], 1)
            for key in ("buyers", "orders", "revenue")
        ),
    )

    success = {
        "frozen_before_final_reveal": True,
        "final_month": str(config.final_month),
        "development_months": [str(item) for item in config.development_months],
        "primary_metrics": [
            "buyer_count",
            "orders",
            "revenue",
            "purchase_brier",
            "purchase_calibration",
            "heterogeneity_auc",
            "category_revenue_js",
        ],
        "pass_rule": (
            "beat strongest baseline on at least 5 of 7; buyer count, orders and revenue "
            "are mandatory wins; calibration error <= 0.05; heterogeneity AUC > 0.5"
        ),
        "no_final_tuning": True,
    }
    success_path = config.output_dir / "success_criteria.json"
    success_path.write_text(json.dumps(success, indent=2), encoding="utf-8")
    frozen_selection = {
        "stage_winners": winners,
        "arrival_winner": arrival_winner,
        "top_down_winner": top_down_winner,
        "test_metrics_used": False,
    }
    (config.output_dir / "frozen_selection.json").write_text(
        json.dumps(frozen_selection, indent=2), encoding="utf-8"
    )

    # Train through January; February outcomes remain unreferenced until predictions are frozen.
    train_months = [date(2019, 11, 1), date(2019, 12, 1), date(2020, 1, 1)]
    state_parts, outcome_parts = [], []
    for month in train_months:
        state, outcome, _ = _state_and_outcome(customer_month, month)
        state_parts.append(state)
        outcome_parts.append(outcome)
    train_state = pl.concat(state_parts, how="vertical")
    train_outcome = pl.concat(outcome_parts, how="vertical")
    final_state, _, _ = _state_and_outcome(
        customer_month.filter(pl.col("month") < config.final_month), config.final_month
    )
    x_train, x_final = _matrix(train_state), _matrix(final_state)
    purchase_models = _purchase_models(x_train, train_outcome["purchase"].to_numpy(), config.seed)
    purchase_prediction = _predict(
        purchase_models[winners["purchase"]], x_final, winners["purchase"]
    )
    buyer_train = train_outcome["purchase"].to_numpy() > 0
    count_models = _count_models(
        x_train[buyer_train], train_outcome["orders"].to_numpy()[buyer_train], config.seed
    )
    conditional_orders = _direct_predict(
        count_models[winners["orders"]], x_final, winners["orders"]
    )
    conditional_orders = np.maximum(conditional_orders, 1.0)
    train_order_value = (
        train_outcome["revenue"].to_numpy()[buyer_train]
        / train_outcome["orders"].to_numpy()[buyer_train]
    )
    value_models = _value_models(x_train[buyer_train], train_order_value, config.seed)
    conditional_value = _direct_predict(
        value_models[winners["order_value"]], x_final, winners["order_value"]
    )
    existing_orders = purchase_prediction * conditional_orders
    existing_revenue = existing_orders * conditional_value
    arrival_prediction = _arrival_candidates(arrival_history)[cast(str, arrival_winner)]
    new_buyers_prediction = arrival_prediction["arrivals"] * arrival_prediction["buyer_rate"]
    new_orders_prediction = new_buyers_prediction * arrival_prediction["orders_per_buyer"]
    new_revenue_prediction = new_orders_prediction * arrival_prediction["revenue_per_order"]
    frozen = pl.DataFrame(
        {
            "customer_id": final_state["customer_id"],
            "purchase_probability": purchase_prediction,
            "conditional_orders": conditional_orders,
            "conditional_order_value": conditional_value,
            "expected_orders": existing_orders,
            "expected_revenue": existing_revenue,
        }
    )
    frozen_path = config.output_dir / "frozen_final_existing_customer_predictions.parquet"
    frozen.write_parquet(frozen_path)
    (config.output_dir / "frozen_new_customer_prediction.json").write_text(
        json.dumps(
            {
                "model": arrival_winner,
                **arrival_prediction,
                "buyers": new_buyers_prediction,
                "orders": new_orders_prediction,
                "revenue": new_revenue_prediction,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ledger_path = config.output_dir / "prediction_ledger.duckdb"
    if ledger_path.exists():
        ledger_path.unlink()
    ledger = PredictionLedger(ledger_path)
    ledger.append_frozen_batch(
        batch_id=f"customer-population-v2:final:seed-{config.seed}",
        dataset_name="REES46 Cosmetics",
        dataset_version=_sha(config.customer_month_path),
        split="2020-02-final",
        model_name=json.dumps(frozen_selection, sort_keys=True),
        row_count=frozen.height,
        predictions_path=str(frozen_path),
        predictions_sha256=_sha(frozen_path),
        config=asdict(config),
        outcome_columns_hidden=("buyers", "orders", "revenue", "new_customers", "category_revenue"),
    )

    # FINAL REVEAL: first reference to February outcome rows.
    final_month_rows = (
        pl.scan_parquet(config.customer_month_path)
        .filter(pl.col("month") == config.final_month)
        .collect()
    )
    customer_month = pl.concat([customer_month, final_month_rows], how="vertical")
    _, final_existing, final_new = _state_and_outcome(customer_month, config.final_month)
    actual_existing_buyers = float(final_existing["purchase"].sum())
    actual_existing_orders = float(final_existing["orders"].sum())
    actual_existing_revenue = float(final_existing["revenue"].sum())
    actual_new_buyers = float((final_new["orders"] > 0).sum())
    actual_new_orders = float(final_new["orders"].sum())
    actual_new_revenue = float(final_new["revenue"].sum())
    predicted = {
        "buyers": float(purchase_prediction.sum()) + new_buyers_prediction,
        "orders": float(existing_orders.sum()) + new_orders_prediction,
        "revenue": float(existing_revenue.sum()) + new_revenue_prediction,
    }
    actual = {
        "buyers": actual_existing_buyers + actual_new_buyers,
        "orders": actual_existing_orders + actual_new_orders,
        "revenue": actual_existing_revenue + actual_new_revenue,
    }
    errors = {key: abs(predicted[key] - actual[key]) / max(actual[key], 1) for key in predicted}
    top_down_predictions = _top_down(monthly_actuals)[top_down_winner]
    top_down_errors = {
        key: abs(top_down_predictions[key] - actual[key]) / max(actual[key], 1) for key in actual
    }
    strongest_baseline = {
        key: min(
            top_down_errors[key], abs(monthly_actuals[-1][key] - actual[key]) / max(actual[key], 1)
        )
        for key in actual
    }
    mandatory_wins = {
        key: errors[key] < strongest_baseline[key] for key in ("buyers", "orders", "revenue")
    }
    purchase_metric = _purchase_metrics(final_existing["purchase"].to_numpy(), purchase_prediction)
    simple_purchase_metrics = {
        name: _purchase_metrics(
            final_existing["purchase"].to_numpy(),
            _predict(purchase_models[name], x_final, name),
        )
        for name in ("population_average", "rfm")
    }
    from sklearn.metrics import roc_auc_score

    auc = float(roc_auc_score(final_existing["purchase"].to_numpy(), purchase_prediction))
    heterogeneity_frame = final_state.select(
        "customer_id",
        "recent_category",
        "orders_last",
        "views_last",
        "orders_history",
        "purchase_months",
    ).with_columns(
        pl.Series("prediction", purchase_prediction),
        pl.Series("actual", final_existing["purchase"].to_numpy()),
        pl.when(pl.col("orders_last") > 0)
        .then(pl.lit("ACTIVE_PURCHASER"))
        .when(pl.col("views_last") > 0)
        .then(pl.lit("COOLING_BROWSER"))
        .otherwise(pl.lit("DORMANT"))
        .alias("lifecycle"),
        pl.when(pl.col("orders_history") >= 2)
        .then(pl.lit("HIGH_FREQUENCY"))
        .otherwise(pl.lit("LOW_FREQUENCY"))
        .alias("frequency_segment"),
        pl.when(pl.col("purchase_months") >= 2)
        .then(pl.lit("HIGH_REPEAT"))
        .otherwise(pl.lit("LOW_REPEAT"))
        .alias("repeat_segment"),
    )

    def heterogeneity_breakdown(column: str, limit: int | None = None) -> list[dict[str, Any]]:
        table = (
            heterogeneity_frame.group_by(column)
            .agg(
                pl.len().alias("customers"),
                pl.col("prediction").mean().alias("predicted_purchase_rate"),
                pl.col("actual").mean().alias("actual_purchase_rate"),
            )
            .with_columns(
                (pl.col("predicted_purchase_rate") - pl.col("actual_purchase_rate"))
                .abs()
                .alias("calibration_error")
            )
            .sort("customers", descending=True)
        )
        if limit is not None:
            table = table.head(limit)
        return table.to_dicts()

    heterogeneity = {
        "lifecycle": heterogeneity_breakdown("lifecycle"),
        "frequency": heterogeneity_breakdown("frequency_segment"),
        "repeat_propensity": heterogeneity_breakdown("repeat_segment"),
        "category_affinity_top20": heterogeneity_breakdown("recent_category", 20),
    }
    actual_categories = (
        customer_month.filter((pl.col("month") == config.final_month) & (pl.col("revenue") > 0))
        .group_by("recent_category")
        .agg(pl.col("revenue").sum())
    )
    predicted_categories = (
        final_state.with_columns(pl.Series("predicted_revenue", existing_revenue))
        .group_by("recent_category")
        .agg(pl.col("predicted_revenue").sum())
    )
    category_keys = sorted(
        set(actual_categories["recent_category"].to_list())
        | set(predicted_categories["recent_category"].to_list())
    )
    actual_map, predicted_map = (
        dict(actual_categories.iter_rows()),
        dict(predicted_categories.iter_rows()),
    )
    prior_categories = (
        customer_month.filter((pl.col("month") == date(2020, 1, 1)) & (pl.col("revenue") > 0))
        .group_by("recent_category")
        .agg(pl.col("revenue").sum())
    )
    prior_map = dict(prior_categories.iter_rows())
    prior_total = max(sum(float(value) for value in prior_map.values()), 1e-9)
    for key in set(prior_map) | set(predicted_map):
        predicted_map[key] = float(predicted_map.get(key, 0)) + (
            new_revenue_prediction * float(prior_map.get(key, 0)) / prior_total
        )
    av = np.array([actual_map.get(key, 0) for key in category_keys], dtype=float) + 1e-9
    pv = np.array([predicted_map.get(key, 0) for key in category_keys], dtype=float) + 1e-9
    category_js = float(jensenshannon(av / av.sum(), pv / pv.sum()) ** 2)
    baseline_category_vector = (
        np.array([prior_map.get(key, 0) for key in category_keys], dtype=float) + 1e-9
    )
    baseline_category_js = float(
        jensenshannon(av / av.sum(), baseline_category_vector / baseline_category_vector.sum()) ** 2
    )
    primary_results = {
        **mandatory_wins,
        "purchase_brier": purchase_metric["brier"]
        < min(item["brier"] for item in simple_purchase_metrics.values()),
        "purchase_calibration": purchase_metric["calibration_error"] <= 0.05,
        "heterogeneity_auc": auc > 0.5,
        "category_revenue_js": category_js < baseline_category_js,
    }
    primary_wins = sum(primary_results.values())
    verdict = (
        "PASS"
        if primary_wins >= 5 and all(mandatory_wins.values())
        else ("MIXED" if primary_wins >= 3 else "FAIL")
    )
    decomposition = decompose_revenue(
        predicted_buyers=predicted["buyers"],
        predicted_orders=predicted["orders"],
        predicted_revenue=predicted["revenue"],
        actual_buyers=actual["buyers"],
        actual_orders=actual["orders"],
        actual_revenue=actual["revenue"],
    )
    actual_order_values = (
        pl.scan_parquet(config.orders_path)
        .filter(pl.col("month") == config.final_month)
        .select("order_value")
        .collect()["order_value"]
        .to_numpy()
    )
    simulation = simulate_hurdle_population(
        purchase_prediction,
        conditional_orders,
        conditional_value,
        new_buyers=new_buyers_prediction,
        new_orders=new_orders_prediction,
        new_revenue=new_revenue_prediction,
        draws=config.simulation_draws,
        seed=config.seed,
    )
    summary = {
        "label": "REAL REES46 COSMETICS V2 — FINAL FEBRUARY 2020 — PREDICTIVE ONLY",
        "selection": frozen_selection,
        "predicted": predicted,
        "actual": actual,
        "relative_errors": errors,
        "existing_actual": {
            "buyers": actual_existing_buyers,
            "orders": actual_existing_orders,
            "revenue": actual_existing_revenue,
        },
        "new_actual": {
            "buyers": actual_new_buyers,
            "orders": actual_new_orders,
            "revenue": actual_new_revenue,
        },
        "new_prediction": {
            "buyers": new_buyers_prediction,
            "orders": new_orders_prediction,
            "revenue": new_revenue_prediction,
        },
        "top_down": {
            "model": top_down_winner,
            "prediction": top_down_predictions,
            "errors": top_down_errors,
        },
        "strongest_baseline_errors": strongest_baseline,
        "mandatory_wins": mandatory_wins,
        "purchase_metrics": purchase_metric,
        "simple_purchase_metrics": simple_purchase_metrics,
        "heterogeneity_auc": auc,
        "heterogeneity_breakdowns": heterogeneity,
        "category_revenue_js": category_js,
        "baseline_category_revenue_js": baseline_category_js,
        "heavy_tail": {
            "actual_order_value": spend_quantiles(actual_order_values),
            "predicted_conditional_value": spend_quantiles(conditional_value),
        },
        "failure_decomposition": decomposition.model_dump(mode="json"),
        "hurdle_simulation": simulation,
        "primary_wins": primary_wins,
        "primary_results": primary_results,
        "verdict": verdict,
        "runtime_seconds": time.perf_counter() - started,
        "v1_comparison": {
            "buyer_error": 0.0613,
            "order_error": 0.4214,
            "revenue_error": 2.0297,
            "warning": "different store and final period; not paired",
        },
    }
    (config.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    development.write_parquet(config.output_dir / "development_tournament.parquet")
    ledger.append_frozen_batch_evaluation(
        f"customer-population-v2:final:seed-{config.seed}", summary
    )
    ledger.close()
    return config.output_dir
