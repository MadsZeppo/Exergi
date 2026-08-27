from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast

import polars as pl

from commercial_twin.cohorts import build_behavior_cohorts
from commercial_twin.readiness import assess_readiness
from commercial_twin.schemas import (
    CommercialState,
    CompanyState,
    ProductState,
    WorldState,
)
from commercial_twin.twin import CommercialTwin
from decision_engine.ledger import PredictionLedger
from decision_engine.registry import ModelPerformanceRegistry
from domains.commerce.behavior import ContinuousDiscountBehaviorModel

REQUIRED_COLUMNS = frozenset(
    {
        "date",
        "store_id",
        "category_id",
        "sku_id",
        "regular_price",
        "price",
        "discount",
        "observed_sales",
        "lagged_demand",
    }
)
ORACLE_COLUMNS = frozenset({"baseline_demand", "beta", "gamma", "hidden_u", "oracle_truth"})


class TwinFactory:
    @staticmethod
    def validate_data(history: pl.DataFrame) -> None:
        missing = REQUIRED_COLUMNS - set(history.columns)
        if missing:
            raise ValueError(f"canonical commercial data is missing: {sorted(missing)}")
        leaked = ORACLE_COLUMNS & set(history.columns)
        if leaked:
            raise ValueError(f"oracle fields are forbidden from twin input: {sorted(leaked)}")
        if history.is_empty():
            raise ValueError("canonical commercial data cannot be empty")
        minimum = cast(float, history["discount"].min())
        maximum = cast(float, history["discount"].max())
        if minimum < 0 or maximum > 0.30:
            raise ValueError("discount must lie in [0, 0.30]")

    def build_twin(
        self,
        twin_id: str,
        company_id: str,
        history: pl.DataFrame,
        world_state: WorldState,
        *,
        seed: int = 42,
        ledger: PredictionLedger | None = None,
        registry: ModelPerformanceRegistry | None = None,
        behavior_features: list[str] | None = None,
    ) -> CommercialTwin:
        self.validate_data(history)
        latest = history["date"].max()
        if isinstance(latest, datetime):
            as_of = latest.replace(tzinfo=latest.tzinfo or UTC)
        elif isinstance(latest, date):
            as_of = datetime.combine(latest, datetime.min.time(), tzinfo=UTC)
        else:
            raise ValueError("date column must contain date or datetime values")
        cost_expression = (
            pl.col("unit_cost").drop_nulls().last()
            if "unit_cost" in history.columns
            else pl.lit(None, dtype=pl.Float64)
        )
        inventory_expression = (
            pl.col("inventory").drop_nulls().last()
            if "inventory" in history.columns
            else pl.lit(None, dtype=pl.Float64)
        )
        product_rows = (
            history.sort("date")
            .group_by("sku_id")
            .agg(
                pl.col("category_id").last(),
                pl.col("price").last(),
                cost_expression.alias("unit_cost"),
                inventory_expression.alias("inventory"),
            )
            .sort("sku_id")
        )
        products = tuple(
            ProductState(
                product_id=str(row["sku_id"]),
                category_id=str(row["category_id"]),
                current_price=float(row["price"]),
                unit_cost=(float(row["unit_cost"]) if row["unit_cost"] is not None else None),
                inventory=(float(row["inventory"]) if row["inventory"] is not None else None),
            )
            for row in product_rows.iter_rows(named=True)
        )
        state = CommercialState(
            customer_states=build_behavior_cohorts(history, as_of),
            company_state=CompanyState(
                company_id=company_id,
                products=products,
                channels=("retail",),
                observed_at=as_of,
            ),
            world_state=world_state,
            as_of=as_of,
        )
        model = ContinuousDiscountBehaviorModel(features=behavior_features, seed=seed).fit(history)
        readiness = assess_readiness(
            twin_id,
            history,
            world_signal_count=len(world_state.signals),
        )
        return CommercialTwin(
            twin_id,
            state,
            {"discount": model},
            readiness,
            ledger=ledger,
            registry=registry,
        )

    @staticmethod
    def validate_twin(twin: CommercialTwin) -> tuple[str, ...]:
        issues: list[str] = []
        if "discount" not in twin.behavior_models:
            issues.append("missing discount behavior model")
        if not twin.state.company_state.products:
            issues.append("company state contains no products")
        if not twin.state.customer_states:
            issues.append("commercial state contains no customer cohorts")
        return tuple(issues)

    def update_twin(
        self,
        twin: CommercialTwin,
        history: pl.DataFrame,
        world_state: WorldState | None = None,
    ) -> CommercialTwin:
        return self.build_twin(
            twin.twin_id,
            twin.state.company_state.company_id,
            history,
            world_state or twin.state.world_state,
            ledger=twin.ledger,
            registry=twin.registry,
        )
