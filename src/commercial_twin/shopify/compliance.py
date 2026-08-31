"""Versioned agreement acceptance backed by the exact public document payload."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from commercial_twin.database_security import tenant_transaction

from .auth import MerchantPrincipal

DOCUMENT_PATH = Path(__file__).with_name("compliance_documents.json")
REQUIRED_DOCUMENTS = ("terms", "privacy", "dpa", "subprocessors")
COMPLIANCE_WEBHOOK_TOPICS = (
    "customers/data_request",
    "customers/redact",
    "shop/redact",
    "app/uninstalled",
)


def load_documents() -> dict[str, Any]:
    payload = json.loads(DOCUMENT_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(name in payload for name in REQUIRED_DOCUMENTS):
        raise RuntimeError("compliance document bundle is invalid")
    return payload


def current_document_contract() -> tuple[str, dict[str, str]]:
    payload = load_documents()
    version = str(payload["version"])
    hashes = {
        name: hashlib.sha256(
            json.dumps(payload[name], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for name in REQUIRED_DOCUMENTS
    }
    return version, hashes


class AgreementRequiredError(RuntimeError):
    pass


class AgreementGate(Protocol):
    def require_current(self, principal: MerchantPrincipal) -> None: ...


@dataclass(frozen=True)
class AgreementStatus:
    required_version: str
    accepted: bool
    accepted_at: str | None
    document_hashes: dict[str, str]


class SqlAgreementService:
    def __init__(self, engine: Engine, audit_key: str, dashboard_origin: str) -> None:
        if len(audit_key.encode()) < 32:
            raise ValueError("agreement audit key must contain at least 32 bytes")
        self.engine = engine
        self._audit_key = audit_key.encode()
        self.dashboard_origin = dashboard_origin.rstrip("/")

    @classmethod
    def from_env(cls, engine: Engine, dashboard_origin: str) -> SqlAgreementService:
        key = os.environ.get("AGREEMENT_AUDIT_KEY", "")
        if not key:
            raise RuntimeError("missing required compliance configuration: AGREEMENT_AUDIT_KEY")
        return cls(engine, key, dashboard_origin)

    def status(self, principal: MerchantPrincipal) -> AgreementStatus:
        version, hashes = current_document_contract()
        with tenant_transaction(self.engine, principal.merchant_id) as connection:
            row = (
                connection.execute(
                    text("""
                    SELECT accepted_at FROM merchant_agreement_acceptances
                    WHERE merchant_id = :merchant_id AND agreement_version = :version
                      AND document_hashes = CAST(:hashes AS jsonb)
                    ORDER BY accepted_at DESC LIMIT 1
                    """),
                    {
                        "merchant_id": principal.merchant_id,
                        "version": version,
                        "hashes": json.dumps(hashes, sort_keys=True),
                    },
                )
                .mappings()
                .first()
            )
        return AgreementStatus(
            version,
            row is not None,
            row["accepted_at"].isoformat() if row is not None else None,
            hashes,
        )

    def require_current(self, principal: MerchantPrincipal) -> None:
        if not self.status(principal).accepted:
            raise AgreementRequiredError("current Terms, Privacy Policy and DPA must be accepted")

    def accept(
        self,
        principal: MerchantPrincipal,
        *,
        requested_version: str,
        client_ip: str,
        user_agent: str,
        origin: str,
    ) -> AgreementStatus:
        version, hashes = current_document_contract()
        if requested_version != version:
            raise ValueError("agreement version is no longer current")
        subject_hash = self._digest(f"subject:{principal.subject}")
        ip_hash = self._digest(f"ip:{client_ip or 'unknown'}")
        user_agent_hash = self._digest(f"ua:{user_agent[:512] or 'unknown'}")
        safe_origin = (
            origin.rstrip("/") if origin.rstrip("/") == self.dashboard_origin else "direct"
        )
        with tenant_transaction(self.engine, principal.merchant_id) as connection:
            connection.execute(
                text("""
                INSERT INTO maintenance_tenants (merchant_id)
                VALUES (:merchant_id)
                ON CONFLICT (merchant_id) DO UPDATE SET updated_at = now()
                """),
                {"merchant_id": principal.merchant_id},
            )
            connection.execute(
                text("""
                INSERT INTO merchant_agreement_acceptances
                    (id, organization_id, merchant_id, agreement_version, document_hashes,
                     clerk_subject_hash, request_ip_hash, user_agent_hash, request_origin)
                VALUES
                    (:id, :organization_id, :merchant_id, :version, CAST(:hashes AS jsonb),
                     :subject_hash, :ip_hash, :user_agent_hash, :origin)
                ON CONFLICT (merchant_id, agreement_version, clerk_subject_hash) DO NOTHING
                """),
                {
                    "id": uuid4(),
                    "organization_id": principal.organization_id,
                    "merchant_id": principal.merchant_id,
                    "version": version,
                    "hashes": json.dumps(hashes, sort_keys=True),
                    "subject_hash": subject_hash,
                    "ip_hash": ip_hash,
                    "user_agent_hash": user_agent_hash,
                    "origin": safe_origin,
                },
            )
        return self.status(principal)

    def dashboard(self, principal: MerchantPrincipal) -> dict[str, Any]:
        status = self.status(principal)
        with tenant_transaction(self.engine, principal.merchant_id) as connection:
            latest = (
                connection.execute(
                    text("""
                    SELECT started_at, completed_at, status, rows_deleted_json, jobs_processed
                    FROM compliance_runs WHERE merchant_id = :merchant_id
                    ORDER BY started_at DESC LIMIT 1
                    """),
                    {"merchant_id": principal.merchant_id},
                )
                .mappings()
                .first()
            )
            job_rows = (
                connection.execute(
                    text("""
                    SELECT status, count(*) AS count FROM jobs
                    WHERE merchant_id = :merchant_id
                      AND job_type = ANY(:job_types)
                    GROUP BY status
                    """),
                    {
                        "merchant_id": principal.merchant_id,
                        "job_types": [
                            "SHOPIFY_CUSTOMER_DATA_EXPORT",
                            "SHOPIFY_CUSTOMER_REDACTION_AUDIT",
                            "SHOPIFY_SHOP_HARD_DELETE",
                            "SHOPIFY_RETENTION_REVIEW",
                        ],
                    },
                )
                .mappings()
                .all()
            )
            jobs: dict[str, int] = {
                str(row["status"]): int(row["count"]) for row in job_rows
            }
            exports_ready = connection.execute(
                text("""
                SELECT count(*) FROM privacy_exports
                WHERE merchant_id = :merchant_id AND status = 'READY' AND expires_at > now()
                """),
                {"merchant_id": principal.merchant_id},
            ).scalar_one()
        verified_at = os.environ.get("SHOPIFY_WEBHOOKS_VERIFIED_AT") or None
        return {
            "agreement": status.__dict__,
            "latest_retention_run": dict(latest) if latest else None,
            "privacy_jobs": {"pending": jobs.get("PENDING", 0), "failed": jobs.get("FAILED", 0)},
            "privacy_exports_ready": exports_ready,
            "webhooks": [
                {
                    "topic": topic,
                    "declared": True,
                    "deployment_status": (
                        "LIVE_VERIFIED" if verified_at else "DECLARED_NOT_VERIFIED"
                    ),
                    "verified_at": verified_at,
                }
                for topic in COMPLIANCE_WEBHOOK_TOPICS
            ],
        }

    def list_exports(self, principal: MerchantPrincipal) -> list[dict[str, Any]]:
        with tenant_transaction(self.engine, principal.merchant_id) as connection:
            rows = (
                connection.execute(
                    text("""
                    SELECT id, status, created_at, expires_at FROM privacy_exports
                    WHERE merchant_id = :merchant_id AND expires_at > now()
                    ORDER BY created_at DESC
                    """),
                    {"merchant_id": principal.merchant_id},
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    def export(self, principal: MerchantPrincipal, export_id: UUID) -> dict[str, Any] | None:
        with tenant_transaction(self.engine, principal.merchant_id) as connection:
            row = (
                connection.execute(
                    text("""
                    SELECT id, status, result_json, created_at, expires_at
                    FROM privacy_exports
                    WHERE merchant_id = :merchant_id AND id = :id AND expires_at > now()
                    """),
                    {"merchant_id": principal.merchant_id, "id": export_id},
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None

    def _digest(self, value: str) -> str:
        return hmac.new(self._audit_key, value.encode(), hashlib.sha256).hexdigest()


class MemoryAgreementGate:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted

    def require_current(self, principal: MerchantPrincipal) -> None:
        del principal
        if not self.accepted:
            raise AgreementRequiredError("current agreements must be accepted")
