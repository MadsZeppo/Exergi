"""Versioned immutable contracts for the first fixed win-back experiment."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenContract(BaseModel):
    model_config = ConfigDict(frozen=True)


class PilotReadiness(StrEnum):
    DATA_NOT_READY = "DATA_NOT_READY"
    READY_FOR_SHADOW = "READY_FOR_SHADOW"
    CONTRACT_FROZEN = "CONTRACT_FROZEN"
    OUTCOME_NOT_MATURE = "OUTCOME_NOT_MATURE"
    READY_FOR_ANALYSIS = "READY_FOR_ANALYSIS"


class CustomerRecord(FrozenContract):
    schema_version: str = "winback.customer.v1"
    customer_id: str
    created_at: datetime
    timezone: str
    currency: str
    consent: bool
    suppressed: bool


class OrderRecord(FrozenContract):
    schema_version: str = "winback.order.v1"
    order_id: str
    customer_id: str
    ordered_at: datetime
    currency: str
    gross_item_sales: float = Field(ge=0)
    line_discounts: float = Field(ge=0)
    shipping_revenue: float = Field(ge=0)
    payment_transaction_cost: float | None = Field(default=None, ge=0)


class OrderLineRecord(FrozenContract):
    schema_version: str = "winback.order_line.v1"
    order_line_id: str
    order_id: str
    product_id: str
    quantity: int = Field(gt=0)
    gross_sales: float = Field(ge=0)
    discount: float = Field(ge=0)
    cogs: float | None = Field(default=None, ge=0)


class ProductRecord(FrozenContract):
    schema_version: str = "winback.product.v1"
    product_id: str
    category: str
    currency: str
    unit_cogs: float | None = Field(default=None, ge=0)


class ReturnRecord(FrozenContract):
    schema_version: str = "winback.return.v1"
    return_id: str
    order_id: str
    order_line_id: str | None = None
    returned_at: datetime
    refund_amount: float = Field(ge=0)
    currency: str


class DiscountRecord(FrozenContract):
    schema_version: str = "winback.discount.v1"
    discount_id: str
    order_id: str
    amount: float = Field(ge=0)
    merchant_funded_amount: float | None = Field(default=None, ge=0)
    currency: str


class CampaignEligibilityRecord(FrozenContract):
    schema_version: str = "winback.eligibility.v1"
    customer_id: str
    snapshot_at: datetime
    historical_purchase_count: int = Field(ge=0)
    last_purchase_at: datetime | None
    last_parallel_campaign_at: datetime | None
    consent: bool
    suppressed: bool


class DeliveryRecord(FrozenContract):
    schema_version: str = "winback.delivery.v1"
    experiment_id: str
    customer_id: str
    arm: str
    delivered_at: datetime | None
    exposed_at: datetime | None


class ChannelCostRecord(FrozenContract):
    schema_version: str = "winback.channel_cost.v1"
    experiment_id: str
    customer_id: str
    channel_cost: float | None = Field(default=None, ge=0)
    shipping_subsidy: float | None = Field(default=None, ge=0)
    currency: str


class ExperimentArmContract(FrozenContract):
    name: str
    allocation_probability: float = Field(gt=0, le=1)
    is_control: bool = False
    action_parameters: dict[str, Any] = {}


class WinbackExperimentContract(FrozenContract):
    schema_version: str = "winback.experiment.v1"
    experiment_id: str
    merchant_id: str
    created_at: datetime
    eligibility_snapshot_at: datetime
    inactivity_days: int = Field(gt=0)
    minimum_historical_purchases: int = Field(gt=0)
    parallel_campaign_exclusion_days: int = Field(gt=0)
    eligibility_hash: str
    primary_outcome: str = "CUSTOMER_LEVEL_CONTRIBUTION_PROFIT_ITT"
    guardrail_outcomes: tuple[str, ...] = ("REFUND_RATE", "UNSUBSCRIBE_RATE")
    outcome_maturity_days: int = Field(gt=0)
    randomization_unit: str = "CUSTOMER"
    strata_fields: tuple[str, ...] = ()
    arms: tuple[ExperimentArmContract, ...]
    minimum_detectable_effect: float = Field(gt=0)
    planned_sample_size: int = Field(gt=0)
    alpha: float = Field(default=0.05, gt=0, lt=1)
    power: float = Field(default=0.80, gt=0, lt=1)
    stopping_rules: tuple[str, ...] = (
        "STOP_FOR_DATA_INTEGRITY_FAILURE",
        "STOP_IF_MATURE_ITT_UPPER_BELOW_ZERO",
        "NO_EFFICACY_STOP_BEFORE_FIXED_HORIZON",
    )
    exclusion_rules: tuple[str, ...] = (
        "SUPPRESSED_OR_NO_CONSENT",
        "RECENT_PURCHASE",
        "RECENT_PARALLEL_CAMPAIGN",
    )
    cost_fields: tuple[str, ...] = (
        "COGS",
        "MERCHANT_FUNDED_DISCOUNT",
        "REFUNDS_RETURNS",
        "SHIPPING_SUBSIDY",
        "PAYMENT_TRANSACTION_COST",
        "CHANNEL_COST",
    )
    expected_effect_per_customer: float | None = None
    expected_effect_authority: str = "PRE_OUTCOME_PREDICTION_NOT_CAUSAL_RESULT"
    randomization_seed: str
    frozen_at: datetime | None = None
    contract_hash: str | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> WinbackExperimentContract:
        if self.created_at.tzinfo is None or self.eligibility_snapshot_at.tzinfo is None:
            raise ValueError("contract timestamps must be timezone-aware")
        if self.eligibility_snapshot_at > self.created_at:
            raise ValueError("eligibility snapshot cannot follow contract creation")
        if len(self.arms) not in {2, 3} or sum(arm.is_control for arm in self.arms) != 1:
            raise ValueError("pilot requires one control and one or two interventions")
        if abs(sum(arm.allocation_probability for arm in self.arms) - 1) > 1e-9:
            raise ValueError("arm allocation probabilities must sum to one")
        if self.randomization_unit != "CUSTOMER":
            raise ValueError("V1 randomizes customers only")
        return self


class AssignmentRecord(FrozenContract):
    schema_version: str = "winback.assignment.v1"
    experiment_id: str
    merchant_id: str
    customer_id: str
    stratum: str
    arm: str
    propensity: float = Field(gt=0, le=1)
    assigned_at: datetime
    contract_hash: str
    assignment_hash: str


class OutcomeRecord(FrozenContract):
    schema_version: str = "winback.outcome.v1"
    experiment_id: str
    merchant_id: str
    customer_id: str
    measured_at: datetime
    currency: str
    net_revenue: float
    merchant_funded_discount: float | None = Field(default=None, ge=0)
    refunds_returns: float | None = Field(default=None, ge=0)
    cogs: float | None = Field(default=None, ge=0)
    shipping_subsidy: float | None = Field(default=None, ge=0)
    payment_transaction_cost: float | None = Field(default=None, ge=0)
    channel_cost: float | None = Field(default=None, ge=0)
    unsubscribe: bool = False

    @property
    def contribution_profit(self) -> float | None:
        costs = (
            self.merchant_funded_discount,
            self.refunds_returns,
            self.cogs,
            self.shipping_subsidy,
            self.payment_transaction_cost,
            self.channel_cost,
        )
        if any(value is None for value in costs):
            return None
        return self.net_revenue - sum(float(value) for value in costs if value is not None)
