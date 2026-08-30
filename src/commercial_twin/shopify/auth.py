"""Signed Exergi merchant sessions used by the Shopify product endpoints."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import asdict, dataclass
from uuid import UUID


@dataclass(frozen=True)
class MerchantPrincipal:
    organization_id: UUID
    merchant_id: UUID
    subject: str


@dataclass(frozen=True)
class _SessionPayload:
    organization_id: str
    merchant_id: str
    subject: str
    issued_at: int
    expires_at: int


class SessionSigner:
    def __init__(self, key: str, *, lifetime_seconds: int = 3600) -> None:
        if len(key.encode()) < 32:
            raise ValueError("session signing key must contain at least 32 bytes")
        self._key = key.encode()
        self._lifetime_seconds = lifetime_seconds

    def issue(self, principal: MerchantPrincipal, *, now: int | None = None) -> str:
        issued_at = int(time.time()) if now is None else now
        payload = _SessionPayload(
            str(principal.organization_id),
            str(principal.merchant_id),
            principal.subject,
            issued_at,
            issued_at + self._lifetime_seconds,
        )
        raw = json.dumps(asdict(payload), sort_keys=True, separators=(",", ":")).encode()
        signature = hmac.new(self._key, raw, hashlib.sha256).digest()
        return f"{_encode(raw)}.{_encode(signature)}"

    def verify(self, token: str, *, now: int | None = None) -> MerchantPrincipal:
        try:
            raw_part, signature_part = token.split(".", 1)
            raw = _decode(raw_part)
            supplied = _decode(signature_part)
            payload = _SessionPayload(**json.loads(raw))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid Exergi session") from exc
        expected = hmac.new(self._key, raw, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("invalid Exergi session signature")
        current = int(time.time()) if now is None else now
        if payload.expires_at < current or payload.issued_at > current + 30:
            raise ValueError("expired Exergi session")
        return MerchantPrincipal(
            UUID(payload.organization_id), UUID(payload.merchant_id), payload.subject
        )


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
