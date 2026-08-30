"""OAuth, session, token and pseudonym security primitives."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from uuid import UUID

SHOP_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]\.myshopify\.com$")
SHORT_SHOP_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$")


def canonicalize_shop_domain(value: str) -> str:
    candidate = value.strip().lower().rstrip(".")
    if SHORT_SHOP_PATTERN.fullmatch(candidate):
        candidate = f"{candidate}.myshopify.com"
    if not SHOP_PATTERN.fullmatch(candidate):
        raise ValueError("shop must be a valid *.myshopify.com domain")
    return candidate


def verify_shopify_oauth_hmac(parameters: Mapping[str, str], client_secret: str) -> bool:
    supplied = parameters.get("hmac", "")
    if not supplied or not re.fullmatch(r"[0-9a-fA-F]{64}", supplied):
        return False
    message = "&".join(
        f"{key}={value}"
        for key, value in sorted(parameters.items())
        if key not in {"hmac", "signature"}
    )
    expected = hmac.new(client_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)


def verify_webhook_hmac(body: bytes, supplied: str, client_secret: str) -> bool:
    expected = base64.b64encode(
        hmac.new(client_secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, supplied)


@dataclass(frozen=True)
class OAuthState:
    organization_id: str
    merchant_id: str
    shop: str
    nonce: str
    issued_at: int
    expires_at: int


class StateSigner:
    def __init__(self, key: str, *, lifetime_seconds: int = 600) -> None:
        if len(key.encode()) < 32:
            raise ValueError("OAuth state key must contain at least 32 bytes")
        self._key = key.encode()
        self._lifetime_seconds = lifetime_seconds

    def issue(self, organization_id: UUID, merchant_id: UUID, shop: str) -> OAuthState:
        now = int(time.time())
        return OAuthState(
            organization_id=str(organization_id),
            merchant_id=str(merchant_id),
            shop=canonicalize_shop_domain(shop),
            nonce=secrets.token_urlsafe(32),
            issued_at=now,
            expires_at=now + self._lifetime_seconds,
        )

    def encode(self, state: OAuthState) -> str:
        payload = json.dumps(asdict(state), sort_keys=True, separators=(",", ":")).encode()
        signature = hmac.new(self._key, payload, hashlib.sha256).digest()
        return f"{_b64(payload)}.{_b64(signature)}"

    def decode(self, encoded: str, *, now: int | None = None) -> OAuthState:
        try:
            payload_part, signature_part = encoded.split(".", 1)
            payload = _unb64(payload_part)
            supplied = _unb64(signature_part)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid OAuth state") from exc
        expected = hmac.new(self._key, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("invalid OAuth state signature")
        try:
            state = OAuthState(**json.loads(payload))
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid OAuth state payload") from exc
        current = int(time.time()) if now is None else now
        if state.expires_at < current or state.issued_at > current + 30:
            raise ValueError("expired OAuth state")
        canonicalize_shop_domain(state.shop)
        return state


class TokenCipher:
    """Fernet envelope used only server-side; keys come from a secret manager."""

    def __init__(self, key: str) -> None:
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:  # pragma: no cover - deployment dependency check
            raise RuntimeError("cryptography is required for Shopify token encryption") from exc
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            raise ValueError("cannot encrypt an empty token")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()


def pseudonymize_customer(shop_id: UUID, source_customer_id: str, key: str) -> str:
    if len(key.encode()) < 32:
        raise ValueError("customer pseudonym key must contain at least 32 bytes")
    message = f"{shop_id}:{source_customer_id}".encode()
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()


def nonce_hash(nonce: str) -> str:
    return hashlib.sha256(nonce.encode()).hexdigest()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
