from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import numpy as np
import polars as pl
from scipy.spatial.distance import jensenshannon
from scipy.stats import wasserstein_distance
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error, mean_squared_error

from commercial_twin.population_contracts import PopulationFidelityReport
from commercial_twin.population_ingestion import write_canonical_parquet
from commercial_twin.population_models import (
    PopulationOutcomeModel,
    baseline_predictions,
    build_future_outcomes,
    simulate_population,
)
from commercial_twin.population_state import (
    attach_affinities,
    build_cohorts,
    build_customer_states,
    build_population_snapshot,
)
from decision_engine.ledger import PredictionLedger


@dataclass(frozen=True)
class PopulationBenchmarkConfig:
    raw_path: Path = Path("data/raw/rees46/electronics-events.csv.gz")
    canonical_path: Path = Path("data/processed/rees46/electronics-events.parquet")
    output_dir: Path = Path("artifacts/customer_population/rees46-electronics-v1-seed-42")
    development_cutoffs: tuple[datetime, ...] = (
        datetime(2020, 12, 1, tzinfo=UTC),
        datetime(2021, 1, 1, tzinfo=UTC),
    )
    final_cutoff: datetime = datetime(2021, 2, 1, tzinfo=UTC)
    horizon_days: int = 30
    n_cohorts: int = 8
    seed: int = 42
    monte_carlo_draws: int = 300


def _state(
    events: pl.DataFrame, cutoff: datetime, config: PopulationBenchmarkConfig
) -> pl.DataFrame:
    state = build_customer_states(events, cutoff)
    state = attach_affinities(events, state, cutoff)
    labeled, _ = build_cohorts(state, n_cohorts=config.n_cohorts, seed=config.seed)
    return labeled


def _cohort_prediction(
    train_state: pl.DataFrame,
    train_outcome: pl.DataFrame,
    target_state: pl.DataFrame,
    outcome: str,
) -> np.ndarray:
    rates = (
        train_state.select("customer_id", "cohort_id")
        .join(train_outcome, on="customer_id")
        .group_by("cohort_id")
        .agg(pl.col(outcome).mean().alias("prediction"))
    )
    fallback = float(cast(float, train_outcome[outcome].mean()))
    return (
        target_state.select("cohort_id")
        .join(rates, on="cohort_id", how="left")
        .with_columns(pl.col("prediction").fill_null(fallback))["prediction"]
        .to_numpy()
    )


def _metrics(outcome: str, actual: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    prediction = np.asarray(prediction, dtype=float)
    if outcome == "purchase":
        clipped = np.clip(prediction, 1e-6, 1 - 1e-6)
        bins = np.minimum((clipped * 10).astype(int), 9)
        calibration = 0.0
        for value in np.unique(bins):
            mask = bins == value
            calibration += float(mask.mean()) * abs(
                float(clipped[mask].mean()) - float(actual[mask].mean())
            )
        return {
            "brier": float(brier_score_loss(actual, clipped)),
            "log_loss": float(log_loss(actual, clipped, labels=[0, 1])),
            "calibration_error": calibration,
            "aggregate_relative_error": abs(float(clipped.sum() - actual.sum()))
            / max(float(actual.sum()), 1.0),
        }
    return {
        "mae": float(mean_absolute_error(actual, prediction)),
        "rmse": float(np.sqrt(mean_squared_error(actual, prediction))),
        "aggregate_relative_error": abs(float(prediction.sum() - actual.sum()))
        / max(float(actual.sum()), 1.0),
    }


def _selection_score(outcome: str, metrics: dict[str, float]) -> float:
    if outcome == "purchase":
        return metrics["brier"] + metrics["calibration_error"] + metrics["aggregate_relative_error"]
    return metrics["mae"] + metrics["aggregate_relative_error"]


def _fit_candidates(
    train_state: pl.DataFrame,
    train_outcome: pl.DataFrame,
    target_state: pl.DataFrame,
    outcome: str,
    seed: int,
) -> dict[str, np.ndarray]:
    typed_outcome = outcome  # mypy narrows this at the constructor boundary below.
    baseline = baseline_predictions(target_state, train_outcome, typed_outcome)  # type: ignore[arg-type]
    baseline["cohort_average"] = _cohort_prediction(
        train_state, train_outcome, target_state, outcome
    )
    target = train_outcome[outcome].to_numpy().astype(float)
    for representation, name in (
        ("RFM_STATE", "gradient_boosting_rfm"),
        ("BEHAVIOR_CATEGORY", "gradient_boosting_category"),
    ):
        model = PopulationOutcomeModel(typed_outcome, representation, seed)  # type: ignore[arg-type]
        baseline[name] = model.fit(train_state, target).predict(target_state)
    return baseline


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_success_criteria(config: PopulationBenchmarkConfig) -> Path:
    path = config.output_dir / "success_criteria.json"
    payload = {
        "frozen_before_final_reveal": True,
        "development_cutoffs": [item.isoformat() for item in config.development_cutoffs],
        "final_cutoff": config.final_cutoff.isoformat(),
        "horizon_days": config.horizon_days,
        "key_metrics": [
            "purchase_brier",
            "purchase_calibration",
            "buyer_count_error",
            "order_error",
            "revenue_error",
            "cohort_calibration",
            "category_mix_divergence",
        ],
        "pass_rule": (
            "selected engine must beat the strongest simple baseline on at least 4 of 7 key "
            "final metrics and purchase calibration error must be <= 0.05"
        ),
        "simple_baselines": [
            "population_average",
            "last_period",
            "rfm",
            "cohort_average",
        ],
        "criteria_may_not_change_after_final_reveal": True,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def run_population_benchmark(config: PopulationBenchmarkConfig | None = None) -> Path:
    config = config or PopulationBenchmarkConfig()
    started = time.perf_counter()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    if not config.canonical_path.exists():
        write_canonical_parquet(config.raw_path, config.canonical_path)
    events = pl.read_parquet(config.canonical_path)
    development_rows: list[dict[str, Any]] = []
    for cutoff_index, cutoff in enumerate(config.development_cutoffs):
        origin = cutoff - timedelta(days=config.horizon_days)
        train_state = _state(events, origin, config)
        train_outcome = build_future_outcomes(events, train_state, origin, cutoff)
        target_state = _state(events, cutoff, config)
        target_outcome = build_future_outcomes(
            events, target_state, cutoff, cutoff + timedelta(days=config.horizon_days)
        )
        for outcome in ("purchase", "orders", "spend"):
            candidates = _fit_candidates(
                train_state,
                train_outcome,
                target_state,
                outcome,
                config.seed + cutoff_index,
            )
            actual = target_outcome[outcome].to_numpy()
            for model_name, prediction in candidates.items():
                metric = _metrics(outcome, actual, prediction)
                development_rows.append(
                    {
                        "cutoff": cutoff.isoformat(),
                        "outcome": outcome,
                        "model": model_name,
                        "selection_score": _selection_score(outcome, metric),
                        **metric,
                    }
                )
    development = pl.DataFrame(development_rows)
    selection = (
        development.group_by("outcome", "model")
        .agg(pl.col("selection_score").mean().alias("mean_selection_score"))
        .sort(["outcome", "mean_selection_score"])
        .group_by("outcome", maintain_order=True)
        .first()
    )
    winners = {str(row["outcome"]): str(row["model"]) for row in selection.iter_rows(named=True)}
    success_path = _write_success_criteria(config)

    # Fit the frozen winners using only periods whose outcomes are available by final_cutoff.
    training_states: list[pl.DataFrame] = []
    training_outcomes: list[pl.DataFrame] = []
    for origin in config.development_cutoffs:
        state = _state(events, origin, config)
        outcome_frame = build_future_outcomes(
            events, state, origin, origin + timedelta(days=config.horizon_days)
        )
        training_states.append(state)
        training_outcomes.append(outcome_frame)
    train_state = pl.concat(training_states, how="diagonal_relaxed")
    train_outcome = pl.concat(training_outcomes, how="diagonal_relaxed")
    final_state = _state(events, config.final_cutoff, config)
    predictions: dict[str, np.ndarray] = {}
    all_final_candidates: dict[str, dict[str, np.ndarray]] = {}
    for index, outcome in enumerate(("purchase", "orders", "spend")):
        candidates = _fit_candidates(
            train_state,
            train_outcome,
            final_state,
            outcome,
            config.seed + 100 + index,
        )
        all_final_candidates[outcome] = candidates
        predictions[outcome] = candidates[winners[outcome]]

    frozen = pl.DataFrame(
        {
            "customer_id": final_state["customer_id"],
            "purchase_probability": predictions["purchase"],
            "expected_orders": predictions["orders"],
            "expected_spend": predictions["spend"],
            "cohort_id": final_state["cohort_id"],
            "dominant_category": final_state["dominant_category"],
        }
    )
    frozen_path = config.output_dir / "frozen_final_customer_predictions.parquet"
    frozen.write_parquet(frozen_path)
    ledger_path = config.output_dir / "prediction_ledger.duckdb"
    if ledger_path.exists():
        ledger_path.unlink()
    ledger = PredictionLedger(ledger_path)
    ledger.append_frozen_batch(
        batch_id=f"customer-population:final:seed-{config.seed}",
        dataset_name="REES46 electronics events",
        dataset_version=_sha256(config.raw_path),
        split="final_untouched_30d",
        model_name=json.dumps(winners, sort_keys=True),
        row_count=frozen.height,
        predictions_path=str(frozen_path),
        predictions_sha256=_sha256(frozen_path),
        config=asdict(config),
        outcome_columns_hidden=("purchase", "orders", "spend", "category"),
    )

    # Final outcome reveal starts only after criteria, selection, and predictions are frozen.
    final_outcome = build_future_outcomes(
        events,
        final_state,
        config.final_cutoff,
        config.final_cutoff + timedelta(days=config.horizon_days),
    )
    final_rows: list[dict[str, Any]] = []
    for outcome in ("purchase", "orders", "spend"):
        actual = final_outcome[outcome].to_numpy()
        for model_name, prediction in all_final_candidates[outcome].items():
            final_rows.append(
                {
                    "outcome": outcome,
                    "model": model_name,
                    "selected": model_name == winners[outcome],
                    **_metrics(outcome, actual, prediction),
                }
            )
    final_metrics = pl.DataFrame(final_rows)
    selected_metrics = final_metrics.filter(pl.col("selected"))
    purchase_metrics = selected_metrics.filter(pl.col("outcome") == "purchase").row(0, named=True)
    orders_metrics = selected_metrics.filter(pl.col("outcome") == "orders").row(0, named=True)
    spend_metrics = selected_metrics.filter(pl.col("outcome") == "spend").row(0, named=True)

    purchase_events = events.filter(
        (pl.col("event_time") > config.final_cutoff)
        & (pl.col("event_time") <= config.final_cutoff + timedelta(days=config.horizon_days))
        & (pl.col("event_type") == "purchase")
    )
    actual_category = purchase_events.group_by("category_id").len()
    categories = sorted(
        set(actual_category["category_id"].to_list())
        | set(final_state["dominant_category"].to_list())
    )
    actual_map = dict(actual_category.iter_rows())
    actual_vector = np.array([float(actual_map.get(key, 0)) for key in categories]) + 1e-9
    actual_vector /= actual_vector.sum()

    def category_divergence(probability: np.ndarray) -> float:
        weighted = (
            pl.DataFrame({"category": final_state["dominant_category"], "probability": probability})
            .group_by("category")
            .agg(pl.col("probability").sum())
        )
        predicted_map = dict(weighted.iter_rows())
        vector = np.array([float(predicted_map.get(key, 0)) for key in categories]) + 1e-9
        vector /= vector.sum()
        return float(jensenshannon(actual_vector, vector) ** 2)

    category_js = category_divergence(predictions["purchase"])

    actual_spend = final_outcome["spend"].to_numpy()
    predicted_spend = predictions["spend"]
    actual_aov = actual_spend[actual_spend > 0]
    predicted_aov = predicted_spend[predicted_spend > 0]
    aov_distance = float(wasserstein_distance(actual_aov, predicted_aov))

    def cohort_calibration(probability: np.ndarray) -> tuple[pl.DataFrame, float]:
        table = (
            final_state.select("customer_id", "cohort_id")
            .with_columns(pl.Series("purchase_probability", probability))
            .join(final_outcome, on="customer_id")
            .group_by("cohort_id")
            .agg(
                pl.col("purchase_probability").mean().alias("predicted"),
                pl.col("purchase").mean().alias("actual"),
            )
            .with_columns((pl.col("predicted") - pl.col("actual")).abs().alias("error"))
        )
        return table, float(cast(float, table["error"].mean()))

    cohort, cohort_error = cohort_calibration(predictions["purchase"])
    simulation = simulate_population(
        predictions["purchase"],
        predictions["orders"],
        predictions["spend"],
        draws=config.monte_carlo_draws,
        seed=config.seed,
    )

    simple = {"population_average", "last_period", "rfm", "cohort_average"}
    key_wins = 0
    comparisons: dict[str, Any] = {}
    for outcome in ("orders", "spend"):
        metric_name = "aggregate_relative_error"
        outcome_rows = final_metrics.filter(pl.col("outcome") == outcome)
        selected_value = float(outcome_rows.filter(pl.col("selected"))[metric_name].item())
        simple_value = float(
            cast(
                float,
                outcome_rows.filter(pl.col("model").is_in(list(simple)))[metric_name].min(),
            )
        )
        comparisons[outcome] = {
            "metric": metric_name,
            "selected": selected_value,
            "strongest_simple": simple_value,
            "win": selected_value < simple_value and not np.isclose(selected_value, simple_value),
        }
        key_wins += int(
            selected_value < simple_value and not np.isclose(selected_value, simple_value)
        )
    purchase_rows = final_metrics.filter(pl.col("outcome") == "purchase")
    for label, metric_name in (
        ("purchase_brier", "brier"),
        ("purchase_calibration", "calibration_error"),
        ("buyer_count", "aggregate_relative_error"),
    ):
        selected_value = float(purchase_rows.filter(pl.col("selected"))[metric_name].item())
        simple_value = float(
            cast(
                float,
                purchase_rows.filter(pl.col("model").is_in(list(simple)))[metric_name].min(),
            )
        )
        comparisons[label] = {
            "metric": metric_name,
            "selected": selected_value,
            "strongest_simple": simple_value,
            "win": selected_value < simple_value and not np.isclose(selected_value, simple_value),
        }
        key_wins += int(
            selected_value < simple_value and not np.isclose(selected_value, simple_value)
        )
    simple_cohort = min(
        cohort_calibration(all_final_candidates["purchase"][name])[1] for name in simple
    )
    simple_category = min(
        category_divergence(all_final_candidates["purchase"][name]) for name in simple
    )
    for label, selected_value, simple_value in (
        ("cohort_calibration", cohort_error, simple_cohort),
        ("category_mix", category_js, simple_category),
    ):
        comparisons[label] = {
            "selected": selected_value,
            "strongest_simple": simple_value,
            "win": selected_value < simple_value and not np.isclose(selected_value, simple_value),
        }
        key_wins += int(
            selected_value < simple_value and not np.isclose(selected_value, simple_value)
        )
    verdict = "PASS" if key_wins >= 4 else ("MIXED" if key_wins >= 2 else "FAIL")
    fidelity = PopulationFidelityReport(
        purchase_calibration=float(purchase_metrics["calibration_error"]),
        buyer_count_relative_error=float(purchase_metrics["aggregate_relative_error"]),
        order_error=float(orders_metrics["aggregate_relative_error"]),
        revenue_relative_error=float(spend_metrics["aggregate_relative_error"]),
        aov_distribution_error=aov_distance,
        category_mix_divergence=category_js,
        cohort_calibration=cohort_error,
        temporal_stability=float(cast(float, development["selection_score"].std())),
        verdict=verdict,
        raw_metrics={"baseline_comparisons": comparisons, "key_wins": key_wins},
    )
    labeled_state, cohorts = build_cohorts(
        final_state, n_cohorts=config.n_cohorts, seed=config.seed
    )
    product_snapshot = build_population_snapshot(
        labeled_state,
        cohorts,
        as_of=config.final_cutoff,
        model_versions=winners,
    )
    summary = {
        "label": "REAL CUSTOMER POPULATION — REES46 ELECTRONICS — NOT CAUSAL EVIDENCE",
        "source": "https://data.rees46.com/datasets/electronics-events/electronics-events.csv.gz",
        "raw_sha256": _sha256(config.raw_path),
        "events": events.height,
        "unique_customers": events["customer_id"].n_unique(),
        "history_start": str(events["event_time"].min()),
        "history_end": str(events["event_time"].max()),
        "development_cutoffs": [item.isoformat() for item in config.development_cutoffs],
        "final_cutoff": config.final_cutoff.isoformat(),
        "selected_models": winners,
        "selection_frozen_before_final": True,
        "success_criteria_sha256": _sha256(success_path),
        "fidelity": fidelity.model_dump(mode="json"),
        "simulation": simulation,
        "actual_population": {
            "buyers": int(final_outcome["purchase"].sum()),
            "orders": float(final_outcome["orders"].sum()),
            "revenue": float(final_outcome["spend"].sum()),
        },
        "world_state": "NOT_AVAILABLE_FOR_VALIDATION",
        "world_effect_validated": False,
        "driver_evidence": "PREDICTIVE_ONLY",
        "runtime_seconds": time.perf_counter() - started,
    }
    (config.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (config.output_dir / "customer_population_snapshot.json").write_text(
        product_snapshot.model_dump_json(indent=2), encoding="utf-8"
    )
    development.write_parquet(config.output_dir / "development_tournament.parquet")
    final_metrics.write_parquet(config.output_dir / "final_metrics.parquet")
    cohort.write_parquet(config.output_dir / "cohort_fidelity.parquet")
    ledger.append_frozen_batch_evaluation(
        f"customer-population:final:seed-{config.seed}", fidelity.model_dump(mode="json")
    )
    ledger.close()
    return config.output_dir
