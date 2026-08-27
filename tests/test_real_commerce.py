from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from commercial_twin.factory import TwinFactory
from commercial_twin.schemas import WorldState
from decision_engine.datasets.dominicks import DominicksDataset
from decision_engine.synthetic.retail import RetailWorldConfig, generate_retail_world
from domains.commerce.real_runner import (
    RealTwinRunConfig,
    observational_causal_status,
    split_at_cutoff,
)


def _write_dominicks_fixture(root: Path, *, missing_profit: bool = False) -> None:
    rows = []
    for week in range(91, 111):
        price = 2.0 if week % 4 else 1.8
        rows.append(
            {
                "STORE": 2,
                "UPC": 111,
                "WEEK": week,
                "MOVE": 10 + week % 3,
                "QTY": 1,
                "PRICE": price,
                "SALE": "S" if price < 2 else None,
                "PROFIT": None if missing_profit else 25.0,
                "OK": 1,
                "PRICE_HEX": "x",
                "PROFIT_HEX": "x",
            }
        )
    pl.DataFrame(rows).write_csv(root / "woat.csv")
    pl.DataFrame(
        {
            "COM_CODE": [310],
            "UPC": [111],
            "DESCRIP": ["OATMEAL"],
            "SIZE": ["10 OZ"],
            "CASE": [12],
            "NITEM": [1],
        }
    ).write_csv(root / "upcoat.csv")


def test_real_adapter_maps_observed_and_inferred_fields(tmp_path: Path) -> None:
    _write_dominicks_fixture(tmp_path)
    frame, report = DominicksDataset(tmp_path).load_canonical()
    assert frame.height > 0
    assert frame["sku_id"].unique().to_list() == ["111"]
    assert frame["date"].dtype == pl.Datetime("us", "UTC")
    assert frame["discount"].max() > 0
    assert "discount" in report.inferred_fields
    assert "inventory" in report.unavailable_fields


def test_real_adapter_preserves_missing_cost(tmp_path: Path) -> None:
    _write_dominicks_fixture(tmp_path, missing_profit=True)
    frame, report = DominicksDataset(tmp_path).load_canonical()
    assert frame["unit_cost"].null_count() == frame.height
    assert report.missingness["unit_cost"] == 1.0


def test_strict_cutoff_prevents_future_rows() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    frame = pl.DataFrame(
        {"date": [start + timedelta(weeks=index) for index in range(10)]}
    )
    cutoff = start + timedelta(weeks=7)
    history, future = split_at_cutoff(frame, cutoff, 2)
    assert history["date"].max() < cutoff
    assert future["date"].min() >= cutoff
    assert future["date"].max() < cutoff + timedelta(weeks=2)


def test_observational_data_never_claims_counterfactual_truth() -> None:
    status = observational_causal_status()
    assert status["status"] == "NOT_IDENTIFIABLE"
    assert status["randomized_experiment_used"] is False


def test_factory_accepts_explicitly_missing_inventory() -> None:
    history = generate_retail_world(
        RetailWorldConfig(stores=2, categories=2, skus=4, days=60, seed=31)
    ).frame.drop("inventory", "marketing")
    world = WorldState(signals=(), as_of=datetime.now(UTC))
    twin = TwinFactory().build_twin(
        "real-like",
        "company",
        history,
        world,
        behavior_features=[
            "store_id", "category_id", "sku_id", "regular_price", "weekday",
            "product_age", "lagged_demand",
        ],
    )
    assert all(product.inventory is None for product in twin.state.company_state.products)
    assert twin.state.world_state.signals == ()


def test_real_volume_config_is_deterministic() -> None:
    first = RealTwinRunConfig(seed=7)
    second = RealTwinRunConfig(seed=7)
    assert first.volume_fractions == second.volume_fractions
    assert first.candidate_discounts == second.candidate_discounts
