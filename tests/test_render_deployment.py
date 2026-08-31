from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from commercial_twin.merchant_validation.api import create_app
from commercial_twin.shopify.config import ShopifySettings

ROOT = Path(__file__).resolve().parents[1]


def test_render_hostname_is_used_without_hardcoded_api_domain(monkeypatch: Any) -> None:
    required = {
        "SHOPIFY_CLIENT_ID": "client-id",
        "SHOPIFY_CLIENT_SECRET": "client-secret",
        "EXERGI_DASHBOARD_URL": "https://dashboard.example",
        "SHOPIFY_TOKEN_ENCRYPTION_KEY": "token-key",
        "SHOPIFY_OAUTH_STATE_KEY": "state-key",
        "CUSTOMER_PSEUDONYM_KEY": "pseudonym-key",
        "DATABASE_URL": "postgresql+psycopg://db/exergi",
        "RENDER_EXTERNAL_HOSTNAME": "exergi-api.onrender.com",
    }
    monkeypatch.delenv("EXERGI_API_BASE_URL", raising=False)
    for key, value in required.items():
        monkeypatch.setenv(key, value)

    settings = ShopifySettings.from_env()

    assert settings.app_base_url == "https://exergi-api.onrender.com"
    assert settings.oauth_callback_url == (
        "https://exergi-api.onrender.com/api/v1/shopify/oauth/callback"
    )


def test_render_blueprint_has_no_secret_values_and_uses_private_database() -> None:
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    service = blueprint["services"][0]
    variables = {item["key"]: item for item in service["envVars"]}

    assert service["plan"] == "free"
    assert service["healthCheckPath"] == "/healthz"
    assert "preDeployCommand" not in service
    assert service["startCommand"].startswith(
        "uv run alembic upgrade head && exec uv run uvicorn "
    )
    assert variables["DATABASE_URL"]["fromDatabase"]["property"] == "connectionString"
    assert variables["PGSSLMODE"] == {"key": "PGSSLMODE", "value": "require"}
    for key in ("SHOPIFY_CLIENT_SECRET", "SHOPIFY_TOKEN_ENCRYPTION_KEY"):
        assert variables[key] == {"key": key, "sync": False}
    assert variables["TENANT_PROVISIONING_KEY"] == {
        "key": "TENANT_PROVISIONING_KEY",
        "generateValue": True,
    }
    for key in ("CLERK_ISSUER_URL", "CLERK_JWKS_URL", "CLERK_AUTHORIZED_PARTIES"):
        assert variables[key] == {"key": key, "sync": False}
    assert blueprint["databases"][0]["plan"] == "free"
    assert blueprint["databases"][0]["ipAllowList"] == []


def test_fastapi_exposes_render_health_check() -> None:
    app = create_app()
    route = next(route for route in app.routes if getattr(route, "path", None) == "/healthz")

    assert route.endpoint() == {"status": "ok"}
