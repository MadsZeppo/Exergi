from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from commercial_twin.commerce_contracts import (
    Customer,
    KlaviyoTwinAdapter,
    ShopifyTwinAdapter,
)
from commercial_twin.customer_twin_core import (
    ActionDefinition,
    ActionFamily,
    EvidenceBoundAnswerRenderer,
    EvidenceType,
    ExperimentDefinition,
    StateInteractionEvidence,
    TwinQuery,
    TwinQueryPlanner,
    deterministic_assignment,
    discount_action,
    revenue_shapley_decomposition,
    srm_check,
)
from commercial_twin.query_benchmark import QUERY_BENCHMARK
from decision_engine.ledger.store import PredictionLedger

NOW = datetime(2011, 11, 1, tzinfo=UTC)


def test_canonical_provenance_cannot_overlap() -> None:
    with pytest.raises(ValidationError):
        Customer(
            customer_id="hashed",
            observed_fields=frozenset({"country"}),
            derived_fields=frozenset({"country"}),
        )


def test_shopify_mapping_is_allowlisted() -> None:
    assert ShopifyTwinAdapter.map_standard_event("checkout_completed") == "CHECKOUT_COMPLETED"
    with pytest.raises(ValueError, match="unsupported"):
        ShopifyTwinAdapter.map_standard_event("invented_event")


def test_klaviyo_open_is_engagement_not_assignment() -> None:
    mapped = KlaviyoTwinAdapter.map_event("Opened Email", assigned_treatment=None)
    assert mapped["engagement"] is True
    assert mapped["causal_exposure"] is False


def test_revenue_shapley_reconciles_exactly_and_is_not_causal() -> None:
    earlier = {"buyers": 100.0, "orders_per_buyer": 2.0, "revenue_per_order": 10.0}
    later = {"buyers": 120.0, "orders_per_buyer": 1.5, "revenue_per_order": 12.0}
    result = revenue_shapley_decomposition(earlier, later)
    assert result["total_change"] == pytest.approx(160.0)
    assert sum(result[key] for key in earlier) == pytest.approx(result["total_change"])
    assert result["residual"] == 0


def test_query_suite_routes_at_least_95_percent() -> None:
    planner = TwinQueryPlanner()
    correct = 0
    for index, (text, intent, evidence) in enumerate(QUERY_BENCHMARK):
        plan = planner.plan(TwinQuery(query_id=str(index), text=text, as_of=NOW))
        correct += plan.intent == intent and plan.required_evidence_level == evidence
    assert correct / len(QUERY_BENCHMARK) >= 0.95


def test_unknown_query_fails_closed() -> None:
    plan = TwinQueryPlanner().plan(TwinQuery(query_id="x", text="Tell me a story", as_of=NOW))
    assert plan.required_evidence_level == EvidenceType.INSUFFICIENT


@pytest.mark.parametrize(
    ("evidence", "prefix"),
    [
        (EvidenceType.OBSERVED_IDENTITY, "Observed data show"),
        (EvidenceType.PREDICTIVE_ASSOCIATION, "predicted"),
        (EvidenceType.CAUSAL_RCT, "randomized evidence"),
        (EvidenceType.CAUSAL_OBSERVATIONAL, "identification assumptions"),
        (EvidenceType.INSUFFICIENT, "not have enough evidence"),
    ],
)
def test_evidence_renderer_enforces_wording(evidence: EvidenceType, prefix: str) -> None:
    rendered = EvidenceBoundAnswerRenderer().render_statement(evidence, "sales changed")
    assert prefix in rendered


def test_world_due_to_wording_requires_causal_evidence() -> None:
    with pytest.raises(ValidationError):
        StateInteractionEvidence(
            driver="sentiment",
            customer_segment="cohort_01",
            current_state="low",
            historical_reference="normal",
            interaction_estimate=0.1,
            uncertainty={},
            out_of_time_validation="NONE",
            geographic_alignment="MISALIGNED",
            evidence_type=EvidenceType.CONTEXT_ONLY,
            wording_allowed=True,
        )


def test_deterministic_experiment_assignment_is_stable() -> None:
    first = [deterministic_assignment("exp", str(index), 0.5) for index in range(100)]
    second = [deterministic_assignment("exp", str(index), 0.5) for index in range(100)]
    assert first == second
    assert 30 < sum(first) < 70


def test_srm_blocks_unbalanced_experiment() -> None:
    assert srm_check(900, 100, 0.5)["trusted"] is False
    assert srm_check(500, 500, 0.5)["trusted"] is True


def test_experiment_window_is_validated() -> None:
    action = ActionDefinition(action_id="email", family=ActionFamily.TARGETED_COMMUNICATION)
    with pytest.raises(ValidationError):
        ExperimentDefinition(
            experiment_id="exp",
            action=action,
            randomization_unit="customer",
            eligibility_rule="active",
            control="no_email",
            treatment="email",
            assignment_probability=0.5,
            primary_metric="purchase_30d",
            guardrails=("unsubscribe",),
            minimum_detectable_effect=0.01,
            planned_sample_size=1000,
            start_time=NOW,
            end_time=NOW - timedelta(days=1),
        )


def test_discount_query_never_routes_as_descriptive_or_predictive() -> None:
    plan = TwinQueryPlanner().plan(
        TwinQuery(query_id="discount", text="What happens with a 20% discount?", as_of=NOW)
    )
    assert plan.intent.value == "DECISION"
    assert plan.required_evidence_level == EvidenceType.CAUSAL_OBSERVATIONAL


def test_discount_action_contract_is_bounded() -> None:
    assert discount_action(10).parameters["percent"] == 10
    with pytest.raises(ValueError):
        discount_action(101)


def test_twin_ledger_freezes_answer_and_appends_outcome_once(tmp_path: Path) -> None:
    ledger = PredictionLedger(tmp_path / "ledger.duckdb")
    ledger.append_twin_query(
        query_id="q1",
        as_of=NOW,
        query_plan={"metric": "purchase_probability"},
        snapshot_version="v1",
        model_version="logistic-v1",
        answer_distribution={"mean": 0.2},
        evidence_type="PREDICTIVE_ASSOCIATION",
        validation_status="RANKING_ONLY",
    )
    ledger.append_twin_query_outcome(
        "q1", realized_outcome={"purchased": True}, calibration_update={"error": 0.8}
    )
    with pytest.raises(ValueError, match="already appended"):
        ledger.append_twin_query_outcome(
            "q1", realized_outcome={"purchased": False}, calibration_update={"error": 0.2}
        )
    ledger.close()
