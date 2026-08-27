"""Fail-closed economic outcome contract for a real merchant experiment."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MerchantEconomicOutcome(BaseModel):
    """Auditable customer-level ITT outcome after the declared maturity window.

    ``order_revenue`` is gross item revenue before merchant-funded discounts.
    Missing costs deliberately make contribution profit unavailable.
    """

    model_config = ConfigDict(frozen=True)

    experiment_id: UUID
    merchant_id: UUID
    customer_id: UUID
    interference_key: str
    assignment_timestamp: datetime
    eligibility_snapshot_timestamp: datetime
    outcome_maturity_timestamp: datetime
    arm: str
    propensity: float = Field(gt=0, le=1)
    delivered: bool | None
    exposed: bool | None
    complied: bool | None
    order_revenue: float = Field(ge=0)
    item_level_cogs: float | None = Field(default=None, ge=0)
    merchant_funded_discount: float | None = Field(default=None, ge=0)
    shipping_subsidy: float | None = Field(default=None, ge=0)
    returns_and_refunds: float | None = Field(default=None, ge=0)
    payment_transaction_fees: float | None = Field(default=None, ge=0)
    campaign_channel_cost: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_temporal_contract(self) -> MerchantEconomicOutcome:
        timestamps = (
            self.assignment_timestamp,
            self.eligibility_snapshot_timestamp,
            self.outcome_maturity_timestamp,
        )
        if any(value.tzinfo is None for value in timestamps):
            raise ValueError("all timestamps must be timezone-aware")
        if self.eligibility_snapshot_timestamp > self.assignment_timestamp:
            raise ValueError("eligibility snapshot must not occur after assignment")
        if self.outcome_maturity_timestamp <= self.assignment_timestamp:
            raise ValueError("outcome maturity must occur after assignment")
        return self

    @property
    def is_economically_complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.item_level_cogs,
                self.merchant_funded_discount,
                self.shipping_subsidy,
                self.returns_and_refunds,
                self.payment_transaction_fees,
                self.campaign_channel_cost,
            )
        )

    def contribution_profit(self, *, observed_at: datetime) -> float | None:
        """Return mature contribution profit or ``None`` when evidence is incomplete."""

        if observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if observed_at < self.outcome_maturity_timestamp or not self.is_economically_complete:
            return None
        costs = (
            self.item_level_cogs,
            self.merchant_funded_discount,
            self.shipping_subsidy,
            self.returns_and_refunds,
            self.payment_transaction_fees,
            self.campaign_channel_cost,
        )
        return self.order_revenue - sum(float(value) for value in costs if value is not None)

