from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import numpy as np
import polars as pl

from commercial_twin.factory import TwinFactory
from commercial_twin.schemas import WorldState
from decision_engine.datasets.dominicks import DominicksDataset
from decision_engine.ledger import PredictionLedger
from domains.commerce.actions import DiscountAction
from domains.commerce.behavior import ContinuousDiscountBehaviorModel

REAL_FEATURES = [
    "store_id",
    "category_id",
    "sku_id",
    "regular_price",
    "weekday",
    "product_age",
    "lagged_demand",
]


@dataclass(frozen=True)
class RealTwinRunConfig:
    raw_dir: Path = Path("data/raw/dominicks/oatmeal")
    output_dir: Path = Path("artifacts/real_commercial_twin/dominicks")
    seed: int = 42
    cutoff_fraction: float = 0.80
    holdout_weeks: int = 8
    products: int = 8
    stores: int = 8
    candidate_discounts: tuple[float, ...] = (0.0, 0.05, 0.10, 0.15)
    volume_fractions: tuple[float, ...] = (0.05, 0.10, 0.25, 0.50, 0.75, 1.0)


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - actual
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "bias": float(np.mean(error)),
    }


def _display_outcome(outcomes: dict[str, dict[str, Any]], name: str) -> str:
    value = outcomes.get(name)
    if value is None:
        return "NOT_AVAILABLE"
    return f"{value['mean']:.2f} [{value['p05']:.2f}, {value['p95']:.2f}]"


def split_at_cutoff(
    frame: pl.DataFrame, cutoff: Any, holdout_weeks: int
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Create a strict pre-cutoff history and bounded post-cutoff factual holdout."""
    future_end = cutoff + timedelta(weeks=holdout_weeks)
    history = frame.filter(pl.col("date") < cutoff)
    future = frame.filter((pl.col("date") >= cutoff) & (pl.col("date") < future_end))
    return history, future


def observational_causal_status() -> dict[str, Any]:
    return {
        "status": "NOT_IDENTIFIABLE",
        "reason": "candidate-action counterfactual outcomes are not observed for the same rows",
        "randomized_experiment_used": False,
    }


def _factual_evaluation(
    model: ContinuousDiscountBehaviorModel, future: pl.DataFrame
) -> dict[str, Any]:
    indexed = future.with_row_index("__row")
    factual = np.zeros(indexed.height)
    binned = np.round(indexed["discount"].to_numpy() / 0.01) * 0.01
    for dose in np.unique(binned):
        mask = binned == dose
        subset = indexed.filter(pl.Series(mask))
        factual[mask] = model.estimator_.dose_response(subset, np.array([dose]))[:, 0]
    actual_units = indexed["observed_sales"].to_numpy()
    baseline = indexed["lagged_demand"].to_numpy()
    flexible = model.estimator_.outcome_model_.predict_observed(indexed)
    scale = model.residual_scale_
    lower = np.maximum(factual - 1.645 * scale, 0)
    upper = factual + 1.645 * scale
    interval_score = upper - lower
    interval_score += 20 * np.maximum(lower - actual_units, 0)
    interval_score += 20 * np.maximum(actual_units - upper, 0)
    price = indexed["price"].to_numpy()
    predicted_price = indexed["regular_price"].to_numpy() * (1 - binned)
    result: dict[str, Any] = {
        "rows": indexed.height,
        "actual_action_evaluation": "FACTUAL_PREDICTION_ONLY",
        "demand": {
            "seasonal_lag_baseline": _metrics(actual_units, baseline),
            "flexible_outcome_model": _metrics(actual_units, flexible),
            "dr_factual_at_observed_dose_bin": _metrics(actual_units, factual),
        },
        "revenue": _metrics(price * actual_units, predicted_price * factual),
        "interval_90": {
            "coverage": float(np.mean((actual_units >= lower) & (actual_units <= upper))),
            "average_width": float(np.mean(upper - lower)),
            "wis_90_single_interval": float(np.mean(interval_score)),
        },
        "discount_binning": "nearest 1 percentage point for factual DR evaluation",
    }
    cost_mask = indexed["unit_cost"].is_not_null().to_numpy()
    if cost_mask.any():
        costs = indexed["unit_cost"].fill_null(0).to_numpy()
        actual_profit = (price - costs) * actual_units
        predicted_profit = (predicted_price - costs) * factual
        result["contribution_profit"] = _metrics(
            actual_profit[cost_mask], predicted_profit[cost_mask]
        )
    else:
        result["contribution_profit"] = {"status": "NOT_AVAILABLE_MISSING_COST"}
    return result


def _select_scope(
    history: pl.DataFrame, products: int, stores: int
) -> tuple[pl.DataFrame, tuple[str, ...], tuple[str, ...]]:
    product_ids = tuple(
        history.group_by("sku_id")
        .agg(pl.len().alias("rows"), pl.col("observed_sales").sum().alias("units"))
        .sort(["rows", "units", "sku_id"], descending=[True, True, False])
        .head(products)["sku_id"]
        .to_list()
    )
    store_ids = tuple(
        history.filter(pl.col("sku_id").is_in(product_ids))
        .group_by("store_id")
        .agg(pl.len().alias("rows"), pl.col("observed_sales").sum().alias("units"))
        .sort(["rows", "units", "store_id"], descending=[True, True, False])
        .head(stores)["store_id"]
        .to_list()
    )
    selected = history.filter(
        pl.col("sku_id").is_in(product_ids) & pl.col("store_id").is_in(store_ids)
    )
    return selected, product_ids, store_ids


def run_real_commercial_twin(config: RealTwinRunConfig | None = None) -> Path:
    config = config or RealTwinRunConfig()
    started = time.perf_counter()
    canonical, profile = DominicksDataset(config.raw_dir).load_canonical()
    dates = canonical["date"].unique().sort().to_list()
    cutoff = dates[min(int(len(dates) * config.cutoff_fraction), len(dates) - 2)]
    full_history, _ = split_at_cutoff(canonical, cutoff, config.holdout_weeks)
    selected_history, product_ids, store_ids = _select_scope(
        full_history, config.products, config.stores
    )
    future_end = cutoff + timedelta(weeks=config.holdout_weeks)

    run_id = f"oatmeal-cutoff-{cutoff.date()}-seed-{config.seed}-v1"
    output = config.output_dir / run_id
    output.mkdir(parents=True, exist_ok=True)
    ledger = PredictionLedger(output / "prediction_ledger.duckdb")
    world = WorldState(signals=(), as_of=cutoff)
    twin = TwinFactory().build_twin(
        "dominicks-oatmeal",
        "dominicks-historical",
        selected_history,
        world,
        seed=config.seed,
        ledger=ledger,
        behavior_features=REAL_FEATURES,
    )
    actions = tuple(
        DiscountAction(
            action_id=f"oatmeal-{int(depth * 100):02d}",
            scope="selected_oatmeal_products_stores",
            start=cutoff,
            end=cutoff + timedelta(weeks=1),
            discount_depth=depth,
            product_ids=product_ids,
        )
        for depth in config.candidate_discounts
    )
    # These immutable rows are persisted before `future` is materialized below.
    simulations = twin.compare(actions)
    frozen_rows = [
        {
            "simulation_id": item.simulation_id,
            "action_id": item.candidate_action.action_id,
            "discount": float(item.candidate_action.parameters["discount_depth"]),
            "disposition": item.disposition.value,
            "support_level": item.support["support_level"],
            "support": json.dumps(item.support, default=str),
            "evidence": json.dumps(item.evidence, default=str),
            "uncertainty": json.dumps(item.uncertainty, default=str),
            "outcomes": json.dumps(
                [value.model_dump(mode="json") for value in item.outcome_distributions]
            ),
            "generated_at": item.generated_at,
        }
        for item in simulations
    ]
    pl.DataFrame(frozen_rows).write_parquet(output / "frozen_simulations.parquet")

    _, future_all = split_at_cutoff(canonical, cutoff, config.holdout_weeks)
    future = future_all.filter(
        pl.col("sku_id").is_in(product_ids) & pl.col("store_id").is_in(store_ids)
    )
    model = cast(ContinuousDiscountBehaviorModel, twin.behavior_models["discount"])
    factual = _factual_evaluation(model, future)
    causal = {
        **observational_causal_status(),
        "diagnostics": {
            "treatment_density": model.diagnostics()["density"],
            "candidate_support": {
                row["action_id"]: row["support_level"] for row in frozen_rows
            },
            "hidden_confounding": "cannot be ruled out",
            "promotion_code_quality": "incomplete per source manual",
        },
    }

    volume_rows: list[dict[str, Any]] = []
    history_dates = selected_history["date"].unique().sort().to_list()
    for fraction in config.volume_fractions:
        volume_started = time.perf_counter()
        count = max(4, int(len(history_dates) * fraction))
        subset = selected_history.filter(pl.col("date").is_in(history_dates[:count]))
        try:
            subset_twin = TwinFactory().build_twin(
                f"dominicks-volume-{fraction}",
                "dominicks-historical",
                subset,
                WorldState(signals=(), as_of=cast(Any, subset["date"].max())),
                seed=config.seed,
                behavior_features=REAL_FEATURES,
            )
            subset_results = subset_twin.compare(actions)
            subset_result = subset_results[2]
            supported_doses = [
                float(item.candidate_action.parameters["discount_depth"])
                for item in subset_results
                if item.support["support_level"] != "UNSUPPORTED"
            ]
            width = next(
                value.p95 - value.p05
                for value in subset_result.outcome_distributions
                if value.outcome_name == "units"
            )
            subset_readiness = next(
                item.status.value
                for item in subset_twin.readiness().capabilities
                if item.capability == "discount"
            )
            subset_model = cast(
                ContinuousDiscountBehaviorModel, subset_twin.behavior_models["discount"]
            )
            subset_factual = _factual_evaluation(subset_model, future)
            volume_rows.append(
                {
                    "fraction": fraction,
                    "rows": subset.height,
                    "weeks": count,
                    "readiness": subset_readiness,
                    "support_level": subset_result.support["support_level"],
                    "disposition": subset_result.disposition.value,
                    "supported_action_min": min(supported_doses) if supported_doses else None,
                    "supported_action_max": max(supported_doses) if supported_doses else None,
                    "factual_demand_mae": subset_factual["demand"][
                        "dr_factual_at_observed_dose_bin"
                    ]["mae"],
                    "interval_width_units_90": width,
                    "runtime_seconds": time.perf_counter() - volume_started,
                    "error": None,
                }
            )
        except (ValueError, TypeError) as error:
            volume_rows.append(
                {
                    "fraction": fraction,
                    "rows": subset.height,
                    "weeks": count,
                    "readiness": "NOT_READY",
                    "support_level": "NOT_EVALUATED",
                    "disposition": "ABSTAIN",
                    "supported_action_min": None,
                    "supported_action_max": None,
                    "factual_demand_mae": None,
                    "interval_width_units_90": None,
                    "runtime_seconds": time.perf_counter() - volume_started,
                    "error": str(error),
                }
            )

    readiness = twin.readiness().model_dump(mode="json")
    cohorts = pl.DataFrame(
        [item.model_dump(mode="json") for item in twin.state.customer_states]
    )
    support = pl.DataFrame(
        [
            {"action_id": item.candidate_action.action_id, **item.support}
            for item in simulations
        ]
    )
    config_payload = {
        **asdict(config),
        "raw_dir": str(config.raw_dir),
        "output_dir": str(config.output_dir),
        "cutoff": str(cutoff),
        "future_end": str(future_end),
        "selected_products": product_ids,
        "selected_stores": store_ids,
        "selection_rule": "top pre-cutoff rows, then units; deterministic ID tie-break",
        "runtime_seconds": time.perf_counter() - started,
    }
    (output / "canonical_data_profile.json").write_text(
        profile.model_dump_json(indent=2), encoding="utf-8"
    )
    (output / "readiness.json").write_text(
        json.dumps(readiness, indent=2), encoding="utf-8"
    )
    (output / "factual_evaluation.json").write_text(
        json.dumps(factual, indent=2), encoding="utf-8"
    )
    (output / "causal_evaluation.json").write_text(
        json.dumps(causal, indent=2), encoding="utf-8"
    )
    (output / "config.json").write_text(
        json.dumps(config_payload, indent=2, default=str), encoding="utf-8"
    )
    cohorts.write_parquet(output / "cohorts.parquet")
    support.write_parquet(output / "support_diagnostics.parquet")
    pl.DataFrame(volume_rows).write_parquet(output / "data_volume_benchmark.parquet")
    ledger.close()
    _write_report(
        output,
        profile.model_dump(mode="json"),
        readiness,
        frozen_rows,
        factual,
        causal,
        volume_rows,
        config_payload,
    )
    return output


def _write_report(
    output: Path,
    profile: dict[str, Any],
    readiness: dict[str, Any],
    simulations: list[dict[str, Any]],
    factual: dict[str, Any],
    causal: dict[str, Any],
    volumes: list[dict[str, Any]],
    config: dict[str, Any],
) -> None:
    discount_readiness = next(
        item for item in readiness["capabilities"] if item["capability"] == "discount"
    )
    lines = [
        "# Real Commercial Twin — Dominick's Oatmeal",
        "",
        "> REAL HISTORICAL ACADEMIC DATA — NOT DEPLOYMENT OR CUSTOMER EVIDENCE",
        "",
        "Data source: Chicago Booth Kilts Center. Academic-research use; acknowledgement required.",
        "",
        f"Cutoff: `{config['cutoff']}`. Rows after cutoff were revealed only after "
        "simulations were persisted.",
        "",
        "## Data profile",
        "",
        f"- Canonical rows: {profile['rows_canonical']:,}",
        f"- Products/stores/weeks: {profile['products']} / {profile['stores']} / "
        f"{profile['history_weeks']}",
        f"- Selected pre-cutoff rows: {len(config['selected_products'])} products × "
        f"{len(config['selected_stores'])} stores",
        "- Discount is inferred from a strictly lagged 13-week reference price.",
        "- Inventory, customer IDs, returns, and external world state: NOT AVAILABLE.",
        "",
        "## Readiness",
        "",
        f"Discount capability: **{discount_readiness['status']}**",
        "",
        "## Frozen decision",
        "",
        "Question: what does pre-cutoff evidence support for selected oatmeal products/stores?",
        "",
        "| Discount | Support | Decision | Units mean [90%] | Revenue mean [90%] | "
        "Profit mean [90%] |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for item in simulations:
        outcomes = {
            value["outcome_name"]: value for value in json.loads(item["outcomes"])
        }
        lines.append(
            f"| {item['discount']:.0%} | {item['support_level']} | "
            f"{item['disposition']} | {_display_outcome(outcomes, 'units')} | "
            f"{_display_outcome(outcomes, 'revenue')} | "
            f"{_display_outcome(outcomes, 'contribution_profit')} |"
        )
    lines.extend(
        [
            "",
            "## Factual evaluation",
            "",
            "```json",
            json.dumps(factual, indent=2),
            "```",
            "",
            "## Counterfactual evaluation",
            "",
            f"**{causal['status']}** — {causal['reason']}",
            "",
            "## Data-volume benchmark",
            "",
            "| Fraction | Rows | Weeks | Readiness | Supported range | 10% decision | "
            "Factual MAE | Width | Runtime s |",
            "|---:|---:|---:|---|---|---|---:|---:|---:|",
        ]
    )
    for item in volumes:
        lines.append(
            f"| {item['fraction']:.0%} | {item['rows']} | {item['weeks']} | "
            f"{item['readiness']} | {item['supported_action_min']}–"
            f"{item['supported_action_max']} | {item['disposition']} | "
            f"{item['factual_demand_mae']} | {item['interval_width_units_90']} | "
            f"{item['runtime_seconds']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## What is not known",
            "",
            "Alternative-action outcomes are not observed, hidden confounding cannot be excluded, "
            "promotion flags are incomplete, inferred discount is not an observed list-price "
            "discount, "
            "and average acquisition cost is not replacement cost.",
        ]
    )
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
