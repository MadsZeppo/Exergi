from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

import commercial_twin.shopify.api as api_module
from commercial_twin.shopify.api import build_shopify_router
from commercial_twin.shopify.compliance import MemoryAgreementGate
from commercial_twin.shopify.config import ShopifySettings
from commercial_twin.shopify.identity import (
    ClerkAuthSettings,
    ClerkJWTVerifier,
    VerifiedIdentity,
)
from commercial_twin.shopify.repository import Installation, MemoryShopifyRepository
from commercial_twin.shopify.tenancy import MemoryTenantProvisioner, TenantIdDeriver
from commercial_twin.shopify.webhooks import RecordingPrivacyProcessor, ShopifyWebhookService

ISSUER = "https://clerk.exergi.test"
PARTY = "https://exergi.vercel.app"


class StaticSigningKeys:
    def __init__(self, key: Any) -> None:
        self.key = key

    def get_signing_key_from_jwt(self, token: str) -> Any:
        del token

        @dataclass
        class SigningKey:
            key: Any

        return SigningKey(self.key)


@pytest.fixture
def private_key() -> Any:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _settings() -> ShopifySettings:
    return ShopifySettings(
        client_id="client-id",
        client_secret="s" * 40,
        app_base_url="https://exergi-api.onrender.com",
        dashboard_url=PARTY,
        token_encryption_key=Fernet.generate_key().decode(),
        oauth_state_key="o" * 40,
        customer_pseudonym_key="p" * 40,
        database_url="postgresql+psycopg://unused",
    )


def _verifier(private_key: Any) -> ClerkJWTVerifier:
    config = ClerkAuthSettings(ISSUER, f"{ISSUER}/.well-known/jwks.json", (PARTY,))
    return ClerkJWTVerifier(config, signing_keys=StaticSigningKeys(private_key.public_key()))


def _token(private_key: Any, **overrides: Any) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": "user_merchant_one",
        "azp": PARTY,
        "iat": now,
        "nbf": now - 1,
        "exp": now + 300,
        **overrides,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def _app(private_key: Any) -> tuple[TestClient, MemoryShopifyRepository]:
    config = _settings()
    repository = MemoryShopifyRepository()
    tenants = MemoryTenantProvisioner(TenantIdDeriver("t" * 40))
    webhooks = ShopifyWebhookService(
        config.client_secret, repository, RecordingPrivacyProcessor()
    )
    app = FastAPI()
    app.include_router(
        build_shopify_router(
            config,
            repository,
            webhooks,
            _verifier(private_key),
            tenants,
            agreement_gate=MemoryAgreementGate(),
        )
    )
    return TestClient(app), repository


def test_clerk_configuration_fails_closed(monkeypatch: Any) -> None:
    for key in ("CLERK_ISSUER_URL", "CLERK_JWKS_URL", "CLERK_AUTHORIZED_PARTIES"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="missing required Clerk configuration"):
        ClerkAuthSettings.from_env()
    monkeypatch.setenv("CLERK_ISSUER_URL", "http://unsafe.example")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://clerk.example/.well-known/jwks.json")
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", PARTY)
    with pytest.raises(RuntimeError, match="must use HTTPS"):
        ClerkAuthSettings.from_env()


def test_install_is_public_redirect_only_and_creates_no_oauth_state(private_key: Any) -> None:
    client, repository = _app(private_key)
    response = client.get(
        "/api/v1/shopify/install?shop=SAFE-SHOP.myshopify.com",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"{PARTY}/onboarding?shop=safe-shop.myshopify.com"
    assert repository.nonces == {}


def test_authenticated_routes_have_no_identity_or_tenant_query_parameters(
    private_key: Any,
) -> None:
    client, _ = _app(private_key)
    schema = client.get("/openapi.json").json()
    forbidden = {"identity", "merchant_id", "organization_id"}
    for route in schema["paths"].values():
        for operation in route.values():
            names = {
                item["name"]
                for item in operation.get("parameters", [])
                if item.get("in") == "query"
            }
            assert names.isdisjoint(forbidden)


def test_connect_without_jwt_is_401_and_valid_jwt_provisions_tenant(
    private_key: Any,
) -> None:
    client, repository = _app(private_key)
    missing = client.post("/api/v1/shopify/connect", json={"shop": "safe-shop"})
    assert missing.status_code == 401
    assert "identity" not in missing.text

    valid = client.post(
        "/api/v1/shopify/connect",
        json={"shop": "safe-shop"},
        headers={"Authorization": f"Bearer {_token(private_key)}"},
    )
    assert valid.status_code == 200
    assert valid.json()["authorization_url"].startswith("https://safe-shop.myshopify.com/admin/oauth")
    assert len(repository.nonces) == 1


def test_current_agreement_is_required_before_oauth_state_is_created(
    private_key: Any,
) -> None:
    config = _settings()
    repository = MemoryShopifyRepository()
    app = FastAPI()
    app.include_router(
        build_shopify_router(
            config,
            repository,
            ShopifyWebhookService(
                config.client_secret, repository, RecordingPrivacyProcessor()
            ),
            _verifier(private_key),
            MemoryTenantProvisioner(TenantIdDeriver("t" * 40)),
            agreement_gate=MemoryAgreementGate(accepted=False),
        )
    )
    response = TestClient(app).post(
        "/api/v1/shopify/connect",
        json={"shop": "safe-shop"},
        headers={"Authorization": f"Bearer {_token(private_key)}"},
    )
    assert response.status_code == 428
    assert response.json() == {"detail": "current agreements must be accepted"}
    assert repository.nonces == {}


def test_invalid_expired_and_unauthorized_party_tokens_are_rejected(private_key: Any) -> None:
    client, _ = _app(private_key)
    for token in (
        "not-a-jwt",
        _token(private_key, exp=int(time.time()) - 1),
        _token(private_key, azp="https://attacker.example"),
    ):
        response = client.post(
            "/api/v1/shopify/connect",
            json={"shop": "safe-shop"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert token not in response.text


def test_conflicting_verified_identity_binding_is_403(private_key: Any) -> None:
    class ConflictingTenant:
        def resolve(self, identity: VerifiedIdentity) -> Any:
            del identity
            raise RuntimeError("binding mismatch")

    config = _settings()
    repository = MemoryShopifyRepository()
    app = FastAPI()
    app.include_router(
        build_shopify_router(
            config,
            repository,
            ShopifyWebhookService(
                config.client_secret, repository, RecordingPrivacyProcessor()
            ),
            _verifier(private_key),
            ConflictingTenant(),  # type: ignore[arg-type]
            agreement_gate=MemoryAgreementGate(),
        )
    )
    response = TestClient(app).post(
        "/api/v1/shopify/connect",
        json={"shop": "safe-shop"},
        headers={"Authorization": f"Bearer {_token(private_key)}"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "tenant access denied"}


def test_tenant_provisioning_is_stable_concurrent_and_identity_isolated() -> None:
    tenants = MemoryTenantProvisioner(TenantIdDeriver("k" * 40))
    identity = VerifiedIdentity(ISSUER, "user_one")
    with ThreadPoolExecutor(max_workers=8) as pool:
        principals = list(pool.map(lambda _: tenants.resolve(identity), range(32)))
    assert len({item.merchant_id for item in principals}) == 1
    other = tenants.resolve(VerifiedIdentity(ISSUER, "user_two"))
    assert other.merchant_id != principals[0].merchant_id
    assert other.organization_id != principals[0].organization_id
    with pytest.raises(ValueError, match="invalid verified identity"):
        tenants.resolve(VerifiedIdentity("http://unsafe.example", ""))


def test_cors_allows_only_exact_dashboard_origin(private_key: Any) -> None:
    config = _settings()
    repository = MemoryShopifyRepository()
    app = FastAPI()
    app.include_router(
        build_shopify_router(
            config,
            repository,
            ShopifyWebhookService(
                config.client_secret, repository, RecordingPrivacyProcessor()
            ),
            _verifier(private_key),
            MemoryTenantProvisioner(TenantIdDeriver("t" * 40)),
            agreement_gate=MemoryAgreementGate(),
        )
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[PARTY],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    client = TestClient(app)
    approved = client.options(
        "/api/v1/shopify/connect",
        headers={"Origin": PARTY, "Access-Control-Request-Method": "POST"},
    )
    rejected = client.options(
        "/api/v1/shopify/connect",
        headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"},
    )
    assert approved.headers["access-control-allow-origin"] == PARTY
    assert "access-control-allow-origin" not in rejected.headers


def test_valid_callback_queues_initial_sync_once(monkeypatch: Any, private_key: Any) -> None:
    config = _settings()
    repository = MemoryShopifyRepository()
    installation = Installation(
        id=UUID("00000000-0000-4000-8000-000000000001"),
        organization_id=UUID("00000000-0000-4000-8000-000000000002"),
        merchant_id=UUID("00000000-0000-4000-8000-000000000003"),
        shop_id=UUID("00000000-0000-4000-8000-000000000004"),
        shop_domain="safe-shop.myshopify.com",
        encrypted_access_token="encrypted",
        encrypted_refresh_token=None,
        scopes=config.scopes,
        api_version=config.api_version,
        access_token_expires_at=None,
        refresh_token_expires_at=None,
        status="CONNECTED",
        installed_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    class OAuth:
        calls = 0

        def __init__(self, *args: Any) -> None:
            del args

        def complete(self, parameters: dict[str, str]) -> Installation:
            del parameters
            self.calls += 1
            if self.calls > 1:
                raise ValueError("nonce already consumed")
            return installation

    class Product:
        calls = 0

        def initial_sync(self, settings: ShopifySettings, value: Installation) -> None:
            assert settings is config and value is installation
            self.calls += 1
            # The service has already persisted FAILED; this worker exception must not escape
            # through Starlette's background-task execution into the successful queue response.
            raise RuntimeError("Shopify orders bulk operation REJECTED: INVALID_QUERY")

    monkeypatch.setattr(api_module, "ShopifyOAuthService", OAuth)
    product = Product()
    app = FastAPI()
    app.include_router(
        build_shopify_router(
            config,
            repository,
            ShopifyWebhookService(
                config.client_secret, repository, RecordingPrivacyProcessor()
            ),
            _verifier(private_key),
            MemoryTenantProvisioner(TenantIdDeriver("t" * 40)),
            product,  # type: ignore[arg-type]
            agreement_gate=MemoryAgreementGate(),
        )
    )
    client = TestClient(app)
    first = client.get("/api/v1/shopify/oauth/callback?code=one", follow_redirects=False)
    second = client.get("/api/v1/shopify/oauth/callback?code=one", follow_redirects=False)
    assert first.headers["location"] == (
        f"{PARTY}/onboarding?shopify=connected&shop=safe-shop.myshopify.com"
    )
    assert "shopify=error" in second.headers["location"]
    assert product.calls == 1


def test_retry_sync_uses_existing_authenticated_connection_without_oauth(
    private_key: Any,
) -> None:
    config = _settings()
    repository = MemoryShopifyRepository()
    tenants = MemoryTenantProvisioner(TenantIdDeriver("t" * 40))
    principal = tenants.resolve(VerifiedIdentity(ISSUER, "user_merchant_one"))
    installation = Installation(
        id=UUID("00000000-0000-4000-8000-000000000011"),
        organization_id=principal.organization_id,
        merchant_id=principal.merchant_id,
        shop_id=UUID("00000000-0000-4000-8000-000000000012"),
        shop_domain="safe-shop.myshopify.com",
        encrypted_access_token="encrypted",
        encrypted_refresh_token=None,
        scopes=config.scopes,
        api_version=config.api_version,
        access_token_expires_at=None,
        refresh_token_expires_at=None,
        status="CONNECTED",
        installed_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository.installations[(principal.merchant_id, installation.shop_domain)] = installation

    class Product:
        calls = 0

        def initial_sync(self, settings: ShopifySettings, value: Installation) -> None:
            assert settings is config and value is installation
            self.calls += 1

    product = Product()
    app = FastAPI()
    app.include_router(
        build_shopify_router(
            config,
            repository,
            ShopifyWebhookService(
                config.client_secret, repository, RecordingPrivacyProcessor()
            ),
            _verifier(private_key),
            tenants,
            product,  # type: ignore[arg-type]
            agreement_gate=MemoryAgreementGate(),
        )
    )
    client = TestClient(app)
    missing = client.post("/api/v1/shopify/sync?shop=safe-shop.myshopify.com")
    response = client.post(
        "/api/v1/shopify/sync?shop=safe-shop.myshopify.com",
        headers={"Authorization": f"Bearer {_token(private_key)}"},
    )

    assert missing.status_code == 401
    assert response.json() == {"status": "QUEUED", "mode": "READ_ONLY"}
    assert product.calls == 1
    assert repository.nonces == {}
