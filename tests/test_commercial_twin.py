from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from commercial_twin.factory import TwinFactory
from commercial_twin.schemas import (
    CausalRole,
    CommercialOutcome,
    TemporalCausalMetadata,
    WorldSignal,
    WorldState,
)
from decision_engine.core import DecisionDisposition, OutcomeDistribution, SimulationResult
from decision_engine.ledger import PredictionLedger
from decision_engine.registry import ModelPerformanceRegistry
from domains.commerce.actions import DiscountAction, PriceChangeAction
from domains.commerce.fixtures import build_synthetic_commercial_twin


@pytest.fixture(scope="module")
def fixture():  # type: ignore[no-untyped-def]
    return build_synthetic_commercial_twin(seed=17)


def _action(depth: float = 0.10, action_id: str = "discount-10") -> DiscountAction:
    now = datetime.now(UTC)
    return DiscountAction(
        action_id=action_id,
        scope="all_products",
        start=now,
        end=now + timedelta(days=7),
        discount_depth=depth,
    )


def test_temporal_metadata_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        TemporalCausalMetadata(
            observed_at=datetime(2025, 1, 1),
            source="test",
            causal_role=CausalRole.PRE_TREATMENT,
        )


def test_typed_actions_and_action_horizon() -> None:
    action = _action()
    assert action.action_type == "discount"
    with pytest.raises(ValueError):
        _action(0.31)
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="cannot precede"):
        PriceChangeAction(
            action_id="bad",
            scope="all",
            start=now,
            end=now - timedelta(days=1),
            relative_change=0.1,
        )


def test_factory_builds_states_and_deterministic_cohorts(fixture) -> None:  # type: ignore[no-untyped-def]
    twin = fixture.twin
    assert twin.state.customer_states
    assert twin.state.company_state.products
    assert [c.cohort_id for c in twin.state.customer_states] == sorted(
        c.cohort_id for c in twin.state.customer_states
    )
    assert TwinFactory().validate_twin(twin) == ()


def test_oracle_isolation_is_enforced(fixture) -> None:  # type: ignore[no-untyped-def]
    oracle_names = {"baseline_demand", "beta", "gamma", "hidden_u"}
    assert not (oracle_names & set(fixture.canonical_history.columns))
    bad = fixture.canonical_history.with_columns(pl.lit(1.0).alias("oracle_truth"))
    with pytest.raises(ValueError, match="oracle"):
        TwinFactory.validate_data(bad)


def test_simulation_returns_typed_distributions_and_support(fixture) -> None:  # type: ignore[no-untyped-def]
    result = fixture.twin.simulate(_action())
    assert isinstance(result, SimulationResult)
    assert {d.outcome_name for d in result.outcome_distributions} == {
        "units",
        "revenue",
        "contribution_profit",
    }
    assert all(d.p05 <= d.p50 <= d.p95 for d in result.outcome_distributions)
    assert result.support["support_level"] in {"SUPPORTED", "LIMITED", "UNSUPPORTED"}
    assert "hidden-confounding absence" not in " ".join(result.assumptions).lower()


def test_compare_preserves_action_order(fixture) -> None:  # type: ignore[no-untyped-def]
    results = fixture.twin.compare((_action(0.05, "five"), _action(0.15, "fifteen")))
    assert [item.candidate_action.action_id for item in results] == ["five", "fifteen"]


def test_untrained_world_signals_have_no_manual_effect(fixture) -> None:  # type: ignore[no-untyped-def]
    twin = fixture.twin
    baseline = twin.simulate(_action(0.10, "baseline"))
    old = twin.state
    high = WorldState(
        signals=(
            WorldSignal(
                signal_name="consumer_confidence",
                value=1.30,
                observed_at=old.as_of,
                source="test",
            ),
            WorldSignal(
                signal_name="seasonal_demand_index",
                value=1.20,
                observed_at=old.as_of,
                source="test",
            ),
        ),
        as_of=old.as_of,
    )
    twin.state = old.model_copy(update={"world_state": high})
    changed = twin.simulate(_action(0.10, "changed"))
    twin.state = old
    assert twin.state.customer_states == old.customer_states
    assert twin.state.company_state == old.company_state
    assert changed.outcome_distributions[0].mean == pytest.approx(
        baseline.outcome_distributions[0].mean
    )
    assert changed.evidence["world_state_features_used"] == []
    assert "world_multiplier" not in changed.evidence


def test_readiness_is_decomposed_by_capability(fixture) -> None:  # type: ignore[no-untyped-def]
    report = fixture.twin.readiness()
    by_name = {item.capability: item for item in report.capabilities}
    assert by_name["discount"].components["treatment_support"]
    assert by_name["price_change"].status.value == "NOT_READY"
    assert "score" not in report.model_dump()


def test_unsupported_discount_never_acts(fixture) -> None:  # type: ignore[no-untyped-def]
    result = fixture.twin.simulate(_action(0.30, "boundary"))
    if result.support["support_level"] == "UNSUPPORTED":
        assert result.disposition == DecisionDisposition.ABSTAIN


def test_ledger_and_registry_capture_simulation_and_outcome(tmp_path, fixture) -> None:  # type: ignore[no-untyped-def]
    ledger = PredictionLedger(tmp_path / "ledger.duckdb")
    registry = ModelPerformanceRegistry(tmp_path / "registry.duckdb")
    twin = fixture.twin
    old_ledger, old_registry = twin.ledger, twin.registry
    twin.ledger, twin.registry = ledger, registry
    result = twin.simulate(_action(0.08, "persisted"))
    predicted = {item.outcome_name: item.mean for item in result.outcome_distributions}
    outcomes = tuple(
        CommercialOutcome(
            outcome_name=name,
            value=value * 1.01,
            observed_at=datetime.now(UTC),
            action_id="persisted",
        )
        for name, value in predicted.items()
    )
    record = twin.update(result.simulation_id, outcomes)
    assert record.errors
    simulation_count = ledger.connection.execute(
        "SELECT count(*) FROM simulation_predictions"
    ).fetchone()[0]
    performance_count = registry.connection.execute(
        "SELECT count(*) FROM decision_performance_v2"
    ).fetchone()[0]
    assert simulation_count == 1
    assert performance_count == 1
    twin.ledger, twin.registry = old_ledger, old_registry
    ledger.close()
    registry.close()


def test_outcome_distribution_rejects_crossing_quantiles() -> None:
    with pytest.raises(ValueError, match="nondecreasing"):
        OutcomeDistribution(
            outcome_name="profit",
            mean=10,
            p05=1,
            p10=2,
            p25=3,
            p50=10,
            p75=9,
            p90=12,
            p95=13,
            variance=1,
        )
