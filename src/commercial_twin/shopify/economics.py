"""Deterministic, authority-carrying contribution-profit reconstruction."""

from __future__ import annotations

from .contracts import (
    CanonicalOrder,
    EconomicAssumptions,
    EconomicAuthority,
    MoneyComponent,
    OrderEconomics,
    ValueAuthority,
)


def reconstruct_order_economics(
    order: CanonicalOrder,
    *,
    assumptions: EconomicAssumptions | None = None,
    observed_payment_fees: float | None = None,
    observed_shipping_cost: float | None = None,
    observed_fulfillment_cost: float | None = None,
    observed_action_cost: float | None = None,
) -> OrderEconomics:
    currency = order.currency
    cogs_values = [line.cogs.amount for line in order.lines]
    cogs = sum(value for value in cogs_values if value is not None) if cogs_values else None
    if any(value is None for value in cogs_values) or not cogs_values:
        cogs = None
    payment = _cost_component(
        observed_payment_fees,
        _assumed_payment_fee(order, assumptions),
        currency,
        "Shopify Payments balance transaction",
        assumptions,
    )
    shipping = _cost_component(
        observed_shipping_cost,
        assumptions.shipping_cost_per_order if assumptions else None,
        currency,
        "observed merchant shipping cost",
        assumptions,
    )
    fulfillment = _cost_component(
        observed_fulfillment_cost,
        assumptions.fulfillment_cost_per_order if assumptions else None,
        currency,
        "observed fulfillment cost",
        assumptions,
    )
    action = _cost_component(
        observed_action_cost,
        assumptions.action_cost_per_order if assumptions else None,
        currency,
        "observed action cost",
        assumptions,
    )
    cogs_component = MoneyComponent(
        cogs,
        currency,
        ValueAuthority.OBSERVED if cogs is not None else ValueAuthority.MISSING,
        "Shopify InventoryItem.unitCost",
    )
    required = (cogs_component, payment, shipping, fulfillment, action)
    complete = all(component.amount is not None for component in required)
    used_assumptions = any(
        component.authority is ValueAuthority.MERCHANT_ASSUMPTION for component in required
    )
    contribution = None
    if complete:
        cost_total = 0.0
        for component in required:
            assert component.amount is not None
            cost_total += component.amount
        contribution = order.net_revenue - order.refunds - cost_total
    authority = (
        EconomicAuthority.ESTIMATED_CONTRIBUTION_PROFIT
        if complete and used_assumptions
        else EconomicAuthority.OBSERVED_CONTRIBUTION_PROFIT
        if complete
        else EconomicAuthority.NET_REVENUE_ONLY
        if order.net_revenue >= 0
        else EconomicAuthority.DATA_NOT_READY
    )
    contribution_component = MoneyComponent(
        contribution,
        currency,
        (ValueAuthority.DERIVED if contribution is not None else ValueAuthority.MISSING),
        "net revenue less explicitly sourced cost components",
    )
    return OrderEconomics(
        order_source_id=order.source_id,
        net_revenue=MoneyComponent(
            order.net_revenue, currency, ValueAuthority.OBSERVED, "Shopify order totals"
        ),
        cogs=cogs_component,
        refunds=MoneyComponent(order.refunds, currency, ValueAuthority.OBSERVED, "Shopify refunds"),
        payment_fees=payment,
        shipping_subsidy=shipping,
        fulfillment_cost=fulfillment,
        action_cost=action,
        contribution_profit=contribution_component,
        authority=authority,
        completeness={
            "revenue": True,
            "discounts": True,
            "cogs": cogs_component.amount is not None,
            "refunds": True,
            "payment_fees": payment.amount is not None,
            "shipping_subsidy": shipping.amount is not None,
            "fulfillment": fulfillment.amount is not None,
            "action_cost": action.amount is not None,
        },
    )


def _assumed_payment_fee(
    order: CanonicalOrder, assumptions: EconomicAssumptions | None
) -> float | None:
    if assumptions is None or assumptions.payment_fee_rate is None:
        return None
    return order.net_revenue * assumptions.payment_fee_rate + (assumptions.payment_fixed_fee or 0.0)


def _cost_component(
    observed: float | None,
    assumed: float | None,
    currency: str,
    observed_source: str,
    assumptions: EconomicAssumptions | None,
) -> MoneyComponent:
    if observed is not None:
        return MoneyComponent(observed, currency, ValueAuthority.OBSERVED, observed_source)
    if assumed is not None and assumptions is not None:
        return MoneyComponent(
            assumed,
            currency,
            ValueAuthority.MERCHANT_ASSUMPTION,
            f"economic assumptions version {assumptions.version}",
        )
    return MoneyComponent(None, currency, ValueAuthority.MISSING, "not supplied")
