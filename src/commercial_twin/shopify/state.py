"""Leak-safe point-in-time customer and company state builders."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from statistics import median
from uuid import UUID

from .contracts import (
    CanonicalOrder,
    CompanyState,
    CustomerState,
    EconomicAuthority,
    Lifecycle,
    OrderEconomics,
)


def build_customer_states(
    orders: Iterable[CanonicalOrder],
    economics: Mapping[str, OrderEconomics],
    *,
    as_of: datetime,
) -> tuple[CustomerState, ...]:
    eligible = _eligible_orders(orders, as_of)
    by_customer: dict[str, list[CanonicalOrder]] = defaultdict(list)
    for order in eligible:
        if order.customer_key and not order.cancelled:
            by_customer[order.customer_key].append(order)
    states: list[CustomerState] = []
    for customer_key, customer_orders in by_customer.items():
        customer_orders.sort(key=lambda order: order.occurred_at)
        gaps = [
            (right.occurred_at - left.occurred_at).total_seconds() / 86400
            for left, right in zip(customer_orders, customer_orders[1:], strict=False)
        ]
        normal_interval = float(median(gaps)) if gaps else None
        recency = max(0, (as_of.date() - customer_orders[-1].occurred_at.date()).days)
        lifecycle = _lifecycle(customer_orders, recency, normal_interval)
        net_revenue = sum(order.net_revenue - order.refunds for order in customer_orders)
        contribution_values = [
            economics[order.source_id].contribution_profit.amount
            for order in customer_orders
            if order.source_id in economics
        ]
        contribution = _complete_sum(contribution_values)
        product_counts: Counter[str] = Counter()
        for order in customer_orders:
            for line in order.lines:
                if line.product_source_id:
                    product_counts[line.product_source_id] += line.quantity
        gross = sum(order.gross_sales for order in customer_orders)
        states.append(
            CustomerState(
                customer_key=customer_key,
                as_of=as_of,
                recency_days=recency,
                purchase_frequency=len(customer_orders),
                average_order_value=net_revenue / len(customer_orders),
                net_revenue=net_revenue,
                contribution_profit=contribution,
                normal_interpurchase_days=normal_interval,
                lifecycle=lifecycle,
                discount_share=(
                    sum(order.discounts for order in customer_orders) / gross if gross else 0.0
                ),
                return_rate=(
                    sum(order.refunds for order in customer_orders) / net_revenue
                    if net_revenue
                    else 0.0
                ),
                tenure_days=max(0, (as_of.date() - customer_orders[0].occurred_at.date()).days),
                category_affinity=tuple(key for key, _ in product_counts.most_common(3)),
                support="HIGH" if len(customer_orders) >= 3 else "LIMITED",
                uncertainty={
                    "history_orders": len(customer_orders),
                    "cadence_estimated": normal_interval is not None,
                    "contribution_profit_complete": contribution is not None,
                },
            )
        )
    return tuple(sorted(states, key=lambda state: state.customer_key))


def build_company_state(
    shop_id: UUID,
    orders: Iterable[CanonicalOrder],
    economics: Mapping[str, OrderEconomics],
    customer_states: Iterable[CustomerState],
    *,
    as_of: datetime,
) -> CompanyState:
    eligible = tuple(order for order in _eligible_orders(orders, as_of) if not order.cancelled)
    states = tuple(customer_states)
    currencies = {order.currency for order in eligible}
    if len(currencies) > 1:
        raise ValueError("company state cannot aggregate multiple currencies without FX authority")
    currency = next(iter(currencies), "---")
    cp_values = [
        economics[order.source_id].contribution_profit.amount
        for order in eligible
        if order.source_id in economics
    ]
    contribution = _complete_sum(cp_values) if len(cp_values) == len(eligible) else None
    authorities = {
        economics[order.source_id].authority for order in eligible if order.source_id in economics
    }
    economic_authority = (
        EconomicAuthority.OBSERVED_CONTRIBUTION_PROFIT
        if authorities == {EconomicAuthority.OBSERVED_CONTRIBUTION_PROFIT}
        else EconomicAuthority.ESTIMATED_CONTRIBUTION_PROFIT
        if contribution is not None
        else EconomicAuthority.NET_REVENUE_ONLY
        if eligible
        else EconomicAuthority.DATA_NOT_READY
    )
    orders_per_customer: Counter[str] = Counter(
        order.customer_key for order in eligible if order.customer_key
    )
    repeat_revenue = sum(
        order.net_revenue - order.refunds
        for order in eligible
        if order.customer_key and orders_per_customer[order.customer_key] > 1
    )
    completeness_keys = (
        "revenue",
        "discounts",
        "cogs",
        "refunds",
        "payment_fees",
        "shipping_subsidy",
        "fulfillment",
        "action_cost",
    )
    completeness = {
        key: (
            sum(
                1
                for order in eligible
                if order.source_id in economics and economics[order.source_id].completeness[key]
            )
            / len(eligible)
            if eligible
            else 0.0
        )
        for key in completeness_keys
    }
    net_revenue = sum(order.net_revenue - order.refunds for order in eligible)
    gross_sales = sum(order.gross_sales for order in eligible)
    lifecycle_counts = Counter(state.lifecycle.value for state in states)
    return CompanyState(
        shop_id=shop_id,
        as_of=as_of,
        currency=currency,
        order_count=len(eligible),
        customer_count=len({order.customer_key for order in eligible if order.customer_key}),
        net_revenue=net_revenue,
        contribution_profit=contribution,
        repeat_revenue=repeat_revenue,
        refund_rate=(
            sum(order.refunds for order in eligible) / net_revenue if net_revenue else 0.0
        ),
        discount_rate=(
            sum(order.discounts for order in eligible) / gross_sales if gross_sales else 0.0
        ),
        lifecycle_distribution=dict(sorted(lifecycle_counts.items())),
        economic_authority=economic_authority,
        completeness=completeness,
    )


def _eligible_orders(
    orders: Iterable[CanonicalOrder], as_of: datetime
) -> tuple[CanonicalOrder, ...]:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    return tuple(
        order for order in orders if order.occurred_at <= as_of and order.observed_at <= as_of
    )


def _lifecycle(
    orders: list[CanonicalOrder], recency_days: int, normal_interval: float | None
) -> Lifecycle:
    if len(orders) == 1 and recency_days <= 30:
        return Lifecycle.NEW
    if normal_interval is None:
        return Lifecycle.ACTIVE if recency_days <= 45 else Lifecycle.DORMANT
    if len(orders) >= 2:
        previous_gap = (orders[-1].occurred_at - orders[-2].occurred_at).days
        if previous_gap > max(60.0, 2.5 * normal_interval) and recency_days <= normal_interval:
            return Lifecycle.REACTIVATED
    if recency_days <= max(30.0, 1.25 * normal_interval):
        return Lifecycle.ACTIVE
    if recency_days <= max(60.0, 2.5 * normal_interval):
        return Lifecycle.COOLING
    return Lifecycle.DORMANT


def _complete_sum(values: list[float | None]) -> float | None:
    total = 0.0
    if not values:
        return None
    for value in values:
        if value is None:
            return None
        total += value
    return total
