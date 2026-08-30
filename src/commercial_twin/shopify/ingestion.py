"""Append-only raw ingestion and deterministic Shopify canonical mapping."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from .contracts import (
    CanonicalOrder,
    CanonicalOrderLine,
    MoneyComponent,
    ValueAuthority,
)
from .graphql import (
    CUSTOMERS_BULK_QUERY,
    ORDERS_BULK_QUERY,
    PRODUCTS_BULK_QUERY,
    ShopifyGraphQLClient,
)
from .repository import ShopifyRepository
from .security import pseudonymize_customer


class CanonicalSink(Protocol):
    def upsert_order(self, order: CanonicalOrder) -> None: ...


class MemoryCanonicalSink:
    def __init__(self) -> None:
        self.orders: dict[tuple[UUID, str], CanonicalOrder] = {}

    def upsert_order(self, order: CanonicalOrder) -> None:
        self.orders[(order.shop_id, order.source_id)] = order


class SqlCanonicalSink:
    """Transactional PostgreSQL materializer for the analytical order grain."""

    def __init__(self, engine: Engine, merchant_id: UUID, api_version: str) -> None:
        self.engine = engine
        self.merchant_id = merchant_id
        self.api_version = api_version

    def upsert_order(self, order: CanonicalOrder) -> None:
        order_id = _canonical_uuid(order.shop_id, f"order:{order.source_id}")
        customer_id = (
            _canonical_uuid(order.shop_id, f"customer:{order.customer_key}")
            if order.customer_key
            else None
        )
        with self.engine.begin() as connection:
            if customer_id and order.customer_key:
                connection.execute(
                    text("""
                    INSERT INTO customers
                        (id, merchant_id, shop_id, pseudonymous_customer_key,
                         first_seen_at, last_seen_at, created_at, updated_at)
                    VALUES (:id, :merchant_id, :shop_id, :customer_key,
                            :seen, :seen, now(), now())
                    ON CONFLICT (merchant_id, pseudonymous_customer_key) DO UPDATE SET
                        first_seen_at = LEAST(customers.first_seen_at, EXCLUDED.first_seen_at),
                        last_seen_at = GREATEST(customers.last_seen_at, EXCLUDED.last_seen_at),
                        updated_at = now(), deletion_status = 'ACTIVE'
                    """),
                    {
                        "id": customer_id,
                        "merchant_id": self.merchant_id,
                        "shop_id": order.shop_id,
                        "customer_key": order.customer_key,
                        "seen": order.occurred_at,
                    },
                )
            connection.execute(
                text("""
                INSERT INTO orders
                    (id, merchant_id, shop_id, customer_id, external_order_id, ordered_at,
                     occurred_at, observed_at, currency, gross_item_sales, line_discounts,
                     shipping_revenue, tax, net_sales, financial_status, fulfillment_status,
                     source, source_version, deletion_status)
                VALUES (:id, :merchant_id, :shop_id, :customer_id, :source_id, :occurred_at,
                        :occurred_at, :observed_at, :currency, :gross_sales, :discounts,
                        :shipping, :tax, :net_revenue, :financial, NULL,
                        'SHOPIFY', :source_version, 'ACTIVE')
                ON CONFLICT (merchant_id, external_order_id) DO UPDATE SET
                    customer_id = EXCLUDED.customer_id, observed_at = EXCLUDED.observed_at,
                    gross_item_sales = EXCLUDED.gross_item_sales,
                    line_discounts = EXCLUDED.line_discounts,
                    shipping_revenue = EXCLUDED.shipping_revenue, tax = EXCLUDED.tax,
                    net_sales = EXCLUDED.net_sales, financial_status = EXCLUDED.financial_status,
                    source_version = EXCLUDED.source_version, deletion_status = 'ACTIVE'
                """),
                {
                    "id": order_id,
                    "merchant_id": self.merchant_id,
                    "shop_id": order.shop_id,
                    "customer_id": customer_id,
                    "source_id": order.source_id,
                    "occurred_at": order.occurred_at,
                    "observed_at": order.observed_at,
                    "currency": order.currency,
                    "gross_sales": order.gross_sales,
                    "discounts": order.discounts,
                    "shipping": order.shipping_revenue,
                    "tax": order.tax,
                    "net_revenue": order.net_revenue,
                    "financial": "CANCELLED" if order.cancelled else "OBSERVED",
                    "source_version": self.api_version,
                },
            )
            for line in order.lines:
                product_id = self._upsert_product(connection, order, line)
                variant_id = self._upsert_variant(connection, order, line, product_id)
                connection.execute(
                    text("""
                    INSERT INTO order_lines
                        (id, merchant_id, shop_id, order_id, product_id, variant_id, quantity,
                         gross_unit_price, line_discount, net_line_sales, cogs_per_unit_nullable,
                         observed_at, source_version, deletion_status)
                    VALUES (:id, :merchant_id, :shop_id, :order_id, :product_id, :variant_id,
                            :quantity, :gross_unit_price, :line_discount, :net_line_sales,
                            :cogs_per_unit, :observed_at, :source_version, 'ACTIVE')
                    ON CONFLICT (id) DO UPDATE SET
                        quantity = EXCLUDED.quantity, gross_unit_price = EXCLUDED.gross_unit_price,
                        line_discount = EXCLUDED.line_discount,
                        net_line_sales = EXCLUDED.net_line_sales,
                        cogs_per_unit_nullable = EXCLUDED.cogs_per_unit_nullable,
                        observed_at = EXCLUDED.observed_at, deletion_status = 'ACTIVE'
                    """),
                    {
                        "id": _canonical_uuid(order.shop_id, f"line:{line.source_id}"),
                        "merchant_id": self.merchant_id,
                        "shop_id": order.shop_id,
                        "order_id": order_id,
                        "product_id": product_id,
                        "variant_id": variant_id,
                        "quantity": line.quantity,
                        "gross_unit_price": line.gross_sales / line.quantity,
                        "line_discount": line.discounts,
                        "net_line_sales": line.net_revenue,
                        "cogs_per_unit": (
                            line.cogs.amount / line.quantity
                            if line.cogs.amount is not None
                            else None
                        ),
                        "observed_at": order.observed_at,
                        "source_version": self.api_version,
                    },
                )
            if order.refunds > 0:
                refund_source = f"{order.source_id}:aggregate-refund"
                connection.execute(
                    text("""
                    INSERT INTO refunds
                        (id, merchant_id, shop_id, order_id, external_refund_id,
                         refunded_at, refund_amount, observed_at, source_version, deletion_status)
                    VALUES (:id, :merchant_id, :shop_id, :order_id, :source_id,
                            :refunded_at, :amount, :observed_at, :source_version, 'ACTIVE')
                    ON CONFLICT (merchant_id, external_refund_id) DO UPDATE SET
                        refund_amount = EXCLUDED.refund_amount,
                        observed_at = EXCLUDED.observed_at,
                        source_version = EXCLUDED.source_version, deletion_status = 'ACTIVE'
                    """),
                    {
                        "id": _canonical_uuid(order.shop_id, f"refund:{refund_source}"),
                        "merchant_id": self.merchant_id,
                        "shop_id": order.shop_id,
                        "order_id": order_id,
                        "source_id": refund_source,
                        "refunded_at": order.occurred_at,
                        "amount": order.refunds,
                        "observed_at": order.observed_at,
                        "source_version": self.api_version,
                    },
                )

    def _upsert_product(
        self, connection: Any, order: CanonicalOrder, line: CanonicalOrderLine
    ) -> UUID | None:
        if not line.product_source_id:
            return None
        product_id = _canonical_uuid(order.shop_id, f"product:{line.product_source_id}")
        connection.execute(
            text("""
            INSERT INTO products
                (id, merchant_id, shop_id, external_product_id, observed_at, source_version)
            VALUES (:id, :merchant_id, :shop_id, :source_id, :observed_at, :source_version)
            ON CONFLICT (merchant_id, external_product_id) DO UPDATE SET
                observed_at = EXCLUDED.observed_at, source_version = EXCLUDED.source_version,
                deletion_status = 'ACTIVE'
            """),
            {
                "id": product_id,
                "merchant_id": self.merchant_id,
                "shop_id": order.shop_id,
                "source_id": line.product_source_id,
                "observed_at": order.observed_at,
                "source_version": self.api_version,
            },
        )
        return product_id

    def _upsert_variant(
        self,
        connection: Any,
        order: CanonicalOrder,
        line: CanonicalOrderLine,
        product_id: UUID | None,
    ) -> UUID | None:
        if not line.variant_source_id or product_id is None:
            return None
        variant_id = _canonical_uuid(order.shop_id, f"variant:{line.variant_source_id}")
        connection.execute(
            text("""
            INSERT INTO variants
                (id, merchant_id, shop_id, product_id, external_variant_id,
                 observed_at, source_version)
            VALUES (:id, :merchant_id, :shop_id, :product_id, :source_id,
                    :observed_at, :source_version)
            ON CONFLICT (merchant_id, external_variant_id) DO UPDATE SET
                product_id = EXCLUDED.product_id, observed_at = EXCLUDED.observed_at,
                source_version = EXCLUDED.source_version, deletion_status = 'ACTIVE'
            """),
            {
                "id": variant_id,
                "merchant_id": self.merchant_id,
                "shop_id": order.shop_id,
                "product_id": product_id,
                "source_id": line.variant_source_id,
                "observed_at": order.observed_at,
                "source_version": self.api_version,
            },
        )
        return variant_id


@dataclass(frozen=True)
class SyncResult:
    sync_run_id: UUID
    status: str
    source_rows: int
    accepted_raw_rows: int
    duplicate_raw_rows: int
    canonical_orders: int
    checkpoints: dict[str, str]
    warnings: tuple[str, ...]


class ShopifyInitialSync:
    """One resumable initial sync. Caller persists/requeues operation checkpoints."""

    QUERIES = {
        "customers": CUSTOMERS_BULK_QUERY,
        "products": PRODUCTS_BULK_QUERY,
        "orders": ORDERS_BULK_QUERY,
    }

    def __init__(
        self,
        client: ShopifyGraphQLClient,
        repository: ShopifyRepository,
        sink: CanonicalSink,
        customer_pseudonym_key: str,
        *,
        api_version: str,
    ) -> None:
        self.client = client
        self.repository = repository
        self.sink = sink
        self.customer_pseudonym_key = customer_pseudonym_key
        self.api_version = api_version

    def run(
        self,
        *,
        merchant_id: UUID,
        shop_id: UUID,
        resume_checkpoints: Mapping[str, str] | None = None,
        observed_at: datetime | None = None,
        sync_run_id: UUID | None = None,
        checkpoint_callback: Callable[[dict[str, str]], None] | None = None,
    ) -> SyncResult:
        now = observed_at or datetime.now(UTC)
        sync_run_id = sync_run_id or uuid4()
        checkpoints = dict(resume_checkpoints or {})
        source_rows = accepted = duplicates = canonical_orders = 0
        warnings: list[str] = []
        order_rows: list[dict[str, Any]] = []
        for object_type, query in self.QUERIES.items():
            operation_id = checkpoints.get(object_type)
            operation = (
                self.client.bulk_status(operation_id)
                if operation_id
                else self.client.start_bulk_query(query)
            )
            checkpoints[object_type] = operation.id
            if checkpoint_callback is not None:
                checkpoint_callback(dict(checkpoints))
            if operation.status != "COMPLETED":
                operation = self.client.wait_for_bulk(operation.id)
            if not operation.url:
                raise RuntimeError(f"completed {object_type} bulk operation has no result URL")
            for raw in self.client.iter_jsonl(operation.url):
                source_rows += 1
                source_id = str(raw.get("id") or _stable_fallback_id(raw))
                payload_hash = _payload_hash(raw)
                inserted = self.repository.append_raw_object(
                    merchant_id=merchant_id,
                    shop_id=shop_id,
                    sync_run_id=sync_run_id,
                    object_type=object_type,
                    source_id=source_id,
                    source_updated_at=_optional_datetime(raw.get("updatedAt")),
                    source_version=self.api_version,
                    payload=raw,
                    payload_hash=payload_hash,
                    observed_at=now,
                )
                if inserted:
                    accepted += 1
                else:
                    duplicates += 1
                if object_type == "orders":
                    order_rows.append(raw)
        for order in map_order_jsonl(
            order_rows,
            shop_id=shop_id,
            observed_at=now,
            customer_pseudonym_key=self.customer_pseudonym_key,
        ):
            self.sink.upsert_order(order)
            canonical_orders += 1
        if canonical_orders == 0:
            warnings.append("No orders were available in the granted Shopify history window.")
        return SyncResult(
            sync_run_id,
            "COMPLETED",
            source_rows,
            accepted,
            duplicates,
            canonical_orders,
            checkpoints,
            tuple(warnings),
        )


def map_order_jsonl(
    rows: Iterable[Mapping[str, Any]],
    *,
    shop_id: UUID,
    observed_at: datetime,
    customer_pseudonym_key: str,
) -> tuple[CanonicalOrder, ...]:
    parents: dict[str, dict[str, Any]] = {}
    children: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        row_id = str(row.get("id", ""))
        parent_id = row.get("__parentId")
        if parent_id:
            children.setdefault(str(parent_id), []).append(row)
        elif row_id:
            parents[row_id] = dict(row)
    output: list[CanonicalOrder] = []
    for order_id, raw in parents.items():
        if "currencyCode" not in raw or "createdAt" not in raw:
            continue
        currency = str(raw["currencyCode"])
        gross = _money(raw.get("currentSubtotalPriceSet"), currency)
        discounts = _money(raw.get("currentTotalDiscountsSet"), currency)
        shipping = _money(raw.get("currentShippingPriceSet"), currency)
        tax = _money(raw.get("currentTotalTaxSet"), currency)
        customer = raw.get("customer") or {}
        customer_id = customer.get("id") if isinstance(customer, Mapping) else None
        lines = tuple(
            _map_line(row, order_id, currency)
            for row in children.get(order_id, [])
            if "quantity" in row and "originalUnitPriceSet" in row
        )
        refunds = sum(
            _money(row.get("totalRefundedSet"), currency)
            for row in children.get(order_id, [])
            if "totalRefundedSet" in row
        )
        if lines:
            gross = sum(line.gross_sales for line in lines)
            discounts = sum(line.discounts for line in lines)
        output.append(
            CanonicalOrder(
                shop_id=shop_id,
                source_id=order_id,
                customer_key=(
                    pseudonymize_customer(shop_id, str(customer_id), customer_pseudonym_key)
                    if customer_id
                    else None
                ),
                occurred_at=_required_datetime(raw["createdAt"]),
                observed_at=observed_at,
                currency=currency,
                gross_sales=gross,
                discounts=discounts,
                shipping_revenue=shipping,
                tax=tax,
                refunds=refunds,
                # Refunds remain a separate observed component and are subtracted exactly once
                # by the economics layer.
                net_revenue=max(0.0, gross - discounts + shipping),
                cancelled=raw.get("cancelledAt") is not None,
                lines=lines,
            )
        )
    return tuple(sorted(output, key=lambda value: (value.occurred_at, value.source_id)))


def _map_line(raw: Mapping[str, Any], order_id: str, currency: str) -> CanonicalOrderLine:
    quantity = int(raw["quantity"])
    original = _money(raw.get("originalUnitPriceSet"), currency)
    discounted = _money(raw.get("discountedUnitPriceAfterAllDiscountsSet"), currency)
    variant = raw.get("variant") or {}
    inventory = variant.get("inventoryItem") or {} if isinstance(variant, Mapping) else {}
    unit_cost = inventory.get("unitCost") if isinstance(inventory, Mapping) else None
    cost_amount = _plain_money(unit_cost, currency) if unit_cost else None
    product = raw.get("product") or {}
    return CanonicalOrderLine(
        source_id=str(raw["id"]),
        order_source_id=order_id,
        product_source_id=(str(product.get("id")) if isinstance(product, Mapping) else None),
        variant_source_id=(str(variant.get("id")) if isinstance(variant, Mapping) else None),
        quantity=quantity,
        gross_sales=original * quantity,
        discounts=max(0.0, (original - discounted) * quantity),
        net_revenue=discounted * quantity,
        cogs=MoneyComponent(
            amount=cost_amount * quantity if cost_amount is not None else None,
            currency=currency,
            authority=(
                ValueAuthority.OBSERVED if cost_amount is not None else ValueAuthority.MISSING
            ),
            source="Shopify InventoryItem.unitCost",
        ),
    )


def _money(value: Any, currency: str) -> float:
    if not isinstance(value, Mapping):
        return 0.0
    shop_money = value.get("shopMoney")
    return _plain_money(shop_money, currency) if isinstance(shop_money, Mapping) else 0.0


def _plain_money(value: Mapping[str, Any], currency: str) -> float:
    value_currency = str(value.get("currencyCode") or currency)
    if value_currency != currency:
        raise ValueError(f"mixed currency inside order: {value_currency} != {currency}")
    return float(value.get("amount") or 0.0)


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _stable_fallback_id(payload: Mapping[str, Any]) -> str:
    return f"sha256:{_payload_hash(payload)}"


def _required_datetime(value: Any) -> datetime:
    answer = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if answer.tzinfo is None:
        raise ValueError("Shopify timestamp must be timezone-aware")
    return answer


def _optional_datetime(value: Any) -> datetime | None:
    return _required_datetime(value) if value else None


def _canonical_uuid(shop_id: UUID, name: str) -> UUID:
    from uuid import uuid5

    return uuid5(shop_id, name)
