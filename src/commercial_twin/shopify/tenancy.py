"""Server-side tenant provisioning derived only from verified identity claims."""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, text

from commercial_twin.database_security import tenant_identity_transaction

from .auth import MerchantPrincipal
from .identity import VerifiedIdentity


class TenantResolver(Protocol):
    def resolve(self, identity: VerifiedIdentity) -> MerchantPrincipal: ...


@dataclass(frozen=True)
class TenantIds:
    organization_id: UUID
    merchant_id: UUID


class TenantIdDeriver:
    def __init__(self, key: str) -> None:
        if len(key.encode()) < 32:
            raise ValueError("tenant provisioning key must contain at least 32 bytes")
        self._key = key.encode()

    @classmethod
    def from_env(cls) -> TenantIdDeriver:
        key = os.environ.get("TENANT_PROVISIONING_KEY", "")
        if not key:
            raise RuntimeError("missing required tenant configuration: TENANT_PROVISIONING_KEY")
        return cls(key)

    def derive(self, identity: VerifiedIdentity) -> TenantIds:
        if (
            not identity.issuer.startswith("https://")
            or not identity.subject.strip()
            or len(identity.subject) > 255
        ):
            raise ValueError("invalid verified identity")
        canonical = f"{identity.issuer}\0{identity.subject}".encode()
        organization_digest = hmac.new(
            self._key, b"org\0" + canonical, hashlib.sha256
        ).digest()
        merchant_digest = hmac.new(
            self._key, b"merchant\0" + canonical, hashlib.sha256
        ).digest()
        return TenantIds(
            organization_id=_uuid_from_digest(organization_digest),
            merchant_id=_uuid_from_digest(merchant_digest),
        )


class SqlTenantProvisioner:
    def __init__(self, engine: Engine, deriver: TenantIdDeriver) -> None:
        self.engine = engine
        self.deriver = deriver

    def resolve(self, identity: VerifiedIdentity) -> MerchantPrincipal:
        ids = self.deriver.derive(identity)
        slug = f"clerk-{ids.merchant_id.hex[:20]}"
        with tenant_identity_transaction(
            self.engine, ids.organization_id, ids.merchant_id
        ) as connection:
            connection.execute(
                text("""
                INSERT INTO organizations (id, name)
                VALUES (:organization_id, 'Exergi workspace')
                ON CONFLICT (id) DO NOTHING
                """),
                {"organization_id": ids.organization_id},
            )
            connection.execute(
                text("""
                INSERT INTO merchants
                    (id, organization_id, name, slug, timezone, currency, status)
                VALUES
                    (:merchant_id, :organization_id, 'Exergi merchant', :slug,
                     'UTC', 'XXX', 'ACTIVE')
                ON CONFLICT (id) DO NOTHING
                """),
                {
                    "merchant_id": ids.merchant_id,
                    "organization_id": ids.organization_id,
                    "slug": slug,
                },
            )
            row = (
                connection.execute(
                    text("""
                    INSERT INTO identity_tenants
                        (provider, issuer, subject, organization_id, merchant_id)
                    VALUES ('clerk', :issuer, :subject, :organization_id, :merchant_id)
                    ON CONFLICT (issuer, subject) DO UPDATE SET updated_at = now()
                    RETURNING organization_id, merchant_id
                    """),
                    {
                        "issuer": identity.issuer,
                        "subject": identity.subject,
                        "organization_id": ids.organization_id,
                        "merchant_id": ids.merchant_id,
                    },
                )
                .mappings()
                .one()
            )
            connection.execute(
                text("""
                INSERT INTO maintenance_tenants (merchant_id)
                VALUES (:merchant_id)
                ON CONFLICT (merchant_id) DO UPDATE SET updated_at = now()
                """),
                {"merchant_id": ids.merchant_id},
            )
        if row["organization_id"] != ids.organization_id or row["merchant_id"] != ids.merchant_id:
            raise RuntimeError("verified identity is bound to a different tenant")
        return MerchantPrincipal(ids.organization_id, ids.merchant_id, identity.subject)


class MemoryTenantProvisioner:
    """Thread-safe test implementation of the same immutable identity binding."""

    def __init__(self, deriver: TenantIdDeriver) -> None:
        self.deriver = deriver
        self._bindings: dict[tuple[str, str], TenantIds] = {}
        self._lock = threading.Lock()

    def resolve(self, identity: VerifiedIdentity) -> MerchantPrincipal:
        ids = self.deriver.derive(identity)
        key = (identity.issuer, identity.subject)
        with self._lock:
            existing = self._bindings.setdefault(key, ids)
        if existing != ids:
            raise RuntimeError("verified identity is bound to a different tenant")
        return MerchantPrincipal(ids.organization_id, ids.merchant_id, identity.subject)


def _uuid_from_digest(digest: bytes) -> UUID:
    raw = bytearray(digest[:16])
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return UUID(bytes=bytes(raw))
