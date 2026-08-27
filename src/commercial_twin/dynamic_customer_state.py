"""Typed observational customer-state and fail-closed causal interfaces."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Reliability(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DynamicCustomerState(BaseModel):
    model_config = ConfigDict(frozen=True)
    customer_key: str
    as_of_event: int = Field(ge=0)
    predictive_state_vector: tuple[float, ...]
    latent_state_vector: tuple[float, ...]
    next_event_probabilities: dict[str, float]
    purchase_next_5_probability: float = Field(ge=0, le=1)
    purchase_next_10_probability: float = Field(ge=0, le=1)
    purchase_next_20_probability: float = Field(ge=0, le=1)
    cart_next_5_probability: float = Field(ge=0, le=1)
    cart_next_10_probability: float = Field(ge=0, le=1)
    cart_next_20_probability: float = Field(ge=0, le=1)
    expected_next_5_event_mix: dict[str, float]
    expected_next_10_event_mix: dict[str, float]
    expected_next_20_event_mix: dict[str, float]
    purchase_history_depth: int = Field(ge=0)
    behavioral_history_depth: int = Field(ge=0)
    state_uncertainty: float = Field(ge=0)
    empirical_reliability: Reliability
    model_version: str
    feature_version: str

    @model_validator(mode="after")
    def probability_simplexes(self) -> DynamicCustomerState:
        for values in (
            self.next_event_probabilities,
            self.expected_next_5_event_mix,
            self.expected_next_10_event_mix,
            self.expected_next_20_event_mix,
        ):
            if set(values) != {"CLICK", "CART", "FLW", "ORD"}:
                raise ValueError("event distributions require CLICK/CART/FLW/ORD")
            if any(value < 0 or value > 1 for value in values.values()):
                raise ValueError("event probabilities must be in [0,1]")
            if abs(sum(values.values()) - 1) > 1e-6:
                raise ValueError("event probabilities must sum to one")
        return self


class MerchantActionType(StrEnum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    DISCOUNT = "DISCOUNT"
    PRICE_CHANGE = "PRICE_CHANGE"
    SHIPPING_OFFER = "SHIPPING_OFFER"
    RECOMMENDATION = "RECOMMENDATION"
    AD_EXPOSURE = "AD_EXPOSURE"
    SERVICE_INTERVENTION = "SERVICE_INTERVENTION"


class MerchantAction(BaseModel):
    model_config = ConfigDict(frozen=True)
    action_type: MerchantActionType
    action_id: str
    parameters: dict[str, float | str] = {}


class CausalTransitionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: str
    reason: str


class CausalTransitionKernel(Protocol):
    def evaluate(
        self, state: DynamicCustomerState, action: MerchantAction
    ) -> CausalTransitionResult: ...


class JDSearchCausalTransitionKernel:
    def evaluate(
        self, state: DynamicCustomerState, action: MerchantAction
    ) -> CausalTransitionResult:
        del state, action
        return CausalTransitionResult(
            status="INSUFFICIENT_CAUSAL_EVIDENCE",
            reason="JDsearch records customer behavior, not exogenous merchant action assignment",
        )


@dataclass(frozen=True)
class DynamicsBenchmarkAuthority:
    """Fail-closed boundary between pipeline validation and official science."""

    quick: bool

    def require_definitive(self, operation: str) -> None:
        if self.quick:
            raise PermissionError(f"Quick mode cannot perform official operation: {operation}")


def stable_customer_split(customer_key: int) -> str:
    digest = hashlib.sha256(f"jdsearch-dynamics-v1:{customer_key}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") % 10_000
    if bucket < 7_000:
        return "TRAIN"
    if bucket < 8_500:
        return "DEVELOPMENT"
    return "OFFICIAL_FINAL"
