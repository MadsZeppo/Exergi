"""Verified, replay-safe Shopify webhook and privacy processing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import Engine, text

from commercial_twin.database_security import set_tenant_context, shop_route_transaction

from .repository import ShopifyRepository
from .security import canonicalize_shop_domain, verify_webhook_hmac

SUPPORTED_TOPICS = frozenset(
    {
        "app/uninstalled",
        "customers/data_request",
        "customers/redact",
        "shop/redact",
        "orders/create",
        "orders/updated",
        "orders/cancelled",
        "refunds/create",
        "products/create",
        "products/update",
        "products/delete",
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

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def data_request(self, shop: str, payload: Mapping[str, Any]) -> None:
        self._enqueue(shop, "SHOPIFY_CUSTOMER_DATA_EXPORT", payload)

    def redact_customer(self, shop: str, payload: Mapping[str, Any]) -> None:
        customer = payload.get("customer") or {}
        source_id = str(customer.get("id", "")) if isinstance(customer, Mapping) else ""
        order_ids = [str(value) for value in payload.get("orders_to_redact", [])]
        with shop_route_transaction(self.engine, shop) as connection:
            route = self._route(connection, shop)
            connection.execute(
                text("""
                DELETE FROM raw_import_objects
                WHERE merchant_id = :merchant_id AND shop_id = :shop_id AND (
                    (object_type = 'customers' AND source_id = :source_id)
                    OR (object_type = 'orders' AND source_id = ANY(:order_ids))
                    OR payload_json #>> '{customer,id}' = :source_id
                )
                """),
                {**route, "source_id": source_id, "order_ids": order_ids},
            )
            connection.execute(
                text("""
                UPDATE orders SET customer_id = NULL, deletion_status = 'CUSTOMER_REDACTED'
                WHERE merchant_id = :merchant_id AND shop_id = :shop_id
                  AND external_order_id = ANY(:order_ids)
                """),
                {**route, "order_ids": order_ids},
            )
            self._insert_job(
                connection, route, "SHOPIFY_CUSTOMER_REDACTION_AUDIT", {"orders": order_ids}
            )

    def redact_shop(self, shop: str, payload: Mapping[str, Any]) -> None:
        del payload
        with shop_route_transaction(self.engine, shop) as connection:
            route = self._route(connection, shop)
            # Raw protected data and credentials are removed immediately. Canonical financial
            # records are queued for ordered FK-safe erasure by the retention worker.
            connection.execute(
                text("DELETE FROM raw_import_objects WHERE shop_id = :shop_id"), route
            )
            connection.execute(
                text("""
                UPDATE shop_connections SET encrypted_access_token = '',
                    encrypted_refresh_token = NULL, status = 'SHOP_REDACTION_PENDING',
                    updated_at = now()
                WHERE merchant_id = :merchant_id AND shop_id = :shop_id
                """),
                route,
            )
            self._insert_job(connection, route, "SHOPIFY_SHOP_HARD_DELETE", {"shop": shop})

    def uninstall(self, shop: str, payload: Mapping[str, Any]) -> None:
        del payload
        with shop_route_transaction(self.engine, shop) as connection:
            route = self._route(connection, shop)
            connection.execute(
                text("""
                UPDATE shop_connections SET encrypted_access_token = '',
                    encrypted_refresh_token = NULL, status = 'UNINSTALLED', updated_at = now()
                WHERE merchant_id = :merchant_id AND shop_id = :shop_id
                """),
                route,
            )
            self._insert_job(connection, route, "SHOPIFY_RETENTION_REVIEW", {"shop": shop})

    def incremental(self, shop: str, topic: str, payload: Mapping[str, Any]) -> None:
        self._enqueue(shop, "SHOPIFY_INCREMENTAL_INGEST", {"topic": topic, "payload": payload})

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
    ) -> None:
        import json
        from uuid import uuid4

        connection.execute(
            text("""
            INSERT INTO jobs
                (id, merchant_id, job_type, status, payload, attempts, available_at)
            VALUES (:id, :merchant_id, :kind, 'PENDING', CAST(:payload AS jsonb), 0, now())
            """),
            {
                "id": uuid4(),
                "merchant_id": route["merchant_id"],
                "kind": kind,
                "payload": json.dumps(dict(payload), sort_keys=True),
            },
        )
