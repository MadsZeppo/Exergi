"""Persistence boundaries for Shopify installation, replay protection and raw ingestion."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import Engine, create_engine, text

from commercial_twin.database_security import (
    set_tenant_context,
    shop_route_transaction,
    tenant_transaction,
)
from commercial_twin.database_url import normalize_sqlalchemy_url


@dataclass(frozen=True)
class Installation:
    id: UUID
    organization_id: UUID
    merchant_id: UUID
    shop_id: UUID
    shop_domain: str
    encrypted_access_token: str
    encrypted_refresh_token: str | None
    scopes: tuple[str, ...]
    api_version: str
    access_token_expires_at: datetime | None
    refresh_token_expires_at: datetime | None
    status: str
    installed_at: datetime
    updated_at: datetime


class ShopifyRepository(Protocol):
    def store_oauth_nonce(
        self, merchant_id: UUID, shop: str, nonce_hash: str, expires_at: datetime
    ) -> None: ...

    def consume_oauth_nonce(self, merchant_id: UUID, shop: str, nonce_hash: str) -> bool: ...

    def upsert_installation(self, installation: Installation) -> Installation: ...

    def get_installation(self, merchant_id: UUID, shop: str) -> Installation | None: ...

    def disconnect(self, merchant_id: UUID, shop: str, at: datetime) -> None: ...

    def register_webhook(
        self, shop: str, webhook_id: str, topic: str, payload_hash: str, received_at: datetime
    ) -> bool: ...

    def append_raw_object(
        self,
        *,
        merchant_id: UUID,
        shop_id: UUID,
        sync_run_id: UUID,
        object_type: str,
        source_id: str,
        source_updated_at: datetime | None,
        source_version: str,
        payload: dict[str, Any],
        payload_hash: str,
        observed_at: datetime,
    ) -> bool: ...

    def audit(
        self, merchant_id: UUID, event_type: str, actor: str, details: dict[str, Any]
    ) -> None: ...


class MemoryShopifyRepository:
    """Deterministic test repository implementing the production persistence contract."""

    def __init__(self) -> None:
        self.nonces: dict[tuple[UUID, str, str], tuple[datetime, bool]] = {}
        self.installations: dict[tuple[UUID, str], Installation] = {}
        self.webhooks: set[tuple[str, str]] = set()
        self.raw: set[tuple[UUID, str, str, str]] = set()
        self.audit_rows: list[dict[str, Any]] = []

    def store_oauth_nonce(
        self, merchant_id: UUID, shop: str, nonce_hash: str, expires_at: datetime
    ) -> None:
        self.nonces[(merchant_id, shop, nonce_hash)] = (expires_at, False)

    def consume_oauth_nonce(self, merchant_id: UUID, shop: str, nonce_hash: str) -> bool:
        key = (merchant_id, shop, nonce_hash)
        record = self.nonces.get(key)
        now = datetime.now(UTC)
        if record is None or record[1] or record[0] < now:
            return False
        self.nonces[key] = (record[0], True)
        return True

    def upsert_installation(self, installation: Installation) -> Installation:
        key = (installation.merchant_id, installation.shop_domain)
        if any(
            shop == installation.shop_domain and merchant != installation.merchant_id
            for merchant, shop in self.installations
        ):
            raise PermissionError("Shopify shop is already bound to another tenant")
        existing = self.installations.get(key)
        answer = installation if existing is None else replace(installation, id=existing.id)
        self.installations[key] = answer
        return answer

    def get_installation(self, merchant_id: UUID, shop: str) -> Installation | None:
        return self.installations.get((merchant_id, shop))

    def disconnect(self, merchant_id: UUID, shop: str, at: datetime) -> None:
        current = self.installations.get((merchant_id, shop))
        if current:
            self.installations[(merchant_id, shop)] = replace(
                current,
                encrypted_access_token="",
                encrypted_refresh_token=None,
                status="DISCONNECTED",
                updated_at=at,
            )

    def register_webhook(
        self, shop: str, webhook_id: str, topic: str, payload_hash: str, received_at: datetime
    ) -> bool:
        del topic, payload_hash, received_at
        key = (shop, webhook_id)
        if key in self.webhooks:
            return False
        self.webhooks.add(key)
        return True

    def append_raw_object(
        self,
        *,
        merchant_id: UUID,
        shop_id: UUID,
        sync_run_id: UUID,
        object_type: str,
        source_id: str,
        source_updated_at: datetime | None,
        source_version: str,
        payload: dict[str, Any],
        payload_hash: str,
        observed_at: datetime,
    ) -> bool:
        del sync_run_id, source_updated_at, source_version, payload, observed_at
        key = (merchant_id, str(shop_id), object_type, f"{source_id}:{payload_hash}")
        if key in self.raw:
            return False
        self.raw.add(key)
        return True

    def audit(
        self, merchant_id: UUID, event_type: str, actor: str, details: dict[str, Any]
    ) -> None:
        self.audit_rows.append(
            {"merchant_id": merchant_id, "event_type": event_type, "actor": actor, **details}
        )


class SqlShopifyRepository:
    """PostgreSQL repository; every query includes the authenticated merchant boundary."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def from_url(cls, database_url: str) -> SqlShopifyRepository:
        return cls(create_engine(normalize_sqlalchemy_url(database_url), pool_pre_ping=True))

    def store_oauth_nonce(
        self, merchant_id: UUID, shop: str, nonce_hash: str, expires_at: datetime
    ) -> None:
        with tenant_transaction(self.engine, merchant_id) as connection:
            connection.execute(
                text("""
                INSERT INTO shopify_oauth_nonces
                    (merchant_id, shop_domain, nonce_hash, expires_at)
                VALUES (:merchant_id, :shop, :nonce_hash, :expires_at)
                """),
                {
                    "merchant_id": merchant_id,
                    "shop": shop,
                    "nonce_hash": nonce_hash,
                    "expires_at": expires_at,
                },
            )

    def consume_oauth_nonce(self, merchant_id: UUID, shop: str, nonce_hash: str) -> bool:
        with tenant_transaction(self.engine, merchant_id) as connection:
            result = connection.execute(
                text("""
                UPDATE shopify_oauth_nonces SET consumed_at = now()
                WHERE merchant_id = :merchant_id AND shop_domain = :shop
                  AND nonce_hash = :nonce_hash AND consumed_at IS NULL AND expires_at >= now()
                RETURNING id
                """),
                {"merchant_id": merchant_id, "shop": shop, "nonce_hash": nonce_hash},
            )
            return result.first() is not None

    def upsert_installation(self, installation: Installation) -> Installation:
        values = _installation_values(installation)
        with tenant_transaction(self.engine, installation.merchant_id) as connection:
            row = connection.execute(
                text("""
                INSERT INTO shop_connections
                    (id, organization_id, merchant_id, shop_id, shop_domain,
                     encrypted_access_token, encrypted_refresh_token, scopes_json,
                     api_version, access_token_expires_at, refresh_token_expires_at,
                     status, installed_at, updated_at)
                VALUES
                    (:id, :organization_id, :merchant_id, :shop_id, :shop_domain,
                     :encrypted_access_token, :encrypted_refresh_token, CAST(:scopes_json AS jsonb),
                     :api_version, :access_token_expires_at, :refresh_token_expires_at,
                     :status, :installed_at, :updated_at)
                ON CONFLICT (shop_domain) DO UPDATE SET
                    encrypted_access_token = EXCLUDED.encrypted_access_token,
                    encrypted_refresh_token = EXCLUDED.encrypted_refresh_token,
                    scopes_json = EXCLUDED.scopes_json,
                    api_version = EXCLUDED.api_version,
                    access_token_expires_at = EXCLUDED.access_token_expires_at,
                    refresh_token_expires_at = EXCLUDED.refresh_token_expires_at,
                    status = 'CONNECTED', updated_at = EXCLUDED.updated_at
                WHERE shop_connections.merchant_id = EXCLUDED.merchant_id
                RETURNING id
                """),
                values,
            ).first()
            if row is None:
                raise PermissionError("Shopify shop is already bound to another tenant")
            values["id"] = row.id
            connection.execute(
                text("""
                INSERT INTO data_connections
                    (id, merchant_id, provider, status, external_account_id, api_version,
                     encrypted_secret_reference, scopes_json, created_at, updated_at)
                VALUES (:id, :merchant_id, 'shopify', :status, :shop_domain, :api_version,
                        'shop_connections.encrypted_access_token', CAST(:scopes_json AS jsonb),
                        :installed_at, :updated_at)
                ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status,
                    api_version = EXCLUDED.api_version, scopes_json = EXCLUDED.scopes_json,
                    updated_at = EXCLUDED.updated_at
                """),
                values,
            )
        return replace(installation, id=row.id)

    def get_installation(self, merchant_id: UUID, shop: str) -> Installation | None:
        with tenant_transaction(self.engine, merchant_id) as connection:
            row = (
                connection.execute(
                    text("""
                SELECT * FROM shop_connections
                WHERE merchant_id = :merchant_id AND shop_domain = :shop
                """),
                    {"merchant_id": merchant_id, "shop": shop},
                )
                .mappings()
                .first()
            )
        return _installation_from_row(row) if row else None

    def disconnect(self, merchant_id: UUID, shop: str, at: datetime) -> None:
        with tenant_transaction(self.engine, merchant_id) as connection:
            connection.execute(
                text("""
                UPDATE shop_connections SET encrypted_access_token = '',
                    encrypted_refresh_token = NULL, status = 'DISCONNECTED', updated_at = :at
                WHERE merchant_id = :merchant_id AND shop_domain = :shop
                """),
                {"merchant_id": merchant_id, "shop": shop, "at": at},
            )

    def register_webhook(
        self, shop: str, webhook_id: str, topic: str, payload_hash: str, received_at: datetime
    ) -> bool:
        with shop_route_transaction(self.engine, shop) as connection:
            route = (
                connection.execute(
                    text("""
                    SELECT merchant_id, shop_id FROM shop_connections
                    WHERE shop_domain = :shop
                    """),
                    {"shop": shop},
                )
                .mappings()
                .first()
            )
            if route is None:
                return False
            set_tenant_context(connection, route["merchant_id"])
            row = connection.execute(
                text("""
                INSERT INTO shopify_webhook_receipts
                    (merchant_id, shop_id, shop_domain, webhook_id, topic, payload_hash,
                     received_at)
                VALUES (:merchant_id, :shop_id, :shop, :webhook_id, :topic, :payload_hash,
                        :received_at)
                ON CONFLICT (shop_domain, webhook_id) DO NOTHING RETURNING id
                """),
                {
                    "merchant_id": route["merchant_id"],
                    "shop_id": route["shop_id"],
                    "shop": shop,
                    "webhook_id": webhook_id,
                    "topic": topic,
                    "payload_hash": payload_hash,
                    "received_at": received_at,
                },
            ).first()
            return row is not None

    def append_raw_object(
        self,
        *,
        merchant_id: UUID,
        shop_id: UUID,
        sync_run_id: UUID,
        object_type: str,
        source_id: str,
        source_updated_at: datetime | None,
        source_version: str,
        payload: dict[str, Any],
        payload_hash: str,
        observed_at: datetime,
    ) -> bool:
        with tenant_transaction(self.engine, merchant_id) as connection:
            row = connection.execute(
                text("""
                INSERT INTO raw_import_objects
                    (merchant_id, shop_id, sync_run_id, object_type, source_id,
                     source_updated_at, source_version, payload_json, payload_hash,
                     observed_at, ingested_at)
                VALUES (:merchant_id, :shop_id, :sync_run_id, :object_type, :source_id,
                        :source_updated_at, :source_version, CAST(:payload AS jsonb), :payload_hash,
                        :observed_at, now())
                ON CONFLICT (shop_id, object_type, source_id, payload_hash) DO NOTHING RETURNING id
                """),
                {
                    "merchant_id": merchant_id,
                    "shop_id": shop_id,
                    "sync_run_id": sync_run_id,
                    "object_type": object_type,
                    "source_id": source_id,
                    "source_updated_at": source_updated_at,
                    "source_version": source_version,
                    "payload": json.dumps(payload, sort_keys=True),
                    "payload_hash": payload_hash,
                    "observed_at": observed_at,
                },
            ).first()
            return row is not None

    def audit(
        self, merchant_id: UUID, event_type: str, actor: str, details: dict[str, Any]
    ) -> None:
        with tenant_transaction(self.engine, merchant_id) as connection:
            connection.execute(
                text("""
                INSERT INTO audit_log
                    (id, merchant_id, event_type, actor_reference, occurred_at, detail_json)
                VALUES (:id, :merchant_id, :event_type, :actor, now(), CAST(:details AS jsonb))
                """),
                {
                    "id": uuid4(),
                    "merchant_id": merchant_id,
                    "event_type": event_type,
                    "actor": actor,
                    "details": json.dumps(details, sort_keys=True),
                },
            )


def _installation_values(installation: Installation) -> dict[str, Any]:
    values = installation.__dict__.copy()
    values["scopes_json"] = json.dumps(list(installation.scopes))
    return values


def _installation_from_row(row: Any) -> Installation:
    scopes = row["scopes_json"]
    return Installation(
        id=row["id"],
        organization_id=row["organization_id"],
        merchant_id=row["merchant_id"],
        shop_id=row["shop_id"],
        shop_domain=row["shop_domain"],
        encrypted_access_token=row["encrypted_access_token"],
        encrypted_refresh_token=row["encrypted_refresh_token"],
        scopes=tuple(scopes if isinstance(scopes, list) else json.loads(scopes)),
        api_version=row["api_version"],
        access_token_expires_at=row["access_token_expires_at"],
        refresh_token_expires_at=row["refresh_token_expires_at"],
        status=row["status"],
        installed_at=row["installed_at"],
        updated_at=row["updated_at"],
    )
