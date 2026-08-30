"""FastAPI product surface for Merchant Validation V1."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .connectors import KlaviyoConnector, ShopifyConnector, validate_event_payload
from .service import MerchantValidationService, build_demo_service


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    merchant_id: UUID
    external_event_id: str = Field(min_length=1, max_length=200)
    customer_id: UUID | None = None
    session_id: str | None = Field(default=None, max_length=200)
    event_type: str
    occurred_at: datetime
    observed_at: datetime | None = None
    product_id: str | None = None
    properties: dict[str, Any] = {}
    schema_version: str = "1"


class ExperimentCreateInput(BaseModel):
    opportunity_id: UUID


def create_app(service: MerchantValidationService | None = None) -> FastAPI:
    product = service or build_demo_service()
    app = FastAPI(title="Verified Customer Twin — Merchant Validation V1", version="1.0.0")

    @app.get("/healthz", include_in_schema=False)
    def health() -> dict[str, str]:
        """Render liveness check; migration failure is handled by the pre-deploy command."""
        return {"status": "ok"}

    def authorize(merchant_id: UUID, supplied: str | None) -> None:
        if supplied is None or supplied != str(merchant_id):
            raise HTTPException(status_code=403, detail="merchant authentication failed")
        try:
            product._assert_tenant(merchant_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.get("/api/v1/merchants/{merchant_id}/data-health")
    def data_health(merchant_id: UUID, x_merchant_id: str | None = Header(default=None)) -> Any:
        authorize(merchant_id, x_merchant_id)
        return product.data_health(merchant_id, as_of=datetime.now(UTC))

    @app.post("/api/v1/connections/shopify")
    def shopify_status() -> Any:
        return ShopifyConnector.status()

    @app.post("/api/v1/connections/klaviyo")
    def klaviyo_status() -> Any:
        return KlaviyoConnector.status()

    @app.post("/api/v1/events")
    def event(payload: EventInput, x_merchant_id: str | None = Header(default=None)) -> Any:
        authorize(payload.merchant_id, x_merchant_id)
        raw = payload.model_dump()
        validate_event_payload(raw)
        raw["observed_at"] = raw["observed_at"] or raw["occurred_at"]
        return {"accepted": product.ingest_event(payload.merchant_id, raw)}

    @app.post("/api/v1/events/batch")
    def events(payload: list[EventInput], x_merchant_id: str | None = Header(default=None)) -> Any:
        if not payload or len(payload) > 1000:
            raise HTTPException(status_code=422, detail="batch size must be 1..1000")
        accepted = sum(event(item, x_merchant_id)["accepted"] for item in payload)
        return {"accepted": accepted, "duplicates": len(payload) - accepted}

    @app.get("/api/v1/customer-base")
    def customer_base(merchant_id: UUID, x_merchant_id: str | None = Header(default=None)) -> Any:
        authorize(merchant_id, x_merchant_id)
        return product.population_state(merchant_id, as_of=datetime.now(UTC))

    @app.get("/api/v1/customers/{customer_id}/twin")
    def customer_twin(
        customer_id: UUID, merchant_id: UUID, x_merchant_id: str | None = Header(default=None)
    ) -> Any:
        authorize(merchant_id, x_merchant_id)
        if customer_id not in product.twins:
            raise HTTPException(status_code=404, detail="customer twin not found")
        return product.twins[customer_id]

    @app.get("/api/v1/opportunities")
    def opportunities(merchant_id: UUID, x_merchant_id: str | None = Header(default=None)) -> Any:
        authorize(merchant_id, x_merchant_id)
        return tuple(
            item for item in product.opportunities.values() if item.merchant_id == merchant_id
        )

    @app.get("/api/v1/opportunities/{opportunity_id}")
    def opportunity(
        opportunity_id: UUID, merchant_id: UUID, x_merchant_id: str | None = Header(default=None)
    ) -> Any:
        authorize(merchant_id, x_merchant_id)
        return product.decision_card(merchant_id, opportunity_id)

    @app.post("/api/v1/experiments")
    def create_experiment(
        payload: ExperimentCreateInput,
        merchant_id: UUID,
        x_merchant_id: str | None = Header(default=None),
    ) -> Any:
        authorize(merchant_id, x_merchant_id)
        return product.create_experiment(merchant_id, payload.opportunity_id)

    @app.post("/api/v1/experiments/{experiment_id}/freeze")
    def freeze(
        experiment_id: UUID, merchant_id: UUID, x_merchant_id: str | None = Header(default=None)
    ) -> Any:
        authorize(merchant_id, x_merchant_id)
        return product.freeze_experiment(merchant_id, experiment_id, at=datetime.now(UTC))

    @app.post("/api/v1/experiments/{experiment_id}/assign")
    def assign(
        experiment_id: UUID, merchant_id: UUID, x_merchant_id: str | None = Header(default=None)
    ) -> Any:
        authorize(merchant_id, x_merchant_id)
        return product.assign(merchant_id, experiment_id, at=datetime.now(UTC))

    @app.get("/api/v1/experiments/{experiment_id}")
    def experiment(
        experiment_id: UUID, merchant_id: UUID, x_merchant_id: str | None = Header(default=None)
    ) -> Any:
        authorize(merchant_id, x_merchant_id)
        spec = product.experiments[experiment_id]
        if spec.merchant_id != merchant_id:
            raise HTTPException(status_code=403, detail="cross-merchant access rejected")
        return spec

    @app.post("/api/v1/experiments/{experiment_id}/analyze")
    def analyze(
        experiment_id: UUID, merchant_id: UUID, x_merchant_id: str | None = Header(default=None)
    ) -> Any:
        authorize(merchant_id, x_merchant_id)
        return product.analyze(merchant_id, experiment_id)

    @app.get("/api/v1/experiments/{experiment_id}/results")
    def results(
        experiment_id: UUID, merchant_id: UUID, x_merchant_id: str | None = Header(default=None)
    ) -> Any:
        authorize(merchant_id, x_merchant_id)
        return product.results.get(experiment_id, ())

    @app.get("/api/v1/ledger")
    def ledger(merchant_id: UUID, x_merchant_id: str | None = Header(default=None)) -> Any:
        authorize(merchant_id, x_merchant_id)
        return tuple(row for row in product.ledger if row["merchant_id"] == str(merchant_id))

    # The production Shopify router is enabled only when every required secret is present.
    # Missing configuration never falls back to fake credentials or a live-success claim.
    try:
        from commercial_twin.shopify.api import build_shopify_router
        from commercial_twin.shopify.config import ShopifySettings
        from commercial_twin.shopify.product_service import SqlShopifyProductService
        from commercial_twin.shopify.repository import SqlShopifyRepository
        from commercial_twin.shopify.webhooks import (
            ShopifyWebhookService,
            SqlPrivacyProcessor,
        )

        settings = ShopifySettings.from_env()
    except RuntimeError:
        settings = None
    if settings is not None:
        repository = SqlShopifyRepository.from_url(settings.database_url)
        privacy = SqlPrivacyProcessor(repository.engine)
        webhooks = ShopifyWebhookService(settings.client_secret, repository, privacy)
        product_service = SqlShopifyProductService(repository.engine, repository)
        app.include_router(
            build_shopify_router(settings, repository, webhooks, product_service)
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.dashboard_url.rstrip("/")],
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    app.state.merchant_service = product
    return app


app = create_app()
