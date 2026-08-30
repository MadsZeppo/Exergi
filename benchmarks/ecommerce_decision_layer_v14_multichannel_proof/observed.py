from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np

ACTION_NAMES = (
    "BAU_NO_ACTION",
    "EMAIL_REMINDER",
    "EMAIL_10_PERCENT_DISCOUNT",
    "SMS_REMINDER",
    "SMS_10_PERCENT_DISCOUNT",
    "FREE_SHIPPING",
    "PAID_RETARGETING",
    "ONSITE_PERSONALIZATION",
    "EMAIL_PLUS_RETARGETING",
    "SUPPRESS_DO_NOT_CONTACT",
)
ACTION_INDEX = {name: index for index, name in enumerate(ACTION_NAMES)}

FORBIDDEN_POLICY_KEYS = frozenset(
    {
        "latent_response_type",
        "potential_outcomes",
        "true_cate",
        "true_best_action",
        "future_shocks",
        "future_returns",
        "response_parameters",
        "oracle_value",
        "world_family",
    }
)


@dataclass(frozen=True)
class ObservedCustomerPool:
    merchant_id: str
    family: str
    customer_ids: np.ndarray
    features: np.ndarray
    feature_names: tuple[str, ...]
    lifecycle: np.ndarray
    category: np.ndarray
    email_eligible: np.ndarray
    sms_eligible: np.ndarray
    paid_eligible: np.ndarray

    def __post_init__(self) -> None:
        if len(self.customer_ids) != 20_000 or len(set(self.customer_ids.tolist())) != 20_000:
            raise ValueError("V14 merchant pool must have 20,000 unique customers")
        if self.features.shape != (20_000, len(self.feature_names)):
            raise ValueError("V14 feature matrix shape mismatch")
        if FORBIDDEN_POLICY_KEYS & set(self.feature_names):
            raise ValueError("evaluator truth leaked into V14 feature names")


@dataclass(frozen=True)
class ObservedDecisionBatch:
    merchant_id: str
    family: str
    week: int
    customer_ids: np.ndarray
    features: np.ndarray
    feature_names: tuple[str, ...]
    eligible_actions: np.ndarray
    cost_complete: np.ndarray
    data_valid: bool

    def policy_payload(self) -> dict[str, Any]:
        payload = {
            "merchant_id": self.merchant_id,
            "family": self.family,
            "week": self.week,
            "customer_ids": self.customer_ids.tolist(),
            "features": self.features.tolist(),
            "feature_names": list(self.feature_names),
            "eligible_actions": self.eligible_actions.tolist(),
            "cost_complete": self.cost_complete.tolist(),
            "data_valid": self.data_valid,
        }
        reject_forbidden_payload(payload)
        return payload


@dataclass(frozen=True)
class LoggedDecisionBatch:
    observed: ObservedDecisionBatch
    assignment: np.ndarray
    logged_propensity: np.ndarray
    gross_revenue: np.ndarray
    contribution_profit: np.ndarray
    outcome_maturity_week: np.ndarray


def reject_forbidden_payload(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_POLICY_KEYS & set(value)
        if forbidden:
            raise ValueError(f"evaluator-only keys in policy payload: {sorted(forbidden)}")
        for item in value.values():
            reject_forbidden_payload(item)
    elif isinstance(value, list):
        for item in value:
            reject_forbidden_payload(item)


def state_hash(batch: ObservedDecisionBatch) -> str:
    digest = hashlib.sha256()
    digest.update(batch.merchant_id.encode())
    digest.update(str(batch.week).encode())
    digest.update(batch.customer_ids.tobytes())
    digest.update(batch.features.tobytes())
    digest.update(batch.eligible_actions.tobytes())
    digest.update(batch.cost_complete.tobytes())
    return digest.hexdigest()
