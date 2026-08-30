"""Standalone Shopify authorization-code grant with rotating offline tokens."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID, uuid4, uuid5

from .config import ShopifySettings
from .repository import Installation, ShopifyRepository
from .security import (
    StateSigner,
    TokenCipher,
    canonicalize_shop_domain,
    nonce_hash,
    verify_shopify_oauth_hmac,
)

SHOP_NAMESPACE = UUID("b753b57e-c38e-4b85-b6de-f8d20a42db07")


class TokenExchange(Protocol):
    def exchange(self, shop: str, form: Mapping[str, str]) -> dict[str, Any]: ...


class UrllibTokenExchange:
    def exchange(self, shop: str, form: Mapping[str, str]) -> dict[str, Any]:
        request = Request(
            f"https://{shop}/admin/oauth/access_token",
            data=urlencode(form).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:  # noqa: S310 - domain is validated
            payload = json.loads(response.read())
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected Shopify token response")
        return payload


@dataclass(frozen=True)
class OAuthStart:
    authorization_url: str
    expires_at: datetime


class ShopifyOAuthService:
    def __init__(
        self,
        settings: ShopifySettings,
        repository: ShopifyRepository,
        *,
        token_exchange: TokenExchange | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.signer = StateSigner(settings.oauth_state_key)
        self.cipher = TokenCipher(settings.token_encryption_key)
        self.token_exchange = token_exchange or UrllibTokenExchange()
        self.clock = clock or (lambda: datetime.now(UTC))

    def begin(self, organization_id: UUID, merchant_id: UUID, shop_input: str) -> OAuthStart:
        shop = canonicalize_shop_domain(shop_input)
        state = self.signer.issue(organization_id, merchant_id, shop)
        expires_at = datetime.fromtimestamp(state.expires_at, UTC)
        self.repository.store_oauth_nonce(merchant_id, shop, nonce_hash(state.nonce), expires_at)
        query = urlencode(
            {
                "client_id": self.settings.client_id,
                "scope": ",".join(self.settings.scopes),
                "redirect_uri": self.settings.oauth_callback_url,
                "state": self.signer.encode(state),
            }
        )
        return OAuthStart(f"https://{shop}/admin/oauth/authorize?{query}", expires_at)

    def complete(self, parameters: Mapping[str, str]) -> Installation:
        if not verify_shopify_oauth_hmac(parameters, self.settings.client_secret):
            raise ValueError("invalid Shopify OAuth HMAC")
        shop = canonicalize_shop_domain(parameters.get("shop", ""))
        state = self.signer.decode(parameters.get("state", ""))
        if state.shop != shop:
            raise ValueError("OAuth shop/state mismatch")
        merchant_id = UUID(state.merchant_id)
        if not self.repository.consume_oauth_nonce(merchant_id, shop, nonce_hash(state.nonce)):
            raise ValueError("OAuth state is unknown, expired or already consumed")
        code = parameters.get("code", "")
        if not code:
            raise ValueError("missing OAuth authorization code")
        response = self.token_exchange.exchange(
            shop,
            {
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
                "code": code,
                "expiring": "1",
            },
        )
        return self._persist_token_response(state, response)

    def refresh(self, installation: Installation) -> Installation:
        if not installation.encrypted_refresh_token:
            raise RuntimeError("Shopify reauthorization required: refresh token is unavailable")
        refresh_token = self.cipher.decrypt(installation.encrypted_refresh_token)
        response = self.token_exchange.exchange(
            installation.shop_domain,
            {
                "grant_type": "refresh_token",
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
                "refresh_token": refresh_token,
            },
        )
        return self._persist_token_response_from_installation(installation, response)

    def disconnect(self, merchant_id: UUID, shop_input: str, actor: str) -> None:
        shop = canonicalize_shop_domain(shop_input)
        self.repository.disconnect(merchant_id, shop, self.clock())
        self.repository.audit(merchant_id, "SHOPIFY_DISCONNECTED", actor, {"shop": shop})

    def _persist_token_response(self, state: Any, response: Mapping[str, Any]) -> Installation:
        now = self.clock()
        installation = Installation(
            id=uuid4(),
            organization_id=UUID(state.organization_id),
            merchant_id=UUID(state.merchant_id),
            shop_id=uuid5(SHOP_NAMESPACE, state.shop),
            shop_domain=state.shop,
            encrypted_access_token="",
            encrypted_refresh_token=None,
            scopes=(),
            api_version=self.settings.api_version,
            access_token_expires_at=None,
            refresh_token_expires_at=None,
            status="CONNECTED",
            installed_at=now,
            updated_at=now,
        )
        return self._persist_token_response_from_installation(installation, response)

    def _persist_token_response_from_installation(
        self, installation: Installation, response: Mapping[str, Any]
    ) -> Installation:
        access_token = _required_string(response, "access_token")
        refresh_token = response.get("refresh_token")
        scopes = tuple(sorted(filter(None, str(response.get("scope", "")).split(","))))
        requested = set(self.settings.scopes)
        if not requested.issubset(scopes):
            missing = ", ".join(sorted(requested - set(scopes)))
            raise RuntimeError(f"Shopify did not grant required scopes: {missing}")
        if any(scope.startswith("write_") for scope in scopes):
            raise RuntimeError("Shopify returned a forbidden write scope")
        now = self.clock()
        expires_in = _positive_int(response.get("expires_in"))
        refresh_expires_in = _positive_int(response.get("refresh_token_expires_in"))
        updated = replace(
            installation,
            encrypted_access_token=self.cipher.encrypt(access_token),
            encrypted_refresh_token=(
                self.cipher.encrypt(str(refresh_token)) if refresh_token else None
            ),
            scopes=scopes,
            access_token_expires_at=now + timedelta(seconds=expires_in) if expires_in else None,
            refresh_token_expires_at=(
                now + timedelta(seconds=refresh_expires_in) if refresh_expires_in else None
            ),
            status="CONNECTED",
            updated_at=now,
        )
        persisted = self.repository.upsert_installation(updated)
        self.repository.audit(
            persisted.merchant_id,
            "SHOPIFY_CONNECTED",
            "shopify_oauth",
            {"shop": persisted.shop_domain, "scopes": list(scopes)},
        )
        return persisted


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Shopify token response omitted {key}")
    return value


def _positive_int(value: Any) -> int | None:
    if value is None:
        return None
    answer = int(value)
    return answer if answer > 0 else None
