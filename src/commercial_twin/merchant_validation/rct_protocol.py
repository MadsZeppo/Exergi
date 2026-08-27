"""Preregistered fixed-randomization contract for the first merchant pilot."""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.stats import norm


class PilotArm(StrEnum):
    CONTROL = "CONTROL"
    MESSAGE_ONLY = "MESSAGE_ONLY"
    LOW_DISCOUNT = "LOW_DISCOUNT"


class MerchantRCTProtocol(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_family: str = "WIN_BACK"
    arms: tuple[PilotArm, ...] = (
        PilotArm.CONTROL,
        PilotArm.MESSAGE_ONLY,
        PilotArm.LOW_DISCOUNT,
    )
    allocation_probabilities: tuple[float, ...] = (0.34, 0.33, 0.33)
    primary_outcome: str = "CONTRIBUTION_PROFIT"
    secondary_outcomes: tuple[str, ...] = ("CONVERSION", "REVENUE")
    primary_estimand: str = "INTENTION_TO_TREAT"
    secondary_estimand: str = "TREATMENT_ON_TREATED_ASSUMPTION_DEPENDENT"
    minimum_economically_relevant_effect: float = Field(gt=0)
    pre_period_days: int = Field(default=60, gt=0)
    outcome_maturity_days: int = Field(default=45, gt=0)
    alpha: float = Field(default=0.05, gt=0, lt=1)
    power: float = Field(default=0.8, gt=0, lt=1)
    permanent_control_fraction: float = Field(default=0.05, gt=0, lt=0.5)
    cuped_enabled: bool = True
    fixed_randomization: bool = True
    adaptive_allocation: bool = False
    shadow_mode_completed: bool = False
    merchant_approved_at: datetime | None = None

    @model_validator(mode="after")
    def validate_protocol(self) -> MerchantRCTProtocol:
        if PilotArm.CONTROL not in self.arms:
            raise ValueError("a control arm is mandatory")
        if len(self.arms) != len(self.allocation_probabilities):
            raise ValueError("each arm needs one allocation probability")
        if abs(sum(self.allocation_probabilities) - 1.0) > 1e-9:
            raise ValueError("allocation probabilities must sum to one")
        if self.adaptive_allocation or not self.fixed_randomization:
            raise ValueError("V7 real-world protocol permits fixed randomization only")
        if self.merchant_approved_at is not None and self.merchant_approved_at.tzinfo is None:
            raise ValueError("approval timestamp must be timezone-aware")
        return self

    @property
    def launch_allowed(self) -> bool:
        return self.shadow_mode_completed and self.merchant_approved_at is not None

    def approximate_sample_size_per_comparison(self, *, outcome_sd: float) -> int:
        if outcome_sd <= 0:
            raise ValueError("outcome_sd must be positive")
        z_alpha = norm.ppf(1 - self.alpha / 2)
        z_power = norm.ppf(self.power)
        return math.ceil(
            2 * (z_alpha + z_power) ** 2 * outcome_sd**2
            / self.minimum_economically_relevant_effect**2
        )


class CommercialEvidenceGate(BaseModel):
    model_config = ConfigDict(frozen=True)

    preregistered_experiments: int = Field(ge=0)
    merchants: int = Field(ge=0)
    replicated_action_families: int = Field(ge=0)
    pooled_cp_lower: float | None
    all_negative_trials_included: bool
    any_hard_budget_breach: bool
    any_merchant_serious_loss: bool

    @property
    def permits_real_profit_claim(self) -> bool:
        return (
            self.preregistered_experiments >= 3
            and self.merchants >= 2
            and self.replicated_action_families >= 1
            and self.pooled_cp_lower is not None
            and self.pooled_cp_lower > 0
            and self.all_negative_trials_included
            and not self.any_hard_budget_breach
            and not self.any_merchant_serious_loss
        )

