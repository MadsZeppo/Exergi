from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl

from commercial_twin.population_contracts import DriverEvidence, RelationshipType
from commercial_twin.population_factory import CustomerTwinFactory
from commercial_twin.population_ingestion import Rees46EventAdapter
from commercial_twin.population_models import build_future_outcomes, simulate_population
from commercial_twin.population_state import (
    attach_affinities,
    build_cohorts,
    build_customer_states,
)


def _events() -> pl.DataFrame:
    start = datetime(2021, 1, 1, tzinfo=UTC)
    rows = []
    for customer in range(12):
        for day, event_type in ((0, "view"), (5, "cart"), (10, "purchase")):
            if event_type == "purchase" and customer % 2:
                continue
            rows.append(
                {
                    "event_time": start + timedelta(days=day + customer),
                    "customer_id": str(customer),
                    "session_id": f"s-{customer}-{day}",
                    "event_type": event_type,
                    "product_id": str(customer % 3),
                    "category_id": str(customer % 2),
                    "brand": "brand",
                    "price": float(10 + customer),
                    "quantity": None,
                    "discount": None,
                    "order_id": None,
                    "channel": None,
                    "return_flag": None,
                    "geography": None,
                }
            )
    return pl.DataFrame(rows)


def test_rees46_mapping_is_canonical_and_explicit_about_unavailable_fields() -> None:
    raw = pl.DataFrame(
        {
            "event_time": ["2021-01-01 00:00:00 UTC"],
            "event_type": ["view"],
            "product_id": [1],
            "category_id": [2],
            "brand": ["x"],
            "price": [3.0],
            "user_id": [4],
            "user_session": ["s"],
        }
    )
    mapped = Rees46EventAdapter.map_frame(raw)
    assert mapped["customer_id"].item() == "4"
    assert Rees46EventAdapter.field_status()["geography"].value == "NOT_AVAILABLE"


def test_state_uses_only_events_at_or_before_as_of_and_shrinks_sparse_customers() -> None:
    events = _events()
    as_of = datetime(2021, 1, 15, tzinfo=UTC)
    state = build_customer_states(events, as_of)
    assert state["as_of"].max() == as_of
    sparse = state.sort("observation_count").row(0, named=True)
    dense = state.sort("observation_count", descending=True).row(0, named=True)
    assert sparse["shrinkage_strength"] <= dense["shrinkage_strength"]
    changed_future = pl.concat(
        [
            events,
            events.head(1).with_columns(
                pl.lit(datetime(2022, 1, 1, tzinfo=UTC)).alias("event_time")
            ),
        ]
    )
    assert build_customer_states(changed_future, as_of).equals(state)


def test_cohorts_are_deterministic_and_population_factory_updates_and_compares() -> None:
    events = _events()
    as_of = datetime(2021, 1, 20, tzinfo=UTC)
    state = attach_affinities(events, build_customer_states(events, as_of), as_of)
    first, _ = build_cohorts(state, n_cohorts=3, seed=7)
    second, _ = build_cohorts(state, n_cohorts=3, seed=7)
    assert first["cohort_id"].to_list() == second["cohort_id"].to_list()
    built = CustomerTwinFactory.from_events(events, as_of=as_of, n_cohorts=3)
    later_events = events.head(2).with_columns(
        pl.lit(datetime(2021, 2, 1, tzinfo=UTC)).alias("event_time")
    )
    later = built.engine.update_population(later_events)
    comparison = built.engine.compare_population(built.snapshot, later)
    assert not comparison.causal_interpretation_allowed


def test_future_outcomes_and_probabilistic_simulation_are_deterministic() -> None:
    events = _events()
    cutoff = datetime(2021, 1, 10, tzinfo=UTC)
    states = build_customer_states(events, cutoff)
    outcomes = build_future_outcomes(events, states, cutoff, cutoff + timedelta(days=30))
    assert {"purchase", "orders", "spend"} <= set(outcomes.columns)
    first = simulate_population(
        np.full(10, 0.2), np.full(10, 0.3), np.full(10, 4.0), draws=20, seed=9
    )
    second = simulate_population(
        np.full(10, 0.2), np.full(10, 0.3), np.full(10, 4.0), draws=20, seed=9
    )
    assert first == second
    assert first["buyers"]["lower_90"] <= first["buyers"]["mean"] <= first["buyers"]["upper_90"]


def test_predictive_driver_never_uses_causal_wording() -> None:
    evidence = DriverEvidence(
        driver_name="recent views",
        driver_value=4,
        relationship_type=RelationshipType.PREDICTIVE,
        effect_direction="higher",
        validation_scope="out-of-time customer prediction",
        support="SUPPORTED",
        explanation_allowed=True,
    )
    explanation = evidence.safe_explanation()
    assert explanation.startswith("Under current")
    assert "Because" not in explanation
