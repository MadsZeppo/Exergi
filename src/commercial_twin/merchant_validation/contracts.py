"""Immutable product contracts for Merchant Validation V1."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class EvidenceLabel(StrEnum):
    OBSERVED = "OBSERVED"
    DESCRIPTIVE = "DESCRIPTIVE"
    PREDICTED = "PREDICTED"
    RANDOMIZED_CAUSAL = "RANDOMIZED_CAUSAL"
    OBSERVATIONAL_CAUSAL = "OBSERVATIONAL_CAUSAL"
    EXPERIMENTAL = "EXPERIMENTAL"
    ECONOMIC = "ECONOMIC"
    SIMULATED_ONLY = "SIMULATED_ONLY"
    INSUFFICIENT = "INSUFFICIENT"


class CheckStatus(StrEnum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class ActionRecommendation(StrEnum):
    DO_THIS = "DO_THIS"
    TEST_THIS = "TEST_THIS"
    AVOID = "AVOID"
    NOT_ENOUGH_EVIDENCE = "NOT_ENOUGH_EVIDENCE"


class DataHealthCheck(FrozenModel):
    name: str
    capability: str
    status: CheckStatus
    observed: float | int | str | None = None
    expected: float | int | str | None = None
    tolerance: float | None = None
    detail: dict[str, Any] = {}


class CapabilityMatrix(FrozenModel):
    observed_customer_state: str
    purchase_prediction: str
    opportunity_discovery: str
    causal_historical_action_response: str
    experiment_design: str
    incremental_profit_measurement: str
    do_this_by_action_type: dict[str, bool]
    test_this: str = "ENABLED"


class DataHealthReport(FrozenModel):
    organization_id: UUID
    merchant_id: UUID
    as_of: datetime
    checks: tuple[DataHealthCheck, ...]
    descriptive_ready: bool
    prediction_ready: bool
    behavioral_state_ready: bool
    experiment_ready: bool
    causal_history_ready: bool
    economics_ready: bool


class ObservedCustomerState(FrozenModel):
    tenure_days: int = Field(ge=0)
    last_activity_at: datetime | None
    last_purchase_at: datetime | None
    purchase_count: int = Field(ge=0)
    order_count: int = Field(ge=0)
    net_historical_value: float
    average_order_value: float
    category_affinity: dict[str, float]
    product_affinity: dict[str, float]
    browsing_recency_days: float | None = Field(default=None, ge=0)
    cart_recency_days: float | None = Field(default=None, ge=0)
    cart_frequency: int = Field(ge=0)
    recent_intent: float = Field(ge=0, le=1)
    purchase_cadence_days: float | None = Field(default=None, ge=0)
    promotion_exposure_count: int = Field(ge=0)
    refund_rate: float = Field(ge=0, le=1)
    lifecycle: str
    history_support: str


class PredictiveQuantity(FrozenModel):
    name: str
    point: float | None
    lower: float | None = None
    upper: float | None = None
    model_version: str
    calibration_status: str
    empirical_reliability: str
    support: str
    as_of: datetime


class MerchantCustomerTwin(FrozenModel):
    organization_id: UUID
    merchant_id: UUID
    customer_id: UUID
    as_of: datetime
    observed: ObservedCustomerState
    predictive: tuple[PredictiveQuantity, ...]
    state_hash: str


class PopulationState(FrozenModel):
    merchant_id: UUID
    as_of: datetime
    active_customers: int
    repeat_buyers: int
    new_customers: int
    cooling_customers: int
    dormant_customers: int
    high_intent_customers: int
    repeat_rate: float
    view_to_cart_rate: float
    cart_to_purchase_rate: float
    refund_rate: float
    contribution_profit: float | None


class Opportunity(FrozenModel):
    id: UUID
    merchant_id: UUID
    opportunity_type: str
    title: str
    affected_population: dict[str, Any]
    current_metric: float
    baseline_metric: float
    absolute_difference: float
    relative_difference: float
    interval: tuple[float, float]
    persistence_periods: int
    addressable_value: float | None
    evidence: EvidenceLabel
    materiality: str
    actionability: str
    causal_evidence: str


class ActionCandidate(FrozenModel):
    action_type: str
    parameters: dict[str, Any]
    evidence: EvidenceLabel
    recommendation: ActionRecommendation
    reason: str
    support: str
    expected_incremental_value: float | None = None


class ExperimentArm(FrozenModel):
    id: UUID
    name: str
    action_type: str
    parameters: dict[str, Any]
    allocation_probability: float = Field(gt=0, le=1)
    is_control: bool = False


class ExperimentSpec(FrozenModel):
    id: UUID
    merchant_id: UUID
    opportunity_id: UUID | None
    name: str
    eligibility_customer_ids: tuple[UUID, ...]
    primary_outcome: str
    outcome_window_days: int = Field(gt=0)
    randomization_unit: str = "customer"
    randomization_seed: str
    arms: tuple[ExperimentArm, ...]
    alpha: float = Field(gt=0, lt=1)
    power: float = Field(gt=0, lt=1)
    frozen_at: datetime | None = None
    spec_hash: str | None = None

    @model_validator(mode="after")
    def validate_allocations(self) -> ExperimentSpec:
        if len(self.arms) < 2:
            raise ValueError("an experiment requires at least two arms")
        if abs(sum(a.allocation_probability for a in self.arms) - 1.0) > 1e-9:
            raise ValueError("arm probabilities must sum to one")
        if len(set(self.eligibility_customer_ids)) != len(self.eligibility_customer_ids):
            raise ValueError("eligibility customers must be unique")
        return self


class Assignment(FrozenModel):
    experiment_id: UUID
    merchant_id: UUID
    customer_id: UUID
    arm_id: UUID
    assigned_at: datetime
    assignment_probability: float = Field(gt=0, le=1)
    assignment_hash: str


class ExperimentOutcome(FrozenModel):
    experiment_id: UUID
    merchant_id: UUID
    customer_id: UUID
    purchase: int = Field(ge=0, le=1)
    order_count: int = Field(ge=0)
    gross_item_sales: float
    line_discounts: float
    refunds: float
    shipping_revenue: float
    cogs: float | None
    merchant_shipping_cost: float | None
    campaign_variable_cost: float | None
    payment_processing_cost: float | None
    contribution_profit: float | None


class ExperimentResult(FrozenModel):
    experiment_id: UUID
    estimator: str
    control_arm_id: UUID
    treatment_arm_id: UUID
    sample_control: int
    sample_treatment: int
    effect_per_customer: float
    standard_error: float
    confidence_interval: tuple[float, float]
    total_incremental_effect: float
    evidence: EvidenceLabel
    economics_status: str


class DecisionCard(FrozenModel):
    opportunity: Opportunity
    what_is_happening: str
    why_it_matters: str
    addressable_value_label: str
    candidate_actions: tuple[ActionCandidate, ...]
    recommendation: ActionRecommendation
    recommendation_reason: str
    data_quality: str
    experiment_plan: ExperimentSpec | None = None


class MerchantLearningRecord(FrozenModel):
    merchant_id: UUID
    experiment_id: UUID
    pre_action_state: dict[str, Any]
    action_definition: dict[str, Any]
    outcome_definition: dict[str, Any]
    estimated_effect: dict[str, Any]
    uncertainty: dict[str, Any]
    economics: dict[str, Any]
    evidence: EvidenceLabel
    recorded_at: datetime
