"""Verified, replay-safe Shopify webhook and privacy processing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import Engine, text

from commercial_twin.database_security import set_tenant_context, shop_route_transaction

from .repository import ShopifyRepository
from .security import canonicalize_shop_domain, pseudonymize_customer, verify_webhook_hmac

INCREMENTAL_TOPICS = frozenset(
    {
        "orders/create",
        "orders/updated",
        "orders/cancelled",
        "refunds/create",
        "products/create",
        "products/update",
        "products/delete",
    }
)

SUPPORTED_TOPICS = INCREMENTAL_TOPICS | frozenset(
    {
        "app/uninstalled",
        "customers/data_request",
        "customers/redact",
        "shop/redact",
    }
)


class PrivacyProcessor(Protocol):
    def data_request(self, shop: str, payload: Mapping[str, Any]) -> None: ...

    def redact_customer(self, shop: str, payload: Mapping[str, Any]) -> None: ...

    def redact_shop(self, shop: str, payload: Mapping[str, Any]) -> None: ...

    def uninstall(self, shop: str, payload: Mapping[str, Any]) -> None: ...

    def incremental(self, shop: str, topic: str, payload: Mapping[str, Any]) -> None: ...


@dataclass(frozen=True)
class WebhookResult:
    accepted: bool
    duplicate: bool
    topic: str


class ShopifyWebhookService:
    def __init__(
        self,
        client_secret: str,
        repository: ShopifyRepository,
        processor: PrivacyProcessor,
    ) -> None:
        self.client_secret = client_secret
        self.repository = repository
        self.processor = processor

    def handle(self, body: bytes, headers: Mapping[str, str]) -> WebhookResult:
        normalized = {key.lower(): value for key, value in headers.items()}
        signature = normalized.get("x-shopify-hmac-sha256", "")
        if not verify_webhook_hmac(body, signature, self.client_secret):
            raise ValueError("invalid Shopify webhook HMAC")
        shop = canonicalize_shop_domain(normalized.get("x-shopify-shop-domain", ""))
        topic = normalized.get("x-shopify-topic", "")
        webhook_id = normalized.get("x-shopify-webhook-id", "")
        if topic not in SUPPORTED_TOPICS or not webhook_id:
            raise ValueError("unsupported or malformed Shopify webhook")
        payload_hash = hashlib.sha256(body).hexdigest()
        inserted = self.repository.register_webhook(
            shop, webhook_id, topic, payload_hash, datetime.now(UTC)
        )
        if not inserted:
            return WebhookResult(True, True, topic)
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("Shopify webhook payload must be an object")
        if topic == "customers/data_request":
            self.processor.data_request(shop, payload)
        elif topic == "customers/redact":
            self.processor.redact_customer(shop, payload)
        elif topic == "shop/redact":
            self.processor.redact_shop(shop, payload)
        elif topic == "app/uninstalled":
            self.processor.uninstall(shop, payload)
        else:
            self.processor.incremental(shop, topic, payload)
        return WebhookResult(True, False, topic)


class RecordingPrivacyProcessor:
    """Test/worker queue adapter; production supplies durable deletion job functions."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Mapping[str, Any]]] = []

    def data_request(self, shop: str, payload: Mapping[str, Any]) -> None:
        self.calls.append(("data_request", shop, payload))

    def redact_customer(self, shop: str, payload: Mapping[str, Any]) -> None:
        self.calls.append(("redact_customer", shop, payload))

    def redact_shop(self, shop: str, payload: Mapping[str, Any]) -> None:
        self.calls.append(("redact_shop", shop, payload))

    def uninstall(self, shop: str, payload: Mapping[str, Any]) -> None:
        self.calls.append(("uninstall", shop, payload))

    def incremental(self, shop: str, topic: str, payload: Mapping[str, Any]) -> None:
        self.calls.append((topic, shop, payload))


class SqlPrivacyProcessor:
    """Durable privacy/uninstall processor with no dependency on analytical identifiers."""

    def __init__(self, engine: Engine, customer_pseudonym_key: str) -> None:
        if len(customer_pseudonym_key.encode()) < 32:
            raise ValueError("customer pseudonym key must contain at least 32 bytes")
        self.engine = engine
        self.customer_pseudonym_key = customer_pseudonym_key

    def data_request(self, shop: str, payload: Mapping[str, Any]) -> None:
        customer = payload.get("customer") or {}
        request = payload.get("data_request") or {}
        source_id = str(customer.get("id", "")) if isinstance(customer, Mapping) else ""
        request_id = str(request.get("id", "")) if isinstance(request, Mapping) else ""
        order_ids = [str(value) for value in payload.get("orders_requested", [])]
        self._enqueue(
            shop,
            "SHOPIFY_CUSTOMER_DATA_EXPORT",
            {"customer_id": source_id, "order_ids": order_ids, "request_id": request_id},
        )

    def redact_customer(self, shop: str, payload: Mapping[str, Any]) -> None:
        customer = payload.get("customer") or {}
        source_id = str(customer.get("id", "")) if isinstance(customer, Mapping) else ""
        source_ids = _source_candidates(source_id, "Customer")
        order_ids = _expanded_candidates(payload.get("orders_to_redact", []), "Order")
        with shop_route_transaction(self.engine, shop) as connection:
            route = self._route(connection, shop)
            pseudonyms = [
                pseudonymize_customer(
                    UUID(str(route["shop_id"])), candidate, self.customer_pseudonym_key
                )
                for candidate in source_ids
            ]
            customer_ids = list(
                connection.execute(
                    text("""
                    SELECT id FROM customers
                    WHERE merchant_id = :merchant_id AND shop_id = :shop_id
                      AND pseudonymous_customer_key = ANY(:pseudonyms)
                    """),
                    {**route, "pseudonyms": pseudonyms},
                ).scalars()
            )
            counts: dict[str, int] = {}
            counts["raw_import_objects"] = _execute_count(
                connection,
                """
                DELETE FROM raw_import_objects
                WHERE merchant_id = :merchant_id AND shop_id = :shop_id AND (
                    (object_type = 'customers' AND source_id = ANY(:source_ids))
                    OR (object_type = 'orders' AND source_id = ANY(:order_ids))
                    OR payload_json #>> '{customer,id}' = ANY(:source_ids)
                )
                """,
                {**route, "source_ids": list(source_ids), "order_ids": order_ids},
            )
            counts["raw_source_records"] = _execute_count(
                connection,
                """
                DELETE FROM raw_source_records
                WHERE merchant_id = :merchant_id AND (
                    (source_object_type IN ('customer','customers')
                     AND source_object_id = ANY(:source_ids))
                    OR (source_object_type IN ('order','orders')
                        AND source_object_id = ANY(:order_ids))
                    OR payload_jsonb #>> '{customer,id}' = ANY(:source_ids)
                )
                """,
                {**route, "source_ids": list(source_ids), "order_ids": order_ids},
            )
            for table in (
                "experiment_outcomes",
                "experiment_exposures",
                "experiment_assignments",
                "campaign_events",
                "behavior_events",
                "customer_state_snapshots",
                "customer_daily_state",
                "customer_identities",
            ):
                counts[table] = _execute_count(
                    connection,
                    f"DELETE FROM {table} WHERE merchant_id = :merchant_id "
                    "AND customer_id = ANY(:customer_ids)",
                    {**route, "customer_ids": customer_ids},
                )
            counts["orders_detached"] = _execute_count(
                connection,
                """
                UPDATE orders SET customer_id = NULL, deletion_status = 'CUSTOMER_REDACTED'
                WHERE merchant_id = :merchant_id AND shop_id = :shop_id
                  AND (customer_id = ANY(:customer_ids) OR external_order_id = ANY(:order_ids))
                """,
                {**route, "customer_ids": customer_ids, "order_ids": order_ids},
            )
            counts["customers"] = _execute_count(
                connection,
                "DELETE FROM customers WHERE merchant_id = :merchant_id "
                "AND shop_id = :shop_id AND id = ANY(:customer_ids)",
                {**route, "customer_ids": customer_ids},
            )
            self._insert_job(
                connection,
                route,
                "SHOPIFY_CUSTOMER_REDACTION_AUDIT",
                {"deleted_by_category": counts},
            )

    def redact_shop(self, shop: str, payload: Mapping[str, Any]) -> None:
        del payload
        with shop_route_transaction(self.engine, shop) as connection:
            route = self._route(connection, shop)
            # Raw protected data and credentials are removed immediately. Canonical financial
            # records are queued for ordered FK-safe erasure by the retention worker.
            self._delete_shop_raw_payloads(connection, route, shop)
            connection.execute(
                text("""
                UPDATE shop_connections SET encrypted_access_token = '',
                    encrypted_refresh_token = NULL, status = 'SHOP_REDACTION_PENDING',
                    updated_at = now()
                WHERE merchant_id = :merchant_id AND shop_id = :shop_id
                """),
                route,
            )
            self._insert_job(
                connection,
                route,
                "SHOPIFY_SHOP_HARD_DELETE",
                {},
                delay="7 days",
            )

    def uninstall(self, shop: str, payload: Mapping[str, Any]) -> None:
        del payload
        with shop_route_transaction(self.engine, shop) as connection:
            route = self._route(connection, shop)
            self._delete_shop_raw_payloads(connection, route, shop)
            connection.execute(
                text("""
                UPDATE shop_connections SET encrypted_access_token = '',
                    encrypted_refresh_token = NULL, status = 'UNINSTALLED', updated_at = now()
                WHERE merchant_id = :merchant_id AND shop_id = :shop_id
                """),
                route,
            )
            self._insert_job(
                connection,
                route,
                "SHOPIFY_RETENTION_REVIEW",
                {},
                delay="30 days",
            )

    @staticmethod
    def _delete_shop_raw_payloads(
        connection: Any, route: Mapping[str, Any], shop: str
    ) -> None:
        raw_scope = """
            SELECT id FROM raw_source_records
            WHERE merchant_id = :merchant_id AND connection_id IN (
              SELECT id FROM data_connections
              WHERE merchant_id = :merchant_id AND external_account_id = :shop
            )
        """
        for table in ("orders", "order_lines", "refunds"):
            connection.execute(
                text(
                    f"UPDATE {table} SET raw_source_record_id = NULL "
                    "WHERE merchant_id = :merchant_id AND shop_id = :shop_id"
                ),
                route,
            )
        connection.execute(
            text(
                f"UPDATE behavior_events SET raw_source_record_id = NULL "
                f"WHERE merchant_id = :merchant_id AND raw_source_record_id IN ({raw_scope})"
            ),
            {**route, "shop": shop},
        )
        connection.execute(
            text(
                "DELETE FROM raw_source_records WHERE merchant_id = :merchant_id "
                "AND connection_id IN (SELECT id FROM data_connections "
                "WHERE merchant_id = :merchant_id AND external_account_id = :shop)"
            ),
            {**route, "shop": shop},
        )
        connection.execute(
            text(
                "DELETE FROM raw_import_objects "
                "WHERE merchant_id = :merchant_id AND shop_id = :shop_id"
            ),
            route,
        )

    def incremental(self, shop: str, topic: str, payload: Mapping[str, Any]) -> None:
        source_id = str(payload.get("admin_graphql_api_id") or payload.get("id") or "")
        # The durable queue does not duplicate protected webhook payloads. The source identifier
        # is keyed only as a replay-safe correlation value; the full signed body is transient.
        self._enqueue(
            shop,
            "SHOPIFY_INCREMENTAL_INGEST",
            {"topic": topic, "source_hash": hashlib.sha256(source_id.encode()).hexdigest()},
        )

    def _enqueue(self, shop: str, kind: str, payload: Mapping[str, Any]) -> None:
        with shop_route_transaction(self.engine, shop) as connection:
            route = self._route(connection, shop)
            self._insert_job(connection, route, kind, payload)

    def _route(self, connection: Any, shop: str) -> dict[str, Any]:
        row = (
            connection.execute(
                text("""
            SELECT merchant_id, shop_id FROM shop_connections WHERE shop_domain = :shop
            """),
                {"shop": shop},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ValueError("webhook shop is not installed")
        set_tenant_context(connection, row["merchant_id"])
        return {"merchant_id": row["merchant_id"], "shop_id": row["shop_id"]}

    @staticmethod
    def _insert_job(
        connection: Any,
        route: Mapping[str, Any],
        kind: str,
        payload: Mapping[str, Any],
        *,
        delay: str = "0 seconds",
    ) -> None:
        from uuid import uuid4

        if delay not in {"0 seconds", "7 days", "30 days"}:
            raise ValueError("unsupported privacy-job delay")
        safe_payload = {"shop_id": str(route["shop_id"]), **dict(payload)}

        connection.execute(
            text("""
            INSERT INTO jobs
                (id, merchant_id, job_type, status, payload, attempts, available_at)
            VALUES (:id, :merchant_id, :kind, 'PENDING', CAST(:payload AS jsonb), 0,
                    now() + CAST(:delay AS interval))
            """),
            {
                "id": uuid4(),
                "merchant_id": route["merchant_id"],
                "kind": kind,
                "payload": json.dumps(safe_payload, sort_keys=True),
                "delay": delay,
            },
        )


def _source_candidates(source_id: str, resource: str) -> tuple[str, ...]:
    if not source_id:
        return ()
    if source_id.startswith("gid://"):
        return (source_id, source_id.rsplit("/", 1)[-1])
    return (source_id, f"gid://shopify/{resource}/{source_id}")


def _expanded_candidates(values: Any, resource: str) -> list[str]:
    result: list[str] = []
    for value in values if isinstance(values, list) else []:
        result.extend(_source_candidates(str(value), resource))
    return result


def _execute_count(connection: Any, statement: str, parameters: Mapping[str, Any]) -> int:
    return max(0, connection.execute(text(statement), parameters).rowcount or 0)
