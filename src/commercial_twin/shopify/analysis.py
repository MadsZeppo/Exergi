"""Defensible observational Shopify diagnostics and non-causal decision cards."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from datetime import timedelta

from .contracts import (
    CanonicalOrder,
    CompanyState,
    CustomerState,
    DecisionCard,
    Diagnostic,
    EconomicAuthority,
    OrderEconomics,
    Recommendation,
)


def build_observational_diagnostics(
    orders: Iterable[CanonicalOrder],
    economics: Mapping[str, OrderEconomics],
    customer_states: Iterable[CustomerState],
    company: CompanyState,
    *,
    window_days: int = 30,
) -> tuple[Diagnostic, ...]:
    orders = tuple(
        order
        for order in orders
        if order.occurred_at <= company.as_of
        and order.observed_at <= company.as_of
        and not order.cancelled
    )
    current_start = company.as_of - timedelta(days=window_days)
    previous_start = current_start - timedelta(days=window_days)
    current = tuple(order for order in orders if current_start < order.occurred_at <= company.as_of)
    previous = tuple(
        order for order in orders if previous_start < order.occurred_at <= current_start
    )
    current_revenue = sum(order.net_revenue - order.refunds for order in current)
    previous_revenue = sum(order.net_revenue - order.refunds for order in previous)
    revenue_change = current_revenue - previous_revenue
    discounted_revenue = sum(
        order.net_revenue - order.refunds for order in current if order.discounts > 0
    )
    refund_current = sum(order.refunds for order in current)
    cooling = tuple(
        state for state in customer_states if state.lifecycle.value in {"COOLING", "DORMANT"}
    )
    economics_complete = company.economic_authority in {
        EconomicAuthority.OBSERVED_CONTRIBUTION_PROFIT,
        EconomicAuthority.ESTIMATED_CONTRIBUTION_PROFIT,
    }
    cp_current = _sum_complete_profit(current, economics)
    cp_previous = _sum_complete_profit(previous, economics)
    diagnostics = (
        Diagnostic(
            kind="PROFIT_REVENUE_DECOMPOSITION",
            title="Recent commercial movement",
            observation=(
                f"Net revenue changed by {revenue_change:.2f} {company.currency} versus the "
                f"preceding {window_days}-day window."
            ),
            metrics={
                "current_net_revenue": current_revenue,
                "previous_net_revenue": previous_revenue,
                "net_revenue_change": revenue_change,
                "current_contribution_profit": cp_current,
                "previous_contribution_profit": cp_previous,
            },
        ),
        Diagnostic(
            kind="REPEAT_BEHAVIOR_CHANGE",
            title="Customers beyond normal purchase cadence",
            observation=(
                f"{len(cooling)} customers are cooling or dormant relative to observed history. "
                "This is descriptive and does not identify the effect of a win-back action."
            ),
            metrics={"affected_customers": len(cooling), "known_customers": company.customer_count},
        ),
        Diagnostic(
            kind="DISCOUNT_LEAKAGE",
            title="Revenue associated with discounts",
            observation=(
                "Discounted-order revenue share is an association, not incremental discount value."
            ),
            metrics={
                "discounted_revenue": discounted_revenue,
                "discounted_revenue_share": (
                    discounted_revenue / current_revenue if current_revenue else 0.0
                ),
                "discount_rate": company.discount_rate,
            },
        ),
        Diagnostic(
            kind="RETURN_REFUND_ANOMALY",
            title="Refund pressure",
            observation=(
                f"Refunds in the recent window total {refund_current:.2f} {company.currency}."
            ),
            metrics={"recent_refunds": refund_current, "overall_refund_rate": company.refund_rate},
        ),
        Diagnostic(
            kind="DATA_READINESS",
            title="Evidence boundary",
            observation=(
                "Contribution profit is available with explicit authority."
                if economics_complete
                else "Cost coverage is incomplete; Exergi is limited to net-revenue diagnostics."
            ),
            metrics={
                "economic_authority": company.economic_authority.value,
                **company.completeness,
            },
        ),
    )
    return diagnostics


def build_first_decision_card(
    company: CompanyState,
    diagnostics: Iterable[Diagnostic],
    *,
    created_at: object | None = None,
) -> DecisionCard:
    del created_at
    diagnostics = tuple(diagnostics)
    repeat = next(item for item in diagnostics if item.kind == "REPEAT_BEHAVIOR_CHANGE")
    affected_value = repeat.metrics["affected_customers"]
    if not isinstance(affected_value, (int, float)):
        raise ValueError("affected customer metric must be numeric")
    affected = int(affected_value)
    enough_history = company.order_count >= 30 and company.customer_count >= 20
    recommendation = (
        Recommendation.TEST
        if affected > 0 and enough_history
        else Recommendation.NOT_ENOUGH_EVIDENCE
    )
    reason_codes = ["OBSERVATIONAL_ONLY", "NO_RANDOMIZED_ACTION_EFFECT"]
    if not enough_history:
        reason_codes.append("LIMITED_HISTORY")
    if company.economic_authority in {
        EconomicAuthority.NET_REVENUE_ONLY,
        EconomicAuthority.GROSS_REVENUE_ONLY,
        EconomicAuthority.DATA_NOT_READY,
    }:
        reason_codes.append("INCOMPLETE_COST_COVERAGE")
    fingerprint = hashlib.sha256(
        f"{company.shop_id}:{company.as_of.isoformat()}:repeat-cadence".encode()
    ).hexdigest()[:20]
    return DecisionCard(
        id=f"decision-{fingerprint}",
        created_at=company.as_of,
        observation=repeat.observation,
        economic_significance=(
            "Observed repeat revenue/profit is economically material only as a historical gap; "
            "incremental recoverable value is not identified."
        ),
        affected_population=f"{affected} cooling or dormant observed customers",
        business_as_usual="Continue the current customer-contact policy.",
        possible_action="Merchant-approved controlled holdout test of one bounded win-back action.",
        scenario_range=(None, None),
        downside="Contact cost, discount cost, fatigue and possible margin dilution.",
        data_basis=(
            "Shopify order and refund history",
            "Point-in-time purchase cadence",
            company.economic_authority.value,
        ),
        uncertainty=(
            "Historical behavior cannot identify the counterfactual response to a new action."
        ),
        evidence_authority="OBSERVATIONAL_DESCRIPTIVE",
        reason_codes=tuple(reason_codes),
        recommendation=recommendation,
        assumptions=tuple(key for key, value in company.completeness.items() if value < 1.0),
        what_changes_view=(
            "Mature merchant-specific randomized holdout outcomes",
            "Complete contribution-cost coverage",
            "Stable result across a preregistered temporal window",
        ),
    )


def _sum_complete_profit(
    orders: Iterable[CanonicalOrder], economics: Mapping[str, OrderEconomics]
) -> float | None:
    values = [
        economics[order.source_id].contribution_profit.amount
        for order in orders
        if order.source_id in economics
    ]
    total = 0.0
    if not values:
        return None
    for value in values:
        if value is None:
            return None
        total += value
    return total
