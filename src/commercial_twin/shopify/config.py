"""Fail-closed runtime configuration for the Shopify integration."""

from __future__ import annotations

import os
from dataclasses import dataclass

API_VERSION = "2026-07"
BASE_READ_SCOPES = (
    "read_customers",
    "read_inventory",
    "read_orders",
    "read_products",
    "read_returns",
)
OPTIONAL_READ_ALL_ORDERS = "read_all_orders"
OPTIONAL_PAYMENTS_SCOPE = "read_shopify_payments_payouts"


@dataclass(frozen=True)
class ShopifySettings:
    client_id: str
    client_secret: str
    app_base_url: str
    dashboard_url: str
    token_encryption_key: str
    oauth_state_key: str
    customer_pseudonym_key: str
    session_signing_key: str
    database_url: str
    api_version: str = API_VERSION
    enable_read_all_orders: bool = False
    enable_shopify_payments: bool = False
    production: bool = True

    @property
    def scopes(self) -> tuple[str, ...]:
        scopes = list(BASE_READ_SCOPES)
        if self.enable_read_all_orders:
            scopes.append(OPTIONAL_READ_ALL_ORDERS)
        if self.enable_shopify_payments:
            scopes.append(OPTIONAL_PAYMENTS_SCOPE)
        answer = tuple(sorted(scopes))
        if any(scope.startswith("write_") for scope in answer):
            raise ValueError("Shopify write scopes are forbidden")
        return answer

    @property
    def oauth_callback_url(self) -> str:
        return f"{self.app_base_url.rstrip('/')}/api/v1/shopify/oauth/callback"

    @classmethod
    def from_env(cls) -> ShopifySettings:
        required = {
            "client_id": "SHOPIFY_CLIENT_ID",
            "client_secret": "SHOPIFY_CLIENT_SECRET",
            "dashboard_url": "EXERGI_DASHBOARD_URL",
            "token_encryption_key": "SHOPIFY_TOKEN_ENCRYPTION_KEY",
            "oauth_state_key": "SHOPIFY_OAUTH_STATE_KEY",
            "customer_pseudonym_key": "CUSTOMER_PSEUDONYM_KEY",
            "session_signing_key": "EXERGI_SESSION_SIGNING_KEY",
            "database_url": "DATABASE_URL",
        }
        values: dict[str, str] = {}
        missing: list[str] = []
        for field, environment_name in required.items():
            value = os.environ.get(environment_name, "").strip()
            if not value:
                missing.append(environment_name)
            values[field] = value
        app_base_url = os.environ.get("EXERGI_API_BASE_URL", "").strip()
        render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
        if not app_base_url and render_hostname:
            app_base_url = f"https://{render_hostname}"
        if not app_base_url:
            missing.append("EXERGI_API_BASE_URL")
        values["app_base_url"] = app_base_url
        if missing:
            raise RuntimeError(f"missing required runtime secrets: {', '.join(sorted(missing))}")
        environment = os.environ.get("EXERGI_ENVIRONMENT", "production").lower()
        return cls(
            **values,
            enable_read_all_orders=_boolean("SHOPIFY_ENABLE_READ_ALL_ORDERS"),
            enable_shopify_payments=_boolean("SHOPIFY_ENABLE_PAYMENTS_DATA"),
            production=environment == "production",
        )


def _boolean(name: str) -> bool:
    return os.environ.get(name, "false").strip().lower() in {"1", "true", "yes"}
