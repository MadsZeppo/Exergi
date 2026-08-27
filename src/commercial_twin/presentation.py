from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from commercial_twin.schemas import CommercialTwinSnapshot
from decision_engine.core import CandidateAction, DecisionDisposition, SimulationResult


def _interval(outcomes: dict[str, Any], name: str) -> dict[str, float] | None:
    value = outcomes.get(name)
    return (
        {"mean": value.mean, "lower": value.p05, "upper": value.p95} if value is not None else None
    )


class DecisionOpportunity(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_type: str
    scope: str
    candidate_action: CandidateAction
    baseline_action: CandidateAction
    expected_value_delta: float
    evidence: dict[str, Any] = Field(default_factory=dict)
    reason: str
    priority: str


class WhatIfCard(BaseModel):
    model_config = ConfigDict(frozen=True)
    action_id: str
    action_label: str
    customer_decision: str
    expected_demand: dict[str, float] | None = None
    expected_revenue: dict[str, float] | None = None
    expected_contribution_profit: dict[str, float] | None = None
    support_level: str
    evidence_summary: str
    why: dict[str, Any]


class CommercialTwinView(BaseModel):
    model_config = ConfigDict(frozen=True)
    title: str = "COMMERCIAL TWIN"
    current_state: CommercialTwinSnapshot
    question: str
    options: tuple[WhatIfCard, ...]
    opportunity: DecisionOpportunity | None = None
    caveats: tuple[str, ...] = ()


def _customer_decision(
    disposition: DecisionDisposition, *, customer_facing_do_this_enabled: bool
) -> str:
    if disposition == DecisionDisposition.ACT and not customer_facing_do_this_enabled:
        return "TEST THIS"
    return {
        DecisionDisposition.ACT: "DO THIS",
        DecisionDisposition.EXPERIMENT: "TEST THIS",
        DecisionDisposition.ABSTAIN: "NOT ENOUGH EVIDENCE",
    }[disposition]


def build_commercial_twin_view(
    snapshot: CommercialTwinSnapshot,
    question: str,
    results: tuple[SimulationResult, ...],
    opportunity: DecisionOpportunity | None = None,
) -> CommercialTwinView:
    cards: list[WhatIfCard] = []
    for result in results:
        outcomes = {item.outcome_name: item for item in result.outcome_distributions}

        depth = result.candidate_action.parameters.get("discount_depth")
        label = (
            f"{float(depth):.0%} discount"
            if depth is not None
            else result.candidate_action.action_id
        )
        cards.append(
            WhatIfCard(
                action_id=result.candidate_action.action_id,
                action_label=label,
                customer_decision=_customer_decision(
                    result.disposition,
                    customer_facing_do_this_enabled=(
                        result.evidence.get("customer_facing_do_this_enabled") is True
                    ),
                ),
                expected_demand=_interval(outcomes, "units"),
                expected_revenue=_interval(outcomes, "revenue"),
                expected_contribution_profit=_interval(outcomes, "contribution_profit"),
                support_level=str(result.support.get("support_level", "UNKNOWN")),
                evidence_summary=(
                    "Supported observational estimate"
                    if result.disposition == DecisionDisposition.ACT
                    else "More evidence is required before commitment"
                ),
                why={
                    "support": result.support,
                    "evidence": result.evidence,
                    "uncertainty": result.uncertainty,
                    "assumptions": result.assumptions,
                },
            )
        )
    return CommercialTwinView(
        current_state=snapshot,
        question=question,
        options=tuple(cards),
        opportunity=opportunity,
        caveats=(
            "Predictions are conditional on measured pre-treatment context.",
            "Unsupported actions are withheld; hidden confounding is not ruled out.",
        ),
    )
