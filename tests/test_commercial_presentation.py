from __future__ import annotations

from datetime import UTC, datetime

from commercial_twin.presentation import DecisionOpportunity, build_commercial_twin_view
from commercial_twin.schemas import (
    CommercialState,
    CommercialTwinSnapshot,
    CompanyState,
    WorldState,
)
from decision_engine.core import (
    CandidateAction,
    DecisionDisposition,
    DecisionState,
    OutcomeDistribution,
    SimulationResult,
)


def _result(
    disposition: DecisionDisposition, *, customer_facing_do_this_enabled: bool = False
) -> SimulationResult:
    action = CandidateAction(
        action_id="discount-10", action_type="discount", parameters={"discount_depth": 0.1}
    )
    outcome = OutcomeDistribution(
        outcome_name="units",
        mean=100,
        p05=80,
        p10=85,
        p25=90,
        p50=100,
        p75=110,
        p90=115,
        p95=120,
        variance=100,
    )
    return SimulationResult(
        simulation_id="simulation-1",
        decision_id="decision-1",
        state_snapshot=DecisionState(state_id="state-1", values={}, observed_at=datetime.now(UTC)),
        candidate_action=action,
        outcome_distributions=(outcome,),
        disposition=disposition,
        evidence={
            "status": "observational",
            "customer_facing_do_this_enabled": customer_facing_do_this_enabled,
        },
        support={"support_level": "SUPPORTED"},
        uncertainty={"method": "test"},
        assumptions=("measured confounding only",),
        model_versions={"discount": "v1"},
        generated_at=datetime.now(UTC),
    )


def test_customer_facing_decision_language_and_why_payload() -> None:
    now = datetime.now(UTC)
    snapshot = CommercialTwinSnapshot(
        twin_id="twin",
        state=CommercialState(
            customer_states=(),
            company_state=CompanyState(company_id="brand", products=(), observed_at=now),
            world_state=WorldState(signals=(), as_of=now),
            as_of=now,
        ),
        model_versions={"discount": "v1"},
        created_at=now,
    )
    opportunity = DecisionOpportunity(
        decision_type="promotion",
        scope="all customers",
        candidate_action=_result(DecisionDisposition.EXPERIMENT).candidate_action,
        baseline_action=CandidateAction(action_id="none", action_type="discount"),
        expected_value_delta=2.0,
        reason="promising but uncertain",
        priority="REVIEW",
    )
    view = build_commercial_twin_view(
        snapshot,
        "What happens if we discount 10%?",
        (_result(DecisionDisposition.EXPERIMENT),),
        opportunity,
    )
    assert view.options[0].customer_decision == "TEST THIS"
    assert view.options[0].expected_demand == {"mean": 100.0, "lower": 80.0, "upper": 120.0}
    assert "support" in view.options[0].why
    assert view.opportunity is not None


def test_customer_facing_act_is_fail_closed_without_validated_gate() -> None:
    now = datetime.now(UTC)
    snapshot = CommercialTwinSnapshot(
        twin_id="twin",
        state=CommercialState(
            customer_states=(),
            company_state=CompanyState(company_id="brand", products=(), observed_at=now),
            world_state=WorldState(signals=(), as_of=now),
            as_of=now,
        ),
        model_versions={},
        created_at=now,
    )
    disabled = build_commercial_twin_view(snapshot, "Act?", (_result(DecisionDisposition.ACT),))
    enabled = build_commercial_twin_view(
        snapshot,
        "Act?",
        (_result(DecisionDisposition.ACT, customer_facing_do_this_enabled=True),),
    )
    assert disabled.options[0].customer_decision == "TEST THIS"
    assert enabled.options[0].customer_decision == "DO THIS"
