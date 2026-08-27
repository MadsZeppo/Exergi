from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import polars as pl

from commercial_twin.factory import TwinFactory
from commercial_twin.schemas import WorldSignal, WorldState
from commercial_twin.twin import CommercialTwin
from decision_engine.synthetic.retail import RetailWorld, RetailWorldConfig, generate_retail_world


@dataclass(frozen=True)
class SyntheticCommercialTwinFixture:
    twin: CommercialTwin
    canonical_history: pl.DataFrame
    oracle: RetailWorld


def build_synthetic_commercial_twin(
    *,
    seed: int = 42,
    support: str = "good",
    hidden_confounding: bool = False,
    world_multiplier: float = 1.0,
) -> SyntheticCommercialTwinFixture:
    oracle = generate_retail_world(
        RetailWorldConfig(
            stores=2,
            categories=3,
            skus=9,
            days=100,
            support=support,
            hidden_confounding=hidden_confounding,
            seed=seed,
        )
    )
    # Oracle arrays deliberately remain on the evaluation fixture, never in canonical history.
    history = oracle.frame
    now = datetime.now(UTC)
    world = WorldState(
        signals=(
            WorldSignal(
                signal_name="consumer_confidence",
                value=world_multiplier,
                observed_at=now,
                source="synthetic_fixture",
            ),
            WorldSignal(
                signal_name="seasonal_demand_index",
                value=world_multiplier,
                observed_at=now,
                source="synthetic_fixture",
            ),
        ),
        as_of=now,
    )
    twin = TwinFactory().build_twin(
        "synthetic-commerce", "synthetic-company", history, world, seed=seed
    )
    return SyntheticCommercialTwinFixture(twin=twin, canonical_history=history, oracle=oracle)
