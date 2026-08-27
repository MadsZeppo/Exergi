"""Mechanical economic-claim authority; labels cannot exceed observed components."""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, ConfigDict, model_validator


class ClaimLevel(IntEnum):
    SYNTHETIC_MECHANISM_ONLY = 0
    REAL_RANDOMIZED_PROXY_OUTCOME = 1
    REAL_RANDOMIZED_REVENUE = 2
    REAL_RANDOMIZED_ECONOMIC_VALUE_UNDER_DECLARED_COSTS = 3
    REAL_RANDOMIZED_CONTRIBUTION_PROFIT = 4


class ClaimAuthority(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: ClaimLevel
    randomized: bool
    real_world: bool
    monetary_outcome: bool
    observed_revenue: bool = False
    declared_action_costs: bool = False
    observed_cogs: bool = False
    observed_variable_costs: bool = False
    label: str

    @model_validator(mode="after")
    def validate_authority(self) -> ClaimAuthority:
        if self.level >= ClaimLevel.REAL_RANDOMIZED_PROXY_OUTCOME and not (
            self.randomized and self.real_world
        ):
            raise ValueError("real randomized claim requires real randomized evidence")
        if self.level >= ClaimLevel.REAL_RANDOMIZED_REVENUE and not (
            self.monetary_outcome and self.observed_revenue
        ):
            raise ValueError("revenue claim requires observed monetary revenue")
        if (
            self.level
            >= ClaimLevel.REAL_RANDOMIZED_ECONOMIC_VALUE_UNDER_DECLARED_COSTS
            and not self.declared_action_costs
        ):
            raise ValueError("scenario economic value requires explicit declared costs")
        if self.level is ClaimLevel.REAL_RANDOMIZED_CONTRIBUTION_PROFIT and not (
            self.observed_cogs and self.observed_variable_costs
        ):
            raise ValueError("contribution-profit claim requires observed cost components")
        return self
