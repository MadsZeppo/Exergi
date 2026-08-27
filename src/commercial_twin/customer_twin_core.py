"""Typed, evidence-bound Customer Twin Core V1 contracts and pure engines."""

from __future__ import annotations

import hashlib
import itertools
import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.stats import chisquare


class EvidenceType(StrEnum):
    OBSERVED_IDENTITY = "OBSERVED_IDENTITY"
    DESCRIPTIVE_DECOMPOSITION = "DESCRIPTIVE_DECOMPOSITION"
    PREDICTIVE_ASSOCIATION = "PREDICTIVE_ASSOCIATION"
    CAUSAL_RCT = "CAUSAL_RCT"
    CAUSAL_OBSERVATIONAL = "CAUSAL_OBSERVATIONAL"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    INSUFFICIENT = "INSUFFICIENT"


class QueryClass(StrEnum):
    DESCRIPTIVE = "DESCRIPTIVE"
    CHANGE = "CHANGE"
    SEGMENT = "SEGMENT"
    PREDICTIVE = "PREDICTIVE"
    DRIVER = "DRIVER"
    CAUSAL = "CAUSAL"
    SCENARIO = "SCENARIO"
    DECISION = "DECISION"


class LivingCustomerState(BaseModel):
    model_config = ConfigDict(frozen=True)
    customer_id: str
    as_of: datetime
    country: str | None
    first_seen: datetime
    last_seen: datetime
    recency_days: float = Field(ge=0)
    frequency: int = Field(ge=0)
    monetary_value: float = Field(ge=0)
    orders_by_window: dict[int, int]
    revenue_by_window: dict[int, float]
    units_by_window: dict[int, float]
    aov: float = Field(ge=0)
    median_order_value: float = Field(ge=0)
    lifecycle: str
    interpurchase_days: float | None = Field(default=None, ge=0)
    repeat_rate: float = Field(ge=0, le=1)
    customer_age_days: float = Field(ge=0)
    cadence_change: float
    product_affinity: dict[str, float]
    product_diversity: int = Field(ge=0)
    product_entropy: float = Field(ge=0)
    cancellation_frequency: int = Field(ge=0)
    cancellation_value: float = Field(ge=0)
    recent_frequency_change: float
    recent_revenue_change: float
    recent_aov_change: float
    transaction_count: int = Field(ge=0)
    active_history_days: float = Field(ge=0)
    effective_sample_size: float = Field(ge=0)
    reliability: float = Field(ge=0, le=1)


class CustomerTwinSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    merchant_id: str
    as_of: datetime
    active_customers: int = Field(ge=0)
    new_customers: int = Field(ge=0)
    reactivated_customers: int = Field(ge=0)
    cooling_customers: int = Field(ge=0)
    dormant_customers: int = Field(ge=0)
    repeat_purchase_rate: float = Field(ge=0, le=1)
    purchase_frequency: float = Field(ge=0)
    aov: float = Field(ge=0)
    revenue: float = Field(ge=0)
    orders: int = Field(ge=0)
    cancellation_rate: float = Field(ge=0, le=1)
    value_distribution: dict[str, float]
    purchase_propensity_distribution: dict[str, float]
    lifecycle_distribution: dict[str, int]
    important_state_changes: tuple[dict[str, Any], ...]
    important_cohort_changes: tuple[dict[str, Any], ...]
    model_versions: dict[str, str]
    data_freshness: str
    data_readiness: dict[str, str]


class BehavioralCohortV1(BaseModel):
    model_config = ConfigDict(frozen=True)
    cohort_id: str
    size: int = Field(ge=0)
    statistics: dict[str, float]
    description: str
    month_to_month_stability: float = Field(ge=0, le=1)
    outcome_rate: float | None = Field(default=None, ge=0, le=1)


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    evidence_type: EvidenceType
    statement: str
    source: str
    support: dict[str, float | int | str] = {}
    uncertainty: dict[str, float] = {}
    limitations: tuple[str, ...] = ()


class TwinQuery(BaseModel):
    model_config = ConfigDict(frozen=True)
    query_id: str
    text: str
    as_of: datetime


class TwinQueryPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    query_id: str
    intent: QueryClass
    metric: str
    population: str = "ALL_CUSTOMERS"
    comparison_period: str | None = None
    forecast_horizon_days: int | None = Field(default=None, gt=0)
    action: str | None = None
    filters: dict[str, str] = {}
    required_evidence_level: EvidenceType
    world_context: str = "NOT_AVAILABLE_FOR_THIS_DATASET"


class TwinAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    query_id: str
    answer: str
    value: float | str | dict[str, Any] | list[Any] | None
    evidence_type: EvidenceType
    data_support: dict[str, float | int | str]
    uncertainty: dict[str, float]
    time_horizon: str
    calculation_used: str
    validation_status: str
    limitations: tuple[str, ...]
    evidence: tuple[EvidenceItem, ...]


class TwinQueryPlanner:
    """Deterministic allowlisted router. It never creates SQL."""

    _routes: tuple[tuple[tuple[str, ...], QueryClass, str, EvidenceType], ...] = (
        (("discount",), QueryClass.DECISION, "discount_action", EvidenceType.CAUSAL_OBSERVATIONAL),
        (("should", "offer"), QueryClass.DECISION, "offer_decision", EvidenceType.CAUSAL_RCT),
        (("what happens if",), QueryClass.SCENARIO, "action_scenario", EvidenceType.CAUSAL_RCT),
        (("cause", "campaign"), QueryClass.CAUSAL, "campaign_effect", EvidenceType.CAUSAL_RCT),
        (
            ("why", "revenue"),
            QueryClass.DRIVER,
            "revenue_decomposition",
            EvidenceType.DESCRIPTIVE_DECOMPOSITION,
        ),
        (
            ("revenue", "down"),
            QueryClass.DRIVER,
            "revenue_decomposition",
            EvidenceType.DESCRIPTIVE_DECOMPOSITION,
        ),
        (
            ("most likely", "buy"),
            QueryClass.PREDICTIVE,
            "purchase_probability",
            EvidenceType.PREDICTIVE_ASSOCIATION,
        ),
        (
            ("will", "cooling", "buy"),
            QueryClass.PREDICTIVE,
            "purchase_probability",
            EvidenceType.PREDICTIVE_ASSOCIATION,
        ),
        (
            ("least likely", "return"),
            QueryClass.PREDICTIVE,
            "purchase_probability",
            EvidenceType.PREDICTIVE_ASSOCIATION,
        ),
        (
            ("next 30",),
            QueryClass.PREDICTIVE,
            "thirty_day_forecast",
            EvidenceType.PREDICTIVE_ASSOCIATION,
        ),
        (
            ("cohort", "growing"),
            QueryClass.SEGMENT,
            "cohort_change",
            EvidenceType.OBSERVED_IDENTITY,
        ),
        (
            ("cohort", "shrinking"),
            QueryClass.SEGMENT,
            "cohort_change",
            EvidenceType.OBSERVED_IDENTITY,
        ),
        (
            ("cohort", "revenue"),
            QueryClass.SEGMENT,
            "cohort_revenue",
            EvidenceType.OBSERVED_IDENTITY,
        ),
        (("cooling",), QueryClass.SEGMENT, "lifecycle", EvidenceType.OBSERVED_IDENTITY),
        (("reactivating",), QueryClass.SEGMENT, "lifecycle", EvidenceType.OBSERVED_IDENTITY),
        (
            ("repeat purchase",),
            QueryClass.CHANGE,
            "repeat_purchase_rate",
            EvidenceType.OBSERVED_IDENTITY,
        ),
        (
            ("purchase frequency",),
            QueryClass.CHANGE,
            "purchase_frequency",
            EvidenceType.OBSERVED_IDENTITY,
        ),
        (("aov",), QueryClass.CHANGE, "aov", EvidenceType.OBSERVED_IDENTITY),
        (
            ("customer value",),
            QueryClass.CHANGE,
            "customer_value_distribution",
            EvidenceType.OBSERVED_IDENTITY,
        ),
        (("cancellation",), QueryClass.CHANGE, "cancellation_rate", EvidenceType.OBSERVED_IDENTITY),
        (("affinity",), QueryClass.CHANGE, "product_affinity", EvidenceType.OBSERVED_IDENTITY),
        (("migrat",), QueryClass.CHANGE, "product_migration", EvidenceType.OBSERVED_IDENTITY),
        (
            ("what is happening",),
            QueryClass.DESCRIPTIVE,
            "customer_snapshot",
            EvidenceType.OBSERVED_IDENTITY,
        ),
        (("what changed",), QueryClass.CHANGE, "customer_changes", EvidenceType.OBSERVED_IDENTITY),
        (
            ("deserve attention",),
            QueryClass.CHANGE,
            "attention_changes",
            EvidenceType.OBSERVED_IDENTITY,
        ),
    )

    def plan(self, query: TwinQuery) -> TwinQueryPlan:
        lowered = query.text.lower()
        for tokens, intent, metric, evidence in self._routes:
            if all(token in lowered for token in tokens):
                horizon = 30 if metric in {"purchase_probability", "thirty_day_forecast"} else None
                return TwinQueryPlan(
                    query_id=query.query_id,
                    intent=intent,
                    metric=metric,
                    forecast_horizon_days=horizon,
                    required_evidence_level=evidence,
                )
        return TwinQueryPlan(
            query_id=query.query_id,
            intent=QueryClass.DESCRIPTIVE,
            metric="unsupported",
            required_evidence_level=EvidenceType.INSUFFICIENT,
        )


class EvidenceBoundAnswerRenderer:
    _prefixes = {
        EvidenceType.OBSERVED_IDENTITY: "Observed data show that",
        EvidenceType.DESCRIPTIVE_DECOMPOSITION: "The accounting decomposition associates",
        EvidenceType.PREDICTIVE_ASSOCIATION: "Customers with this profile are predicted to",
        EvidenceType.CAUSAL_RCT: "The randomized evidence estimates that",
        EvidenceType.CAUSAL_OBSERVATIONAL: (
            "Under the stated identification assumptions, we estimate that"
        ),
        EvidenceType.CONTEXT_ONLY: "This is included as context:",
        EvidenceType.INSUFFICIENT: "We do not have enough evidence to answer this reliably.",
    }

    def render_statement(self, evidence_type: EvidenceType, statement: str) -> str:
        if evidence_type == EvidenceType.INSUFFICIENT:
            return self._prefixes[evidence_type]
        return f"{self._prefixes[evidence_type]} {statement}"


def revenue_shapley_decomposition(
    earlier: dict[str, float], later: dict[str, float]
) -> dict[str, float]:
    """Order-independent exact decomposition of B * F * A change."""
    keys = ("buyers", "orders_per_buyer", "revenue_per_order")
    if any(earlier[key] < 0 or later[key] < 0 for key in keys):
        raise ValueError("revenue identity factors must be non-negative")
    contributions = {key: 0.0 for key in keys}
    permutations = list(itertools.permutations(keys))
    for ordering in permutations:
        current = dict(earlier)
        for key in ordering:
            before = math.prod(current[item] for item in keys)
            current[key] = later[key]
            after = math.prod(current[item] for item in keys)
            contributions[key] += (after - before) / len(permutations)
    expected_change = math.prod(later[key] for key in keys) - math.prod(
        earlier[key] for key in keys
    )
    residual = expected_change - sum(contributions.values())
    contributions[keys[-1]] += residual
    return {**contributions, "total_change": expected_change, "residual": 0.0}


class ActionFamily(StrEnum):
    TARGETED_COMMUNICATION = "TARGETED_COMMUNICATION"
    OFFER = "OFFER"
    DISCOUNT_DEPTH = "DISCOUNT_DEPTH"
    NO_ACTION = "NO_ACTION"


class ActionDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    action_id: str
    family: ActionFamily
    parameters: dict[str, float | str | bool] = {}


class ActionSpace(BaseModel):
    model_config = ConfigDict(frozen=True)
    actions: tuple[ActionDefinition, ...]


class ActionEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    action: ActionDefinition
    evidence_type: EvidenceType
    identification: str
    support: str
    calibration: dict[str, float]
    historical_validation: str
    limitations: tuple[str, ...] = ()


def action_evidence_for_dataset(
    dataset: str,
    action: ActionDefinition,
    *,
    assignment_observed: bool,
    overlap_valid: bool,
    frozen_backtest_available: bool,
) -> ActionEvidence:
    """Fail-closed bridge from dataset support to the existing action contract."""
    normalized = dataset.lower().replace("_", " ")
    observational = "dunnhumby" in normalized
    supported = (
        observational and assignment_observed and overlap_valid and frozen_backtest_available
    )
    if supported:
        return ActionEvidence(
            action=action,
            evidence_type=EvidenceType.CAUSAL_OBSERVATIONAL,
            identification="OBSERVATIONAL_BACKDOOR_ADJUSTMENT",
            support="SUPPORTED_WITH_ASSUMPTIONS",
            calibration={},
            historical_validation="FROZEN_CHRONOLOGICAL_BACKTEST",
            limitations=(
                "Conditional ignorability on observed pre-exposure state is assumed, not proven.",
                "No transfer to another merchant is established.",
            ),
        )
    return ActionEvidence(
        action=action,
        evidence_type=EvidenceType.INSUFFICIENT,
        identification="NOT_IDENTIFIED",
        support="NOT_ENOUGH_EVIDENCE",
        calibration={},
        historical_validation="NOT_AVAILABLE",
        limitations=("Observed assignment, overlap, and a frozen backtest are all required.",),
    )


def discount_action(percent: float) -> ActionDefinition:
    if not 0 <= percent <= 100:
        raise ValueError("discount percent must be in [0, 100]")
    return ActionDefinition(
        action_id=f"discount-{percent:g}",
        family=ActionFamily.DISCOUNT_DEPTH,
        parameters={"percent": percent},
    )


class ActionEffectDistribution(BaseModel):
    model_config = ConfigDict(frozen=True)
    action: ActionDefinition
    point: float
    lower: float
    upper: float
    evidence_type: EvidenceType
    support_status: str
    validation_status: str


class EconomicOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)
    incremental_revenue: float | None = None
    incremental_contribution_profit: float | None = None
    gross_revenue: float | None = None
    cogs: float | None = None
    discounts: float | None = None
    refunds: float | None = None
    shipping_subsidies: float | None = None
    action_cost: float | None = None
    status: str
    missing_fields: tuple[str, ...] = ()


class StateInteractionEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    driver: str
    customer_segment: str
    current_state: float | str
    historical_reference: float | str
    interaction_estimate: float | None
    uncertainty: dict[str, float]
    out_of_time_validation: str
    geographic_alignment: str
    evidence_type: EvidenceType
    wording_allowed: bool = False

    @model_validator(mode="after")
    def causal_due_to_requires_causal_evidence(self) -> StateInteractionEvidence:
        if self.wording_allowed and self.evidence_type not in {
            EvidenceType.CAUSAL_RCT,
            EvidenceType.CAUSAL_OBSERVATIONAL,
        }:
            raise ValueError("causal world-interaction wording requires causal evidence")
        return self


class CapabilityStatus(StrEnum):
    READY = "READY"
    LIMITED = "LIMITED"
    NOT_READY = "NOT_READY"


class CustomerTwinReadinessReportV1(BaseModel):
    model_config = ConfigDict(frozen=True)
    descriptive: CapabilityStatus
    predictive_repeat_purchase: CapabilityStatus
    causal_targeted_campaign: CapabilityStatus
    discount_causality: CapabilityStatus
    contribution_profit: CapabilityStatus
    world_interaction: CapabilityStatus
    history_days: int = Field(ge=0)
    unique_customers: int = Field(ge=0)
    repeat_customers: int = Field(ge=0)
    orders: int = Field(ge=0)
    actions: int = Field(ge=0)
    treatment_observations: int = Field(ge=0)
    control_observations: int = Field(ge=0)
    outcome_incidence: float | None = Field(default=None, ge=0, le=1)
    action_overlap: float | None = Field(default=None, ge=0, le=1)
    effective_sample_size: float | None = Field(default=None, ge=0)
    category_support: int = Field(ge=0)
    economic_field_coverage: dict[str, bool]
    reasons: tuple[str, ...]


class ExperimentDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    experiment_id: str
    action: ActionDefinition
    randomization_unit: str
    eligibility_rule: str
    control: str
    treatment: str
    assignment_probability: float = Field(gt=0, lt=1)
    primary_metric: str
    guardrails: tuple[str, ...]
    minimum_detectable_effect: float = Field(gt=0)
    planned_sample_size: int = Field(gt=1)
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def valid_window(self) -> ExperimentDefinition:
        if self.end_time <= self.start_time:
            raise ValueError("experiment end_time must follow start_time")
        return self


def deterministic_assignment(experiment_id: str, unit_id: str, probability: float) -> bool:
    if not 0 < probability < 1:
        raise ValueError("assignment probability must be in (0, 1)")
    digest = hashlib.sha256(f"{experiment_id}:{unit_id}".encode()).digest()
    uniform = int.from_bytes(digest[:8], "big") / 2**64
    return uniform < probability


def srm_check(
    treatment_count: int, control_count: int, probability: float
) -> dict[str, float | bool]:
    total = treatment_count + control_count
    if total <= 0 or not 0 < probability < 1:
        raise ValueError("SRM requires observations and a valid assignment probability")
    expected = np.array([total * probability, total * (1 - probability)])
    statistic, p_value = chisquare([treatment_count, control_count], expected)
    return {
        "statistic": float(statistic),
        "p_value": float(p_value),
        "srm_detected": bool(p_value < 0.01),
        "trusted": bool(p_value >= 0.01),
    }


def utc_now() -> datetime:
    return datetime.now(UTC)
