"""External connector contracts; no credential or live-success fabrication."""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class SecretResolver(Protocol):
    def resolve(self, reference: str) -> str: ...


@dataclass(frozen=True)
class ConnectorStatus:
    provider: str
    implementation: str
    live_connection: str
    reason: str


class ShopifyConnector:
    """Pinned Shopify Admin GraphQL connector contract."""

    api_version = "2026-07"
    resources = ("customers", "products", "variants", "orders", "refunds")

    @staticmethod
    def verify_webhook(body: bytes, signature: str, secret: str) -> bool:
        digest = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
        return hmac.compare_digest(digest, signature)

    @staticmethod
    def status(*, credentials_available: bool = False) -> ConnectorStatus:
        return ConnectorStatus(
            provider="shopify",
            implementation="CONTRACT_AND_MOCK_READY",
            live_connection="NOT_ATTEMPTED" if not credentials_available else "CREDENTIALS_PRESENT",
            reason="Live backfill requires merchant-authorized Admin API credentials.",
        )


class KlaviyoConnector:
    """Klaviyo read connector contract with explicit causal-assignment boundary."""

    api_revision = "2026-07-15"
    resources = ("profiles", "events", "campaigns", "messages")

    @staticmethod
    def evidence_status(record: dict[str, Any]) -> str:
        required = {"eligibility", "assignment", "control", "assignment_probability"}
        return (
            "RANDOMIZED_CAUSAL_ELIGIBLE"
            if required <= record.keys()
            else "CAUSAL_ASSIGNMENT_NOT_IDENTIFIED"
        )

    @staticmethod
    def status(*, credentials_available: bool = False) -> ConnectorStatus:
        return ConnectorStatus(
            provider="klaviyo",
            implementation="CONTRACT_AND_MOCK_READY",
            live_connection="NOT_ATTEMPTED" if not credentials_available else "CREDENTIALS_PRESENT",
            reason="Historical messages are observational unless assignment metadata exists.",
        )


class CanonicalCsvImporter:
    supported_types = frozenset(
        {"costs", "historical_experiments", "returns", "offline_orders", "behavioral_events"}
    )

    def parse(self, data_type: str, content: str) -> tuple[dict[str, str], ...]:
        if data_type not in self.supported_types:
            raise ValueError(f"unsupported CSV type: {data_type}")
        rows = tuple(dict(row) for row in csv.DictReader(io.StringIO(content)))
        if not rows:
            raise ValueError("CSV contains no records")
        return rows


def validate_event_payload(event: dict[str, Any]) -> None:
    allowed = {
        "page_view",
        "product_view",
        "search",
        "click",
        "add_to_cart",
        "remove_from_cart",
        "checkout_started",
    }
    if event.get("event_type") not in allowed:
        raise ValueError("unsupported web event type")
    occurred = event.get("occurred_at")
    if not isinstance(occurred, datetime) or occurred.tzinfo is None:
        raise ValueError("occurred_at must be timezone-aware")
