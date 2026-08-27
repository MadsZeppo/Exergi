"""Typed contracts for randomized multi-arm monetary policy learning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]


class ActionDisposition(StrEnum):
    BAU = "BAU"
    TEST = "TEST"
    ACT = "ACT"
    AVOID = "AVOID"


@dataclass(frozen=True)
class EconomicPolicyDataset:
    features: FloatArray
    action: IntArray
    monetary_outcome: FloatArray
    propensity: FloatArray
    action_cost: FloatArray
    allowed_actions: BoolArray
    unit_id: NDArray[np.str_]
    bau_action: int = 0
    cluster_id: NDArray[np.str_] | None = None
    mature: BoolArray | None = None
    feature_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        n = len(self.action)
        if self.features.ndim != 2 or self.features.shape[0] != n:
            raise ValueError("features must be a two-dimensional n-row matrix")
        arms = self.propensity.shape[1] if self.propensity.ndim == 2 else 0
        expected = (n, arms)
        if arms < 2 or self.action_cost.shape != expected or self.allowed_actions.shape != expected:
            raise ValueError("propensity, costs and allowed_actions must be n x arms")
        if any(len(value) != n for value in (self.monetary_outcome, self.unit_id)):
            raise ValueError("all row vectors must have n entries")
        if self.cluster_id is not None and len(self.cluster_id) != n:
            raise ValueError("cluster_id must have n entries")
        if self.mature is not None and (len(self.mature) != n or not np.all(self.mature)):
            raise ValueError("policy learning requires mature outcomes only")
        if not 0 <= self.bau_action < arms or np.any((self.action < 0) | (self.action >= arms)):
            raise ValueError("action indexes are outside the declared action space")
        if not np.all(np.isfinite(self.features)) or not np.all(np.isfinite(self.monetary_outcome)):
            raise ValueError("features and monetary outcomes must be finite")
        if not np.all(np.isfinite(self.action_cost)) or np.any(self.action_cost < 0):
            raise ValueError("action costs must be finite and non-negative")
        if np.any(self.propensity <= 0) or not np.allclose(self.propensity.sum(axis=1), 1.0):
            raise ValueError("known propensities must be positive and sum to one")
        if not np.all(self.allowed_actions[:, self.bau_action]):
            raise ValueError("BAU must always remain allowed")
        if len(np.unique(self.unit_id)) != n:
            raise ValueError("duplicate randomized units are forbidden")
        if self.feature_names and len(self.feature_names) != self.features.shape[1]:
            raise ValueError("feature_names must match feature width")

    @property
    def arms(self) -> int:
        return self.propensity.shape[1]

    @property
    def observed_net_outcome(self) -> FloatArray:
        return self.monetary_outcome - self.action_cost[np.arange(len(self.action)), self.action]


@dataclass(frozen=True)
class PolicyDecision:
    chosen_action: IntArray
    disposition: NDArray[np.str_]
    expected_net_outcome: FloatArray
    incremental_value: FloatArray
    lower_increment: FloatArray
    supported: BoolArray
    reason_code: NDArray[np.str_]
    policy_hash: str


@dataclass(frozen=True)
class PolicyEvaluation:
    estimator: str
    value_per_unit: float
    standard_error: float
    lower_95: float
    upper_95: float
    total_value: float
    effective_sample_size: float
    max_weight: float
    clipped_fraction: float
    influence: FloatArray
