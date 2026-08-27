from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import polars as pl

from commercial_twin.world_state import CachedWorldStateProvider
from decision_engine.datasets.dominicks import DominicksDataset
from domains.commerce.behavior import ContinuousDiscountBehaviorModel
from domains.commerce.real_runner import REAL_FEATURES, _factual_evaluation, _select_scope


@dataclass(frozen=True)
class WorldAblationConfig:
    raw_dir: Path = Path("data/raw/dominicks/oatmeal")
    output_dir: Path = Path("artifacts/world_state/dominicks-oatmeal-v1")
    seed: int = 42
    final_cutoff_fraction: float = 0.80
    development_holdout_weeks: int = 8
    final_holdout_weeks: int = 8
    products: int = 8
    stores: int = 8
    geography: str = "IL"
    commerce_category: str = "oatmeal"


def attach_world_features(
    frame: pl.DataFrame,
    provider: CachedWorldStateProvider,
    geography: str,
    commerce_category: str,
) -> pl.DataFrame:
    dates = frame["date"].unique().sort().to_list()
    rows = [
        {
            "date": value,
            **provider.feature_row(value, geography, commerce_category),
        }
        for value in dates
    ]
    world = pl.DataFrame(rows)
    return frame.join(world, on="date", how="left", validate="m:1")


def _evaluate_model(
    name: str,
    train: pl.DataFrame,
    evaluation: pl.DataFrame,
    features: list[str],
    seed: int,
) -> tuple[dict[str, Any], ContinuousDiscountBehaviorModel]:
    started = time.perf_counter()
    model = ContinuousDiscountBehaviorModel(features=features, seed=seed).fit(train)
    result = _factual_evaluation(model, evaluation)
    result.update(
        {
            "model": name,
            "features": features,
            "runtime_seconds": time.perf_counter() - started,
        }
    )
    return result, model


def run_world_state_ablation(config: WorldAblationConfig | None = None) -> Path:
    config = config or WorldAblationConfig()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    provider = CachedWorldStateProvider()
    canonical, _ = DominicksDataset(config.raw_dir).load_canonical()
    dates = canonical["date"].unique().sort().to_list()
    final_cutoff = dates[int(len(dates) * config.final_cutoff_fraction)]
    pre_final = canonical.filter(pl.col("date") < final_cutoff)
    selected, product_ids, store_ids = _select_scope(
        pre_final, config.products, config.stores
    )
    scoped = canonical.filter(
        pl.col("sku_id").is_in(product_ids) & pl.col("store_id").is_in(store_ids)
    )
    enriched = attach_world_features(
        scoped, provider, config.geography, config.commerce_category
    )
    cpi_features = sorted(
        name for name in enriched.columns if name.startswith("category_cpi_")
    )
    development_cutoff = final_cutoff - timedelta(weeks=config.development_holdout_weeks)
    development_train = enriched.filter(pl.col("date") < development_cutoff)
    development_test = enriched.filter(
        (pl.col("date") >= development_cutoff) & (pl.col("date") < final_cutoff)
    )
    final_train = enriched.filter(pl.col("date") < final_cutoff)
    final_test = enriched.filter(
        (pl.col("date") >= final_cutoff)
        & (pl.col("date") < final_cutoff + timedelta(weeks=config.final_holdout_weeks))
    )
    development_results = []
    for name, features in (
        ("A_CUSTOMER_COMPANY_ONLY", REAL_FEATURES),
        ("D_PLUS_CATEGORY_CPI", REAL_FEATURES + cpi_features),
    ):
        result, _ = _evaluate_model(
            name, development_train, development_test, features, config.seed
        )
        development_results.append(result)
    selected_name = min(
        development_results,
        key=lambda item: item["demand"]["dr_factual_at_observed_dose_bin"]["mae"],
    )["model"]
    selected_features = (
        REAL_FEATURES + cpi_features
        if selected_name == "D_PLUS_CATEGORY_CPI"
        else REAL_FEATURES
    )
    final_results: list[dict[str, Any]] = []
    models: dict[str, ContinuousDiscountBehaviorModel] = {}
    for name, features in (
        ("A_CUSTOMER_COMPANY_ONLY", REAL_FEATURES),
        ("D_PLUS_CATEGORY_CPI", REAL_FEATURES + cpi_features),
        ("G_DEVELOPMENT_SELECTED", selected_features),
    ):
        result, model = _evaluate_model(name, final_train, final_test, features, config.seed)
        final_results.append(result)
        models[name] = model
    z_name = "category_cpi_trailing_z"
    regime_results: list[dict[str, Any]] = []
    if z_name in final_test.columns:
        threshold = float(cast(Any, final_train[z_name].abs().median()))
        regime = final_test.filter(pl.col(z_name).abs() >= threshold)
        for name in ("A_CUSTOMER_COMPANY_ONLY", "D_PLUS_CATEGORY_CPI"):
            evaluation = _factual_evaluation(models[name], regime)
            regime_results.append(
                {
                    "model": name,
                    "regime": "absolute CPI z at/above training median",
                    "rows": regime.height,
                    "demand_mae": evaluation["demand"][
                        "dr_factual_at_observed_dose_bin"
                    ]["mae"],
                }
            )
    unavailable = {
        "B_PLUS_INCOME": "NOT_TESTABLE_ON_DOMINICKS: no cached historical vintages",
        "C_PLUS_CREDIT_STRESS": "NOT_TESTABLE_ON_DOMINICKS: no cached historical vintages",
        "E_PLUS_SENTIMENT": "NOT_TESTABLE_ON_DOMINICKS: final series is not vintage-safe",
        "F_PLUS_GAS_PRICE": "NOT_TESTABLE_ON_DOMINICKS: historical revisions unavailable",
    }
    payload = {
        "dataset": "Dominick's Oatmeal",
        "final_cutoff": str(final_cutoff),
        "development_cutoff": str(development_cutoff),
        "selection_rule": "minimum development factual DR demand MAE; final holdout untouched",
        "development_selected_model": selected_name,
        "cpi_features": cpi_features,
        "development_results": development_results,
        "final_results": final_results,
        "regime_results": regime_results,
        "unavailable_ablations": unavailable,
        "coverage": provider.coverage_report(),
    }
    (config.output_dir / "world_ablation.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    pl.DataFrame(
        [
            {
                "model": item["model"],
                "demand_mae": item["demand"]["dr_factual_at_observed_dose_bin"]["mae"],
                "demand_rmse": item["demand"]["dr_factual_at_observed_dose_bin"]["rmse"],
                "demand_bias": item["demand"]["dr_factual_at_observed_dose_bin"]["bias"],
                "revenue_mae": item["revenue"]["mae"],
                "profit_mae": item["contribution_profit"]["mae"],
                "coverage_90": item["interval_90"]["coverage"],
                "interval_width_90": item["interval_90"]["average_width"],
                "wis_90": item["interval_90"]["wis_90_single_interval"],
                "runtime_seconds": item["runtime_seconds"],
            }
            for item in final_results
        ]
    ).write_parquet(config.output_dir / "world_ablation_results.parquet")
    return config.output_dir
