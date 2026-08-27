"""CSV/Parquet ingestion and fail-closed validation for win-back pilot tables."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import BaseModel, ValidationError

from .contracts import (
    CampaignEligibilityRecord,
    ChannelCostRecord,
    CustomerRecord,
    DeliveryRecord,
    DiscountRecord,
    OrderLineRecord,
    OrderRecord,
    ProductRecord,
    ReturnRecord,
)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    table: str
    detail: str


@dataclass(frozen=True)
class PilotDataValidation:
    ready: bool
    issues: tuple[ValidationIssue, ...]
    row_counts: dict[str, int]


def load_records[RecordT: BaseModel](
    path: Path, model: type[RecordT]
) -> tuple[RecordT, ...]:
    if path.suffix.lower() == ".parquet":
        rows = pl.read_parquet(path).to_dicts()
    elif path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source))
    else:
        raise ValueError("pilot adapter supports CSV or Parquet only")
    try:
        normalized = [
            {key: None if value == "" else value for key, value in row.items()} for row in rows
        ]
        return tuple(model.model_validate(row) for row in normalized)
    except ValidationError as exc:
        raise ValueError(f"{path.name} does not satisfy {model.__name__}: {exc}") from exc


def validate_tables(
    *,
    customers: tuple[CustomerRecord, ...],
    orders: tuple[OrderRecord, ...],
    order_lines: tuple[OrderLineRecord, ...],
    products: tuple[ProductRecord, ...],
    discounts: tuple[DiscountRecord, ...],
    returns: tuple[ReturnRecord, ...],
    eligibility: tuple[CampaignEligibilityRecord, ...],
    delivery: tuple[DeliveryRecord, ...] = (),
    channel_costs: tuple[ChannelCostRecord, ...] = (),
) -> PilotDataValidation:
    issues: list[ValidationIssue] = []
    tables: dict[str, tuple[Any, ...]] = {
        "customers": customers,
        "orders": orders,
        "order_lines": order_lines,
        "products": products,
        "discounts": discounts,
        "returns": returns,
        "eligibility": eligibility,
        "delivery": delivery,
        "channel_costs": channel_costs,
    }

    def unique(table: str, values: list[str]) -> None:
        if len(values) != len(set(values)):
            issues.append(ValidationIssue("DUPLICATE_ID", table, "IDs must be unique"))

    unique("customers", [row.customer_id for row in customers])
    unique("orders", [row.order_id for row in orders])
    unique("order_lines", [row.order_line_id for row in order_lines])
    unique("products", [row.product_id for row in products])
    unique("discounts", [row.discount_id for row in discounts])
    unique("returns", [row.return_id for row in returns])
    unique("eligibility", [row.customer_id for row in eligibility])
    customer_ids = {row.customer_id for row in customers}
    order_ids = {row.order_id for row in orders}
    line_ids = {row.order_line_id for row in order_lines}
    product_ids = {row.product_id for row in products}
    for order_row in orders:
        if order_row.customer_id not in customer_ids:
            issues.append(ValidationIssue("ORPHAN_ORDER", "orders", order_row.order_id))
        if order_row.payment_transaction_cost is None:
            issues.append(
                ValidationIssue("MISSING_PAYMENT_COST", "orders", order_row.order_id)
            )
    for line_row in order_lines:
        if line_row.order_id not in order_ids or line_row.product_id not in product_ids:
            issues.append(
                ValidationIssue("ORPHAN_ORDER_LINE", "order_lines", line_row.order_line_id)
            )
        if line_row.cogs is None:
            issues.append(
                ValidationIssue("MISSING_COGS", "order_lines", line_row.order_line_id)
            )
    for discount_row in discounts:
        if discount_row.order_id not in order_ids:
            issues.append(
                ValidationIssue("ORPHAN_DISCOUNT", "discounts", discount_row.discount_id)
            )
        if discount_row.merchant_funded_amount is None:
            issues.append(
                ValidationIssue(
                    "MISSING_DISCOUNT_FUNDING", "discounts", discount_row.discount_id
                )
            )
    for return_row in returns:
        if return_row.order_id not in order_ids or (
            return_row.order_line_id is not None and return_row.order_line_id not in line_ids
        ):
            issues.append(ValidationIssue("ORPHAN_RETURN", "returns", return_row.return_id))
        parent_order = next(
            (item for item in orders if item.order_id == return_row.order_id), None
        )
        if parent_order is not None and return_row.returned_at < parent_order.ordered_at:
            issues.append(
                ValidationIssue("RETURN_BEFORE_ORDER", "returns", return_row.return_id)
            )
    for eligibility_row in eligibility:
        if eligibility_row.customer_id not in customer_ids:
            issues.append(
                ValidationIssue(
                    "ORPHAN_ELIGIBILITY", "eligibility", eligibility_row.customer_id
                )
            )
        if (
            eligibility_row.last_purchase_at is not None
            and eligibility_row.last_purchase_at > eligibility_row.snapshot_at
        ):
            issues.append(
                ValidationIssue("FUTURE_LEAKAGE", "eligibility", eligibility_row.customer_id)
            )
    currencies = {
        *[row.currency for row in customers],
        *[row.currency for row in orders],
        *[row.currency for row in products],
        *[row.currency for row in discounts],
        *[row.currency for row in returns],
        *[row.currency for row in channel_costs],
    }
    if len(currencies) > 1:
        issues.append(
            ValidationIssue("CURRENCY_MISMATCH", "all", ",".join(sorted(currencies)))
        )
    for cost_row in channel_costs:
        if cost_row.channel_cost is None or cost_row.shipping_subsidy is None:
            issues.append(
                ValidationIssue("MISSING_ACTION_COST", "channel_costs", cost_row.customer_id)
            )
    cost_customers = {row.customer_id for row in channel_costs}
    eligibility_customers = {row.customer_id for row in eligibility}
    missing_cost_customers = eligibility_customers - cost_customers
    if missing_cost_customers:
        issues.append(
            ValidationIssue(
                "MISSING_ACTION_COST_COVERAGE",
                "channel_costs",
                f"{len(missing_cost_customers)} eligibility customers lack a cost row",
            )
        )
    return PilotDataValidation(
        not issues,
        tuple(issues),
        {name: len(rows) for name, rows in tables.items()},
    )
