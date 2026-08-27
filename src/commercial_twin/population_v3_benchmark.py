from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from scipy.spatial.distance import jensenshannon
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from commercial_twin.population_v3 import (
    calibration_deciles,
    logit_intercept_reconcile,
    naive_probability_scale,
    reconcile_category_revenue,
    reconcile_expected_orders,
    reconcile_expected_revenue,
    simulate_reconciled_aggregates,
)
from decision_engine.ledger import PredictionLedger

START_MONTH = date(2020, 4, 1)
FEATURES = (
    "orders_last",
    "revenue_last",
    "items_last",
    "orders_history",
    "revenue_history",
    "items_history",
    "active_months",
    "recency_months",
    "repeat_months",
    "mean_item_price_history",
    "categories_history",
)


@dataclass(frozen=True)
class PopulationV3Config:
    customer_month_path: Path = Path(
        "data/processed/rees46/electronics-purchases/customer_month.parquet"
    )
    output_dir: Path = Path(
        "artifacts/customer_population_v3/rees46-electronics-purchases-v3-seed-42"
    )
    development_months: tuple[date, ...] = (
        date(2020, 6, 1),
        date(2020, 7, 1),
        date(2020, 8, 1),
        date(2020, 9, 1),
        date(2020, 10, 1),
    )
    final_month: date = date(2020, 11, 1)
    seed: int = 42
    draws: int = 500


def _state_outcome(
    customer_month: pl.DataFrame, target_month: date
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    history = customer_month.filter(
        (pl.col("month") >= START_MONTH) & (pl.col("month") < target_month)
    ).sort("month")
    last = history["month"].max()
    states = history.group_by("customer_id").agg(
        pl.col("orders").filter(pl.col("month") == last).sum().alias("orders_last"),
        pl.col("revenue").filter(pl.col("month") == last).sum().alias("revenue_last"),
        pl.col("purchase_items").filter(pl.col("month") == last).sum().alias("items_last"),
        pl.col("orders").sum().alias("orders_history"),
        pl.col("revenue").sum().alias("revenue_history"),
        pl.col("purchase_items").sum().alias("items_history"),
        pl.col("month").n_unique().alias("active_months"),
        ((pl.lit(target_month) - pl.col("month").max()).dt.total_days() / 30)
        .round()
        .alias("recency_months"),
        (pl.col("orders") > 0).sum().alias("repeat_months"),
        pl.col("mean_item_price").mean().alias("mean_item_price_history"),
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
        .sort("customer_id")
    )
    new = target.join(states.select("customer_id"), on="customer_id", how="anti")
    return states.sort("customer_id"), outcome, new


def _matrix(state: pl.DataFrame) -> np.ndarray:
    return np.log1p(np.clip(state.select(FEATURES).fill_null(0).to_numpy().astype(float), 0, None))


def _monthly_totals(data: pl.DataFrame) -> list[dict[str, Any]]:
    first_month = data.group_by("customer_id").agg(pl.col("month").min().alias("first_month"))
    enriched = data.join(first_month, on="customer_id")
    return (
        enriched.filter(pl.col("month") >= START_MONTH)
        .group_by("month")
        .agg(
            pl.len().alias("buyers"),
            pl.col("orders").sum().alias("orders"),
            pl.col("revenue").sum().alias("revenue"),
            (pl.col("month") == pl.col("first_month")).sum().alias("new_buyers"),
            (pl.col("month") != pl.col("first_month")).sum().alias("existing_buyers"),
        )
        .sort("month")
        .to_dicts()
    )


def _forecast_candidates(history: list[float]) -> dict[str, float]:
    values = np.asarray(history, dtype=float)
    recent = values[-3:]
    weights = np.array([0.15, 0.25, 0.60])[-len(recent) :]
    weights /= weights.sum()
    level = values[0]
    for value in values[1:]:
        level = 0.5 * value + 0.5 * level
    return {
        "last_period": float(values[-1]),
        "trailing_mean": float(recent.mean()),
        "weighted_trailing_mean": float(np.dot(recent, weights)),
        "linear_trend": float(max(values[-1] + (values[-1] - values[-2]), 0))
        if len(values) >= 2
        else float(values[-1]),
        "exponential_smoothing": float(level),
    }


def _fit_propensity(
    train_state: pl.DataFrame, train_outcome: pl.DataFrame, seed: int
) -> tuple[StandardScaler, LogisticRegression]:
    matrix = _matrix(train_state)
    scaler = StandardScaler().fit(matrix)
    model = LogisticRegression(max_iter=300, random_state=seed).fit(
        scaler.transform(matrix), train_outcome["purchase"].to_numpy()
    )
    return scaler, model


def _predict_propensity(
    state: pl.DataFrame, scaler: StandardScaler, model: LogisticRegression
) -> np.ndarray:
    return np.asarray(model.predict_proba(scaler.transform(_matrix(state)))[:, 1], dtype=float)


def _category_js(actual: dict[str, float], predicted: dict[str, float]) -> float:
    keys = sorted(set(actual) | set(predicted))
    left = np.array([actual.get(key, 0) for key in keys], dtype=float) + 1e-9
    right = np.array([predicted.get(key, 0) for key in keys], dtype=float) + 1e-9
    return float(jensenshannon(left / left.sum(), right / right.sum()) ** 2)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative_error(predicted: float, actual: float) -> float:
    return abs(predicted - actual) / max(abs(actual), 1)


def run_population_v3_benchmark(config: PopulationV3Config | None = None) -> Path:
    config = config or PopulationV3Config()
    started = time.perf_counter()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    development_data = (
        pl.scan_parquet(config.customer_month_path)
        .filter((pl.col("month") >= START_MONTH) & (pl.col("month") < config.final_month))
        .collect()
    )
    totals = _monthly_totals(development_data)
    totals_by_month = {row["month"]: row for row in totals}
    series_names = ("buyers", "orders", "revenue", "new_buyers", "existing_buyers")
    top_down_rows: list[dict[str, Any]] = []
    temporal_rows: list[dict[str, Any]] = []
    reconciliation_rows: list[dict[str, Any]] = []
    selected_category_method_rows: list[dict[str, Any]] = []

    for index, month in enumerate(config.development_months):
        previous = [row for row in totals if row["month"] < month]
        actual_total = totals_by_month[month]
        forecasts: dict[str, dict[str, float]] = {}
        for series in series_names:
            candidates = _forecast_candidates([float(row[series]) for row in previous])
            forecasts[series] = candidates
            for name, prediction in candidates.items():
                top_down_rows.append(
                    {
                        "month": str(month),
                        "series": series,
                        "model": name,
                        "prediction": prediction,
                        "actual": float(actual_total[series]),
                        "relative_error": _relative_error(prediction, float(actual_total[series])),
                    }
                )
        train_months = [item for item in config.development_months if item < month]
        origin = train_months[-1] if train_months else date(2020, 5, 1)
        train_state, train_outcome, _ = _state_outcome(development_data, origin)
        state, outcome, new = _state_outcome(development_data, month)
        scaler, model = _fit_propensity(train_state, train_outcome, config.seed + index)
        raw = _predict_propensity(state, scaler, model)
        existing_anchor = forecasts["existing_buyers"]["last_period"]
        logit, alpha = logit_intercept_reconcile(raw, existing_anchor)
        naive = naive_probability_scale(raw, existing_anchor)
        actual_purchase = outcome["purchase"].to_numpy()
        for method, probability in (
            ("raw_bottom_up", raw),
            ("naive_scaling", naive),
            ("logit_intercept", logit),
        ):
            deciles = calibration_deciles(actual_purchase, probability)
            reconciliation_rows.append(
                {
                    "month": str(month),
                    "method": method,
                    "buyer_error": _relative_error(
                        float(probability.sum()), float(actual_purchase.sum())
                    ),
                    "ece": deciles["ece"],
                    "mce": deciles["mce"],
                    "auc": float(roc_auc_score(actual_purchase, probability)),
                    "ranking_correlation": float(spearmanr(raw, probability).statistic),
                    "alpha": alpha if method == "logit_intercept" else None,
                }
            )
        temporal_rows.append(
            {
                "month": str(month),
                "raw_expected_buyers": float(raw.sum()),
                "reconciled_expected_buyers": float(logit.sum()),
                "actual_existing_buyers": float(actual_purchase.sum()),
                "calibration_intercept": alpha,
                "calibration_slope": float(
                    LogisticRegression(max_iter=200)
                    .fit(
                        np.log(np.clip(raw, 1e-9, 1 - 1e-9) / np.clip(1 - raw, 1e-9, 1))[:, None],
                        actual_purchase,
                    )
                    .coef_[0, 0]
                ),
                "auc": float(roc_auc_score(actual_purchase, raw)),
                "raw_buyer_error": _relative_error(float(raw.sum()), float(actual_purchase.sum())),
                "reconciled_buyer_error": _relative_error(
                    float(logit.sum()), float(actual_purchase.sum())
                ),
            }
        )
        actual_category = dict(
            development_data.filter(pl.col("month") == month)
            .group_by("recent_category")
            .agg(pl.col("revenue").sum())
            .iter_rows()
        )
        prior_category = dict(
            development_data.filter(pl.col("month") == previous[-1]["month"])
            .group_by("recent_category")
            .agg(pl.col("revenue").sum())
            .iter_rows()
        )
        raw_value = state["revenue_history"].to_numpy() / np.clip(
            state["orders_history"].to_numpy(), 1, None
        )
        total_order_anchor = forecasts["orders"]["last_period"]
        total_revenue_anchor = forecasts["revenue"]["last_period"]
        new_buyers_anchor = forecasts["new_buyers"]["last_period"]
        new_orders = new_buyers_anchor * float(new["orders"].sum()) / max(new.height, 1)
        existing_orders = reconcile_expected_orders(
            logit,
            state["orders_history"].to_numpy()
            / np.clip(state["active_months"].to_numpy(), 1, None),
            max(total_order_anchor - new_orders, float(logit.sum())),
        )
        existing_revenue_target = total_revenue_anchor * max(
            1 - float(new["revenue"].sum()) / max(float(actual_total["revenue"]), 1), 0
        )
        proportional = reconcile_expected_revenue(
            existing_orders, raw_value, existing_revenue_target
        )
        prior_total = max(sum(float(value) for value in prior_category.values()), 1)
        category_targets = {
            str(key): existing_revenue_target * float(value) / prior_total
            for key, value in prior_category.items()
        }
        hierarchical, _ = reconcile_category_revenue(
            state["recent_category"].to_numpy(), proportional, category_targets
        )
        for method, customer_revenue in (
            ("proportional", proportional),
            ("hierarchical_category", hierarchical),
        ):
            predicted_category = dict(
                pl.DataFrame(
                    {
                        "category": state["recent_category"],
                        "revenue": customer_revenue,
                    }
                )
                .group_by("category")
                .agg(pl.col("revenue").sum())
                .iter_rows()
            )
            selected_category_method_rows.append(
                {
                    "month": str(month),
                    "method": method,
                    "category_js": _category_js(actual_category, predicted_category),
                }
            )

    top_down = pl.DataFrame(top_down_rows)
    selected_top_down = (
        top_down.group_by("series", "model")
        .agg(pl.col("relative_error").mean().alias("mean_error"))
        .sort(["series", "mean_error"])
        .group_by("series", maintain_order=True)
        .first()
    )
    top_down_winners = {
        str(row["series"]): str(row["model"]) for row in selected_top_down.iter_rows(named=True)
    }
    reconciliation = pl.DataFrame(reconciliation_rows)
    selected_reconciliation = (
        reconciliation.filter(pl.col("method") != "raw_bottom_up")
        .group_by("method")
        .agg(
            (pl.col("buyer_error") + pl.col("ece") + (1 - pl.col("ranking_correlation")))
            .mean()
            .alias("score")
        )
        .sort("score")["method"]
        .item(0)
    )
    category_development = pl.DataFrame(selected_category_method_rows)
    selected_category_method = (
        category_development.group_by("method")
        .agg(pl.col("category_js").mean().alias("score"))
        .sort("score")["method"]
        .item(0)
    )
    residuals = {
        series: top_down.filter(
            (pl.col("series") == series) & (pl.col("model") == top_down_winners[series])
        )["relative_error"].to_list()
        for series in series_names
    }
    selection_payload = {
        "top_down_winners": top_down_winners,
        "reconciliation_method": selected_reconciliation,
        "revenue_reconciliation": selected_category_method,
        "seasonal_naive_status": "NOT_IDENTIFIABLE_WITHOUT_A_COMPLETE_SEASONAL_CYCLE",
        "test_metrics_used": False,
    }
    selection_path = config.output_dir / "frozen_selection.json"
    selection_path.write_text(json.dumps(selection_payload, indent=2), encoding="utf-8")

    # Train and predict final existing customers using pre-November information only.
    train_states, train_outcomes = [], []
    for month in config.development_months:
        state, outcome, _ = _state_outcome(development_data, month)
        train_states.append(state)
        train_outcomes.append(outcome)
    train_state = pl.concat(train_states, how="vertical")
    train_outcome = pl.concat(train_outcomes, how="vertical")
    final_state, _, _ = _state_outcome(development_data, config.final_month)
    scaler, model = _fit_propensity(train_state, train_outcome, config.seed)
    raw_probability = _predict_propensity(final_state, scaler, model)
    history_totals = [row for row in totals if row["month"] < config.final_month]
    final_anchors = {
        series: _forecast_candidates([float(row[series]) for row in history_totals])[
            top_down_winners[series]
        ]
        for series in series_names
    }
    existing_target = final_anchors["existing_buyers"]
    if selected_reconciliation == "naive_scaling":
        reconciled_probability = naive_probability_scale(raw_probability, existing_target)
        final_alpha = None
    elif selected_reconciliation == "raw_bottom_up":
        reconciled_probability, final_alpha = raw_probability, None
    else:
        reconciled_probability, final_alpha = logit_intercept_reconcile(
            raw_probability, existing_target
        )
    if not np.isclose(reconciled_probability.sum(), existing_target, atol=1e-5):
        raise RuntimeError("existing-customer probabilities do not reconcile to target")
    new_target = final_anchors["new_buyers"]
    total_buyer_forecast = existing_target + new_target
    total_order_target = max(final_anchors["orders"], total_buyer_forecast)
    new_order_ratio = float(history_totals[-1]["orders"]) / max(
        float(history_totals[-1]["buyers"]), 1
    )
    new_order_target = new_target * new_order_ratio
    existing_order_target = max(total_order_target - new_order_target, existing_target)
    repeat = final_state["orders_history"].to_numpy() / np.clip(
        final_state["active_months"].to_numpy(), 1, None
    )
    expected_orders = reconcile_expected_orders(
        reconciled_probability, repeat, existing_order_target
    )
    historical_value = final_state["revenue_history"].to_numpy() / np.clip(
        final_state["orders_history"].to_numpy(), 1, None
    )
    new_revenue_share = float(history_totals[-1]["new_buyers"]) / max(
        float(history_totals[-1]["buyers"]), 1
    )
    new_revenue_target = final_anchors["revenue"] * new_revenue_share
    existing_revenue_target = max(final_anchors["revenue"] - new_revenue_target, 0)
    expected_revenue = reconcile_expected_revenue(
        expected_orders, historical_value, existing_revenue_target
    )
    prior_category = dict(
        development_data.filter(pl.col("month") == history_totals[-1]["month"])
        .group_by("recent_category")
        .agg(pl.col("revenue").sum())
        .iter_rows()
    )
    prior_total = max(sum(float(value) for value in prior_category.values()), 1)
    category_targets = {
        str(key): existing_revenue_target * float(value) / prior_total
        for key, value in prior_category.items()
    }
    category_adjustments: dict[str, float] = {}
    if selected_category_method == "hierarchical_category":
        expected_revenue, category_adjustments = reconcile_category_revenue(
            final_state["recent_category"].to_numpy(), expected_revenue, category_targets
        )
        # Reconcile any unsupported category residual back to the total anchor.
        expected_revenue = reconcile_expected_revenue(
            expected_orders,
            expected_revenue / np.clip(expected_orders, 1e-9, None),
            existing_revenue_target,
        )
    frozen = pl.DataFrame(
        {
            "customer_id": final_state["customer_id"],
            "category": final_state["recent_category"],
            "raw_purchase_probability": raw_probability,
            "reconciled_purchase_probability": reconciled_probability,
            "expected_orders": expected_orders,
            "expected_revenue": expected_revenue,
        }
    )
    frozen_path = config.output_dir / "frozen_final_customer_predictions.parquet"
    frozen.write_parquet(frozen_path)
    aggregate_frozen = {
        "anchors": final_anchors,
        "existing_buyers": float(reconciled_probability.sum()),
        "new_buyers": new_target,
        "total_buyers": total_buyer_forecast,
        "total_orders": total_order_target,
        "total_revenue": final_anchors["revenue"],
        "alpha": final_alpha,
        "category_adjustments": category_adjustments,
        "residual_distributions": residuals,
    }
    aggregate_path = config.output_dir / "frozen_aggregate_forecast.json"
    aggregate_path.write_text(json.dumps(aggregate_frozen, indent=2), encoding="utf-8")
    ledger_path = config.output_dir / "prediction_ledger.duckdb"
    if ledger_path.exists():
        ledger_path.unlink()
    ledger = PredictionLedger(ledger_path)
    ledger.append_frozen_batch(
        batch_id=f"customer-population-v3:final:seed-{config.seed}",
        dataset_name="REES46 electronics purchase history",
        dataset_version=_sha(config.customer_month_path),
        split="2020-11-final",
        model_name=json.dumps(selection_payload, sort_keys=True),
        row_count=frozen.height,
        predictions_path=str(frozen_path),
        predictions_sha256=_sha(frozen_path),
        config=asdict(config),
        outcome_columns_hidden=("buyers", "orders", "revenue", "category_revenue"),
    )

    # FINAL REVEAL: November is loaded only below this line.
    final_rows = (
        pl.scan_parquet(config.customer_month_path)
        .filter(pl.col("month") == config.final_month)
        .collect()
    )
    full = pl.concat([development_data, final_rows], how="vertical")
    _, final_outcome, final_new = _state_outcome(full, config.final_month)
    actual_existing = float(final_outcome["purchase"].sum())
    actual_new = float(final_new.height)
    actual = {
        "buyers": actual_existing + actual_new,
        "orders": float(final_outcome["orders"].sum()) + float(final_new["orders"].sum()),
        "revenue": float(final_outcome["revenue"].sum()) + float(final_new["revenue"].sum()),
    }
    raw_bottom_up = {
        "buyers": float(raw_probability.sum()) + new_target,
        "orders": float(
            reconcile_expected_orders(
                raw_probability, repeat, max(float(raw_probability.sum()), 1)
            ).sum()
        )
        + new_order_target,
        "revenue": float(
            reconcile_expected_revenue(
                reconcile_expected_orders(
                    raw_probability, repeat, max(float(raw_probability.sum()), 1)
                ),
                historical_value,
                float(np.sum(raw_probability * repeat * historical_value)),
            ).sum()
        )
        + new_revenue_target,
    }
    top_down_only = {
        "buyers": final_anchors["buyers"],
        "orders": final_anchors["orders"],
        "revenue": final_anchors["revenue"],
    }
    reconciled = {
        "buyers": total_buyer_forecast,
        "orders": total_order_target,
        "revenue": final_anchors["revenue"],
    }
    errors = {
        name: {metric: _relative_error(value, actual[metric]) for metric, value in forecast.items()}
        for name, forecast in (
            ("raw_bottom_up", raw_bottom_up),
            ("top_down", top_down_only),
            ("reconciled", reconciled),
        )
    }
    raw_auc = float(roc_auc_score(final_outcome["purchase"].to_numpy(), raw_probability))
    reconciled_auc = float(
        roc_auc_score(final_outcome["purchase"].to_numpy(), reconciled_probability)
    )
    deciles = calibration_deciles(final_outcome["purchase"].to_numpy(), reconciled_probability)
    ranking = float(spearmanr(raw_probability, reconciled_probability).statistic)
    cohort_frame = final_state.select(
        "customer_id", "recency_months", "repeat_months"
    ).with_columns(
        pl.Series("prediction", reconciled_probability),
        pl.Series("actual", final_outcome["purchase"].to_numpy()),
        pl.when(pl.col("recency_months") <= 1)
        .then(
            pl.when(pl.col("repeat_months") >= 2)
            .then(pl.lit("ACTIVE_REPEAT"))
            .otherwise(pl.lit("ACTIVE_SINGLE"))
        )
        .otherwise(pl.lit("LAPSED"))
        .alias("cohort"),
    )
    cohort_fidelity = (
        cohort_frame.group_by("cohort")
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
        .sort("cohort")
        .to_dicts()
    )
    actual_category = dict(
        final_rows.group_by("recent_category").agg(pl.col("revenue").sum()).iter_rows()
    )
    predicted_category = dict(
        frozen.group_by("category").agg(pl.col("expected_revenue").sum()).iter_rows()
    )
    simple_category = {
        str(key): final_anchors["revenue"] * float(value) / prior_total
        for key, value in prior_category.items()
    }
    category_js = _category_js(actual_category, predicted_category)
    simple_category_js = _category_js(actual_category, simple_category)

    simulations = simulate_reconciled_aggregates(
        reconciled, residuals, draws=config.draws, seed=config.seed
    )
    intervals: dict[str, dict[str, float | bool]] = {}
    for metric in ("buyers", "orders", "revenue"):
        lower = float(np.quantile(simulations[metric], 0.05))
        median = float(np.quantile(simulations[metric], 0.50))
        upper = float(np.quantile(simulations[metric], 0.95))
        intervals[metric] = {
            "p05": lower,
            "p50": median,
            "p95": upper,
            "covered": lower <= actual[metric] <= upper,
        }
    development_coverage = float(
        np.mean(
            [
                row["relative_error"] <= np.quantile(residuals[row["series"]], 0.9)
                for row in top_down_rows
                if row["model"] == top_down_winners[row["series"]]
                and row["series"] in {"buyers", "orders", "revenue"}
            ]
        )
    )
    tolerance = 0.02
    aggregate_near = {
        metric: errors["reconciled"][metric] <= errors["top_down"][metric] + tolerance
        for metric in ("buyers", "orders", "revenue")
    }
    aggregate_beats = {
        metric: errors["reconciled"][metric] <= errors["top_down"][metric] - 0.005
        for metric in ("buyers", "orders", "revenue")
    }
    tradeoff = (
        all(
            errors["reconciled"][metric] <= errors["top_down"][metric] + 0.01
            for metric in ("buyers", "orders", "revenue")
        )
        and category_js <= simple_category_js * 0.9
    )
    pass_conditions = {
        "aggregate_within_tolerance": all(aggregate_near.values()),
        "two_aggregate_wins_or_tradeoff": sum(aggregate_beats.values()) >= 2 or tradeoff,
        "auc_retained": reconciled_auc >= 0.85 and raw_auc - reconciled_auc <= 0.005,
        "decile_ece": float(deciles["ece"]) <= 0.03,
        "decile_mce": float(deciles["mce"]) <= 0.10,
        "category_fidelity": category_js < simple_category_js,
        "development_interval_coverage": development_coverage >= 0.70,
    }
    diagnostic_capability_verdict = (
        "PASS"
        if all(pass_conditions.values())
        else ("MIXED" if sum(pass_conditions.values()) >= 4 else "FAIL")
    )
    # The first November run violated the probability-sum invariant. November is now burned;
    # this corrected rerun is diagnostic only and cannot support a scientific PASS.
    verdict = "FAIL"
    snapshot = {
        "as_of": str(config.final_month),
        "expected_active_buyers": reconciled["buyers"],
        "expected_orders": reconciled["orders"],
        "expected_revenue": reconciled["revenue"],
        "prediction_intervals": intervals,
        "new_customer_forecast": {"buyers": new_target},
        "existing_customer_forecast": {"buyers": existing_target},
        "customer_propensity_distribution": {
            "p50": float(np.quantile(reconciled_probability, 0.5)),
            "p90": float(np.quantile(reconciled_probability, 0.9)),
            "p99": float(np.quantile(reconciled_probability, 0.99)),
        },
        "category_mix": predicted_category,
        "cohort_states": cohort_fidelity,
        "aggregate_forecast_source": top_down_winners,
        "bottom_up_forecast": raw_bottom_up,
        "reconciled_forecast": reconciled,
        "reconciliation_method": selected_reconciliation,
        "reconciliation_adjustment": {
            "raw_existing_buyers": float(raw_probability.sum()),
            "target_existing_buyers": existing_target,
            "logit_alpha": final_alpha,
        },
        "purchase_calibration": deciles,
        "population_fidelity": errors,
        "heterogeneity_fidelity": {
            "auc_before": raw_auc,
            "auc_after": reconciled_auc,
            "ranking_correlation": ranking,
        },
        "driver_evidence": "PREDICTIVE_ONLY",
        "readiness_verdict": verdict,
    }
    summary = {
        "label": "REAL REES46 ELECTRONICS PURCHASES V3 — NOVEMBER FINAL — PREDICTIVE ONLY",
        "dataset_profile": json.loads(
            Path("data/processed/rees46/electronics-purchases/profile.json").read_text(
                encoding="utf-8"
            )
        ),
        "splits": {
            "history": ["2020-04", "2020-05"],
            "development": [str(item) for item in config.development_months],
            "final": str(config.final_month),
            "burned_cosmetics_february_used": False,
        },
        "selection": selection_payload,
        "forecasts": {
            "actual": actual,
            "raw_bottom_up": raw_bottom_up,
            "top_down": top_down_only,
            "reconciled": reconciled,
        },
        "errors": errors,
        "new_customer": {
            "predicted_buyers": new_target,
            "actual_buyers": actual_new,
            "relative_error": _relative_error(new_target, actual_new),
        },
        "existing_customer": {
            "predicted_buyers": existing_target,
            "actual_buyers": actual_existing,
            "relative_error": _relative_error(existing_target, actual_existing),
        },
        "auc_before": raw_auc,
        "auc_after": reconciled_auc,
        "ranking_correlation": ranking,
        "decile_calibration": deciles,
        "category_js": category_js,
        "simple_category_js": simple_category_js,
        "cohort_fidelity": cohort_fidelity,
        "intervals": intervals,
        "development_interval_coverage": development_coverage,
        "temporal_calibration": temporal_rows,
        "pass_conditions": pass_conditions,
        "diagnostic_capability_verdict": diagnostic_capability_verdict,
        "final_validation_status": "BURNED_AFTER_INVALID_FIRST_RUN_CORRECTED_DIAGNOSTIC_ONLY",
        "eligible_for_scientific_pass": False,
        "aggregate_beats": aggregate_beats,
        "simple_top_down_plus_propensity_equivalent": selected_category_method == "proportional",
        "verdict": verdict,
        "runtime_seconds": time.perf_counter() - started,
    }
    (config.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (config.output_dir / "customer_population_snapshot_v3.json").write_text(
        json.dumps(snapshot, indent=2), encoding="utf-8"
    )
    top_down.write_parquet(config.output_dir / "development_top_down.parquet")
    reconciliation.write_parquet(config.output_dir / "development_reconciliation.parquet")
    category_development.write_parquet(
        config.output_dir / "development_category_reconciliation.parquet"
    )
    pl.DataFrame(temporal_rows).write_parquet(config.output_dir / "temporal_calibration.parquet")
    ledger.append_frozen_batch_evaluation(
        f"customer-population-v3:final:seed-{config.seed}", summary
    )
    ledger.close()
    return config.output_dir
