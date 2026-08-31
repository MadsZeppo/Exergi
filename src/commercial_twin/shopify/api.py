"""Authenticated FastAPI router for the read-only Shopify product slice."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from .auth import MerchantPrincipal
from .config import ShopifySettings
from .identity import ClerkJWTVerifier
from .oauth import ShopifyOAuthService
from .product_service import SqlShopifyProductService
from .repository import ShopifyRepository
from .security import canonicalize_shop_domain
from .tenancy import TenantResolver
from .webhooks import ShopifyWebhookService


class ConnectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shop: str = Field(min_length=3, max_length=255)


class EconomicAssumptionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shop: str
    version: str = Field(min_length=1, max_length=80)
    valid_from: datetime
    payment_fee_rate: float | None = Field(default=None, ge=0, le=1)
    payment_fixed_fee: float | None = Field(default=None, ge=0)
    shipping_cost_per_order: float | None = Field(default=None, ge=0)
    fulfillment_cost_per_order: float | None = Field(default=None, ge=0)
    action_cost_per_order: float | None = Field(default=None, ge=0)


class BearerMerchantAuthenticator:
    """Resolve a merchant only after verifying a Clerk bearer token."""

    def __init__(self, verifier: ClerkJWTVerifier, tenants: TenantResolver) -> None:
        self.verifier = verifier
        self.tenants = tenants

    def __call__(  # noqa: B008
        self, authorization: str | None = Header(default=None, alias="Authorization")
    ) -> MerchantPrincipal:
        if authorization is None or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="valid Clerk bearer token required")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            verified = self.verifier.verify(token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="invalid authentication token") from exc
        try:
            return self.tenants.resolve(verified)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="invalid authentication identity") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=403, detail="tenant access denied") from exc


def build_shopify_router(
    settings: ShopifySettings,
    repository: ShopifyRepository,
    webhook_service: ShopifyWebhookService,
    verifier: ClerkJWTVerifier,
    tenants: TenantResolver,
    product_service: SqlShopifyProductService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/shopify", tags=["shopify-read-only"])
    oauth = ShopifyOAuthService(settings, repository)
    authenticate = BearerMerchantAuthenticator(verifier, tenants)

    @router.post("/connect")
    def connect(
        payload: ConnectInput,
        identity: MerchantPrincipal = Depends(authenticate),  # noqa: B008
    ) -> Any:
        try:
            start = oauth.begin(identity.organization_id, identity.merchant_id, payload.shop)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return asdict(start)

    @router.get("/install")
    def install(
        shop: str,
    ) -> RedirectResponse:
        try:
            canonical_shop = canonicalize_shop_domain(shop)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        query = urlencode({"shop": canonical_shop})
        return RedirectResponse(f"{settings.dashboard_url}/onboarding?{query}", status_code=303)

    @router.get("/oauth/callback")
    def callback(request: Request, background_tasks: BackgroundTasks) -> RedirectResponse:
        parameters = {key: value for key, value in request.query_params.items()}
        try:
            installation = oauth.complete(parameters)
        except (PermissionError, ValueError, RuntimeError):
            query = urlencode({"shopify": "error", "reason": "OAuth verification failed"})
            return RedirectResponse(f"{settings.dashboard_url}/onboarding?{query}", status_code=303)
        if product_service is not None:
            background_tasks.add_task(product_service.initial_sync, settings, installation)
        query = urlencode({"shopify": "connected", "shop": installation.shop_domain})
        return RedirectResponse(f"{settings.dashboard_url}/onboarding?{query}", status_code=303)

    @router.get("/connection")
    def connection(
        shop: str,
        identity: MerchantPrincipal = Depends(authenticate),  # noqa: B008
    ) -> dict[str, Any]:
        shop = _canonical_shop(shop)
        installation = repository.get_installation(identity.merchant_id, shop)
        if installation is None:
            return {"status": "NOT_CONNECTED", "shop": shop}
        return {
            "status": installation.status,
            "shop": installation.shop_domain,
            "api_version": installation.api_version,
            "scopes": installation.scopes,
            "access_token_expires_at": installation.access_token_expires_at,
            "history": (
                "ALL_APPROVED_ORDERS"
                if "read_all_orders" in installation.scopes
                else "SHOPIFY_DEFAULT_ORDER_WINDOW"
            ),
        }

    @router.delete("/connection")
    def disconnect(
        shop: str,
        identity: MerchantPrincipal = Depends(authenticate),  # noqa: B008
    ) -> dict[str, str]:
        shop = _canonical_shop(shop)
        oauth.disconnect(identity.merchant_id, shop, identity.subject)
        return {"status": "DISCONNECTED"}

    @router.post("/sync")
    def start_sync(
        shop: str,
        background_tasks: BackgroundTasks,
        identity: MerchantPrincipal = Depends(authenticate),  # noqa: B008
    ) -> dict[str, str]:
        if product_service is None:
            raise HTTPException(status_code=503, detail="persistent sync service is unavailable")
        shop = _canonical_shop(shop)
        installation = repository.get_installation(identity.merchant_id, shop)
        if installation is None or installation.status != "CONNECTED":
            raise HTTPException(status_code=409, detail="Shopify is not connected")
        if (
            installation.access_token_expires_at is not None
            and installation.access_token_expires_at <= datetime.now(UTC) + timedelta(minutes=5)
        ):
            try:
                installation = oauth.refresh(installation)
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=401, detail="Shopify reauthorization required"
                ) from exc
        background_tasks.add_task(product_service.initial_sync, settings, installation)
        repository.audit(
            identity.merchant_id,
            "SHOPIFY_INITIAL_SYNC_QUEUED",
            identity.subject,
            {"shop": installation.shop_domain},
        )
        return {"status": "QUEUED", "mode": "READ_ONLY"}

    @router.get("/dashboard")
    def dashboard(
        shop: str,
        identity: MerchantPrincipal = Depends(authenticate),  # noqa: B008
    ) -> Any:
        if product_service is None:
            raise HTTPException(status_code=503, detail="persistent read service is unavailable")
        return product_service.dashboard(identity.merchant_id, _canonical_shop(shop))

    @router.post("/economic-assumptions")
    def economic_assumptions(
        payload: EconomicAssumptionsInput,
        identity: MerchantPrincipal = Depends(authenticate),  # noqa: B008
    ) -> dict[str, str]:
        if product_service is None:
            raise HTTPException(status_code=503, detail="persistent read service is unavailable")
        shop = _canonical_shop(payload.shop)
        installation = repository.get_installation(identity.merchant_id, shop)
        if installation is None:
            raise HTTPException(status_code=404, detail="Shopify connection not found")
        values = payload.model_dump(exclude={"shop", "version", "valid_from"}, exclude_none=False)
        try:
            product_service.save_assumptions(
                identity.merchant_id,
                installation.shop_id,
                version=payload.version,
                valid_from=payload.valid_from,
                assumptions=values,
                actor=identity.subject,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"status": "SAVED", "version": payload.version}

    @router.post("/webhooks")
    async def webhook(request: Request) -> dict[str, Any]:
        body = await request.body()
        try:
            result = webhook_service.handle(body, request.headers)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return asdict(result)

    @router.get("/capabilities")
    def capabilities(
        identity: MerchantPrincipal = Depends(authenticate),  # noqa: B008
    ) -> dict[str, Any]:
        del identity
        return {
            "mode": "READ_ONLY",
            "api_version": settings.api_version,
            "requested_scopes": settings.scopes,
            "write_scopes": [],
            "autonomous_actions": False,
            "causal_claims_from_shopify_history": False,
            "read_all_orders_feature_gate": settings.enable_read_all_orders,
            "shopify_payments_feature_gate": settings.enable_shopify_payments,
        }

    return router


def _canonical_shop(value: str) -> str:
    try:
        return canonicalize_shop_domain(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
