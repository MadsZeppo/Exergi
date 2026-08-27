"""Canonical, source-honest commerce and integration contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CommerceModel(BaseModel):
    model_config = ConfigDict(frozen=True)
    observed_fields: frozenset[str] = frozenset()
    derived_fields: frozenset[str] = frozenset()

    @model_validator(mode="after")
    def provenance_sets_are_disjoint(self) -> CommerceModel:
        overlap = self.observed_fields & self.derived_fields
        if overlap:
            raise ValueError(f"observed_fields and derived_fields overlap: {sorted(overlap)}")
        return self


class Customer(CommerceModel):
    customer_id: str
    country: str | None = None


class Product(CommerceModel):
    product_id: str
    description: str | None = None
    category_id: str | None = None


class OrderLine(CommerceModel):
    order_id: str
    product_id: str
    quantity: float
    unit_price: float
    gross_value: float


class Order(CommerceModel):
    order_id: str
    customer_id: str
    order_time: datetime
    country: str | None = None
    gross_value: float = Field(ge=0)
    lines: tuple[OrderLine, ...] = ()


class Cancellation(CommerceModel):
    cancellation_id: str
    event_time: datetime
    customer_id: str | None = None
    product_id: str | None = None
    quantity: float
    value: float
    original_order_id: str | None = None


class Refund(CommerceModel):
    refund_id: str
    order_id: str | None = None
    event_time: datetime
    value: float = Field(ge=0)


class CustomerEvent(CommerceModel):
    event_id: str
    event_time: datetime
    customer_id: str | None = None
    event_type: str
    order_id: str | None = None
    product_id: str | None = None
    category_id: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    gross_value: float | None = None
    discount_value: float | None = None
    refund_value: float | None = None
    channel: str | None = None
    campaign_id: str | None = None
    action_id: str | None = None
    treatment: bool | None = None
    propensity: float | None = Field(default=None, gt=0, le=1)
    country: str | None = None
    source: str


class MarketingExposure(CommerceModel):
    exposure_id: str
    customer_id: str
    event_time: datetime
    channel: str
    campaign_id: str | None = None
    assigned_treatment: bool | None = None
    engagement_type: str | None = None


class ActionExposure(CommerceModel):
    exposure_id: str
    action_id: str
    customer_id: str
    assigned_at: datetime
    treatment: bool
    propensity: float | None = Field(default=None, gt=0, le=1)
    outcome_window_days: int = Field(gt=0)


class DataReadinessLevel(StrEnum):
    TRANSACTION_ONLY = "TRANSACTION_ONLY"
    FULL_BEHAVIORAL = "FULL_BEHAVIORAL"


class ShopifyTwinAdapter:
    """Pure mapping contract; no OAuth or network access."""

    historical_order_access_required = True

    @staticmethod
    def map_standard_event(event_name: str) -> str:
        allowed = {
            "page_viewed",
            "product_viewed",
            "product_added_to_cart",
            "product_removed_from_cart",
            "cart_viewed",
            "checkout_started",
            "checkout_completed",
            "search_submitted",
            "collection_viewed",
        }
        if event_name not in allowed:
            raise ValueError(f"unsupported Shopify standard event: {event_name}")
        return event_name.upper()


class KlaviyoTwinAdapter:
    """Separates campaign assignment from engagement such as an email open."""

    @staticmethod
    def map_event(metric_name: str, *, assigned_treatment: bool | None) -> dict[str, object]:
        engagement = metric_name in {"Opened Email", "Clicked Email", "Clicked SMS"}
        return {
            "event_type": metric_name.upper().replace(" ", "_"),
            "engagement": engagement,
            "assigned_treatment": assigned_treatment,
            "causal_exposure": assigned_treatment is not None,
        }
