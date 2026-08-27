from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CausalRole(StrEnum):
    PRE_TREATMENT = "PRE_TREATMENT"
    ACTION = "ACTION"
    MEDIATOR = "MEDIATOR"
    OUTCOME = "OUTCOME"
    UNKNOWN = "UNKNOWN"


class TemporalCausalMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)
    observed_at: datetime
    decided_at: datetime | None = None
    effective_at: datetime | None = None
    source: str
    causal_role: CausalRole = CausalRole.UNKNOWN

    @field_validator("observed_at", "decided_at", "effective_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class CustomerState(BaseModel):
    model_config = ConfigDict(frozen=True)
    cohort_id: str
    entity_count: int = Field(ge=1)
    recency_days: float = Field(ge=0)
    frequency: float = Field(ge=0)
    monetary_value: float = Field(ge=0)
    historical_aov: float = Field(ge=0)
    category_affinity: dict[str, float] = Field(default_factory=dict)
    purchase_frequency: float = Field(default=0, ge=0)
    promotion_response: float | None = None
    price_response: float | None = None
    return_rate: float | None = Field(default=None, ge=0, le=1)
    repeat_rate: float | None = Field(default=None, ge=0, le=1)
    acquisition_source: str | None = None
    geography: str | None = None
    customer_age_days: float = Field(default=0, ge=0)
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class ProductState(BaseModel):
    model_config = ConfigDict(frozen=True)
    product_id: str
    category_id: str
    current_price: float = Field(gt=0)
    unit_cost: float | None = Field(default=None, ge=0)
    inventory: float | None = Field(default=None, ge=0)


class CompanyState(BaseModel):
    model_config = ConfigDict(frozen=True)
    company_id: str
    products: tuple[ProductState, ...]
    active_promotions: tuple[str, ...] = ()
    marketing_activity: dict[str, float] = Field(default_factory=dict)
    channels: tuple[str, ...] = ()
    fulfillment: dict[str, Any] = Field(default_factory=dict)
    active_campaigns: tuple[str, ...] = ()
    offer_configuration: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class WorldSignal(BaseModel):
    model_config = ConfigDict(frozen=True)
    signal_name: str
    value: float | str | bool
    observed_at: datetime
    source: str
    geography: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance: dict[str, str] = Field(default_factory=dict)
    observation_period: datetime | None = None
    available_at: datetime | None = None
    retrieved_at: datetime | None = None
    series_id: str | None = None
    frequency: str | None = None
    requested_geography: str | None = None
    resolved_geography: str | None = None
    geography_level: str | None = None
    fallback_level: str | None = None
    fallback_reason: str | None = None
    vintage: str | None = None
    vintage_date: datetime | None = None
    signal_age_days: float | None = Field(default=None, ge=0)

    @field_validator(
        "observed_at", "observation_period", "available_at", "retrieved_at", "vintage_date"
    )
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class GeographicExposure(BaseModel):
    """A normalized customer, revenue, or order exposure across US geographies."""

    model_config = ConfigDict(frozen=True)
    geography: str
    weight: float = Field(gt=0, le=1)
    weight_type: str = "customer_share"

    @field_validator("weight_type")
    @classmethod
    def validate_weight_type(cls, value: str) -> str:
        allowed = {"customer_share", "revenue_share", "order_share"}
        if value not in allowed:
            raise ValueError(f"weight_type must be one of {sorted(allowed)}")
        return value


class WorldState(BaseModel):
    model_config = ConfigDict(frozen=True)
    signals: tuple[WorldSignal, ...]
    as_of: datetime
    requested_geography: str | None = None
    commerce_category: str | None = None
    unavailable_signals: tuple[str, ...] = ()
    geographic_exposure: tuple[GeographicExposure, ...] = ()
    geographic_contributions: dict[str, tuple[dict[str, Any], ...]] = Field(default_factory=dict)

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class CommercialState(BaseModel):
    model_config = ConfigDict(frozen=True)
    customer_states: tuple[CustomerState, ...]
    company_state: CompanyState
    world_state: WorldState
    as_of: datetime

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class CommercialAction(BaseModel):
    model_config = ConfigDict(frozen=True)
    action_id: str
    action_type: str
    scope: str
    start: datetime
    end: datetime
    constraints: dict[str, float] = Field(default_factory=dict)

    @field_validator("start", "end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_period(self) -> CommercialAction:
        if self.end < self.start:
            raise ValueError("action end cannot precede start")
        return self


class CommercialOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)
    outcome_name: str
    value: float
    observed_at: datetime
    action_id: str

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class CommercialTwinSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    twin_id: str
    state: CommercialState
    model_versions: dict[str, str]
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class TwinCalibrationRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    simulation_id: str
    twin_id: str
    action_id: str
    predicted: dict[str, float]
    actual: dict[str, float]
    errors: dict[str, float]
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class ReadinessStatus(StrEnum):
    READY = "READY"
    LIMITED = "LIMITED"
    NOT_READY = "NOT_READY"


class CapabilityReadiness(BaseModel):
    model_config = ConfigDict(frozen=True)
    capability: str
    status: ReadinessStatus
    components: dict[str, ReadinessStatus]
    reasons: tuple[str, ...] = ()


class TwinReadinessReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    twin_id: str
    capabilities: tuple[CapabilityReadiness, ...]
    generated_at: datetime

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value
