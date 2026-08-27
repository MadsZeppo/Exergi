from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FieldStatus(StrEnum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class CustomerEvent(BaseModel):
    """Canonical, pseudonymous commerce event with field-level provenance."""

    model_config = ConfigDict(frozen=True)
    event_time: datetime
    customer_id: str
    event_type: str
    product_id: str
    session_id: str | None = None
    category_id: str | None = None
    brand: str | None = None
    price: float | None = Field(default=None, ge=0)
    quantity: float | None = Field(default=None, gt=0)
    discount: float | None = Field(default=None, ge=0, le=1)
    order_id: str | None = None
    channel: str | None = None
    return_flag: bool | None = None
    geography: str | None = None
    field_status: dict[str, FieldStatus]

    @field_validator("event_time")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("event_time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def provenance_is_complete(self) -> CustomerEvent:
        missing = set(type(self).model_fields) - {"field_status"} - set(self.field_status)
        if missing:
            raise ValueError(f"field_status missing canonical fields: {sorted(missing)}")
        return self


class LifecycleStage(StrEnum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    COOLING = "COOLING"
    DORMANT = "DORMANT"


class CustomerStateSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    customer_id: str
    as_of: datetime
    first_seen: datetime
    last_view_days: float | None = Field(default=None, ge=0)
    last_cart_days: float | None = Field(default=None, ge=0)
    last_purchase_days: float | None = Field(default=None, ge=0)
    views_7d: float = Field(ge=0)
    views_30d: float = Field(ge=0)
    views_90d: float = Field(ge=0)
    carts_7d: float = Field(ge=0)
    carts_30d: float = Field(ge=0)
    carts_90d: float = Field(ge=0)
    purchases_30d: float = Field(ge=0)
    purchases_90d: float = Field(ge=0)
    purchases_180d: float = Field(ge=0)
    spend_30d: float = Field(ge=0)
    spend_90d: float = Field(ge=0)
    spend_180d: float = Field(ge=0)
    aov: float = Field(ge=0)
    median_item_price: float = Field(ge=0)
    category_affinity: dict[str, float] = Field(default_factory=dict)
    brand_affinity: dict[str, float] = Field(default_factory=dict)
    product_repeat_rate: float = Field(ge=0, le=1)
    view_to_cart: float = Field(ge=0, le=1)
    cart_to_purchase: float = Field(ge=0, le=1)
    abandonment_rate: float = Field(ge=0, le=1)
    purchase_frequency_change: float
    spend_change: float
    lifecycle: LifecycleStage
    observation_count: int = Field(ge=1)
    effective_history_days: float = Field(ge=0)
    reliability: float = Field(ge=0, le=1)
    shrinkage_strength: float = Field(ge=0, le=1)
    effective_sample_size: float = Field(ge=0)
    cohort_id: str | None = None

    @field_validator("as_of", "first_seen")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("snapshot timestamps must be timezone-aware")
        return value


class BehavioralCohort(BaseModel):
    model_config = ConfigDict(frozen=True)
    cohort_id: str
    size: int = Field(ge=1)
    centroid: tuple[float, ...]
    statistics: dict[str, float]
    stability: float = Field(ge=0, le=1)
    transition_rate: float | None = Field(default=None, ge=0, le=1)
    description: str


class RelationshipType(StrEnum):
    CAUSAL = "CAUSAL"
    PREDICTIVE = "PREDICTIVE"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    UNKNOWN = "UNKNOWN"


class DriverEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    driver_name: str
    driver_value: float | str | bool
    relationship_type: RelationshipType
    effect_direction: str
    estimated_magnitude: float | None = None
    uncertainty: dict[str, float] = Field(default_factory=dict)
    validation_scope: str
    support: str
    explanation_allowed: bool = False

    def safe_explanation(self) -> str:
        if not self.explanation_allowed:
            return "Insufficient evidence for a customer-facing driver explanation."
        if self.relationship_type == RelationshipType.CAUSAL:
            return (
                f"Because {self.driver_name} changed, we estimate a "
                f"{self.effect_direction} response."
            )
        if self.relationship_type == RelationshipType.PREDICTIVE:
            return (
                f"Under current {self.driver_name} conditions, customers with this profile "
                f"have historically shown a {self.effect_direction} outcome."
            )
        if self.relationship_type == RelationshipType.CONTEXT_ONLY:
            return f"Current {self.driver_name} is included as model context."
        return "The relationship is unknown and is not interpreted."


class CustomerPopulationSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    as_of: datetime
    active_customers: int = Field(ge=0)
    behavioral_cohorts: tuple[BehavioralCohort, ...]
    purchase_rate: float = Field(ge=0, le=1)
    aov: float = Field(ge=0)
    category_mix: dict[str, float]
    customer_state_distribution: dict[str, float]
    recent_behavior_shifts: dict[str, float]
    state_support: dict[str, float | str]
    world_context: str = "NOT_AVAILABLE_FOR_VALIDATION"
    world_effect_validated: bool = False
    model_versions: dict[str, str] = Field(default_factory=dict)


class PopulationFidelityReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    purchase_calibration: float
    buyer_count_relative_error: float
    order_error: float
    revenue_relative_error: float
    aov_distribution_error: float
    category_mix_divergence: float
    cohort_calibration: float
    temporal_stability: float
    verdict: str
    raw_metrics: dict[str, Any]


class CustomerTwinReadinessReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    history_days: int
    active_customers: int
    repeat_customers: int
    event_coverage: dict[str, int]
    transaction_coverage: float
    category_coverage: float
    sparsity: float
    model_calibration: float | None = None
    population_fidelity_status: str = "NOT_EVALUATED"
    reasons: tuple[str, ...] = ()


class PopulationComparison(BaseModel):
    model_config = ConfigDict(frozen=True)
    earlier_as_of: datetime
    later_as_of: datetime
    active_customer_change: int
    purchase_rate_change: float
    aov_change: float
    lifecycle_distribution_change: dict[str, float]
    category_mix_change: dict[str, float]
    causal_interpretation_allowed: bool = False
