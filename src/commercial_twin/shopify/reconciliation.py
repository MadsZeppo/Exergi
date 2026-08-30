"""Shopify Admin reconciliation with explicit differences and explanations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from uuid import UUID

from .contracts import CanonicalOrder, ReconciliationReport


def reconcile_shopify_totals(
    shop_id: UUID,
    orders: Iterable[CanonicalOrder],
    admin_totals: Mapping[str, float | int],
    *,
    as_of: datetime,
    currency: str,
    money_tolerance: float = 0.02,
) -> ReconciliationReport:
    eligible = tuple(
        order
        for order in orders
        if order.shop_id == shop_id
        and order.occurred_at <= as_of
        and order.observed_at <= as_of
        and order.currency == currency
    )
    imported: dict[str, float | int] = {
        "order_count": len(eligible),
        "gross_sales": sum(order.gross_sales for order in eligible),
        "discounts": sum(order.discounts for order in eligible),
        "refunds": sum(order.refunds for order in eligible),
        "net_sales": sum(order.net_revenue - order.refunds for order in eligible),
        "customer_count": len({order.customer_key for order in eligible if order.customer_key}),
    }
    differences = {
        key: float(imported.get(key, 0)) - float(value) for key, value in admin_totals.items()
    }
    explanations: list[str] = []
    if any(order.cancelled for order in eligible):
        explanations.append("Imported totals include canonical cancellation flags for inspection.")
    if any(order.customer_key is None for order in eligible):
        explanations.append("Guest checkouts are included in orders but not identified customers.")
    if any(order.currency != currency for order in orders):
        explanations.append(
            "Orders in other currencies are excluded; no FX conversion is invented."
        )
    if not explanations:
        explanations.append("No known coverage difference was detected in the selected window.")
    passed = all(
        abs(difference) <= (0.0 if key.endswith("count") else money_tolerance)
        for key, difference in differences.items()
    )
    return ReconciliationReport(
        shop_id,
        as_of,
        currency,
        dict(admin_totals),
        imported,
        differences,
        tuple(explanations),
        passed,
    )
