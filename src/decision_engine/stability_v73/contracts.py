"""Deployable V7.3 stability-gate contracts with no evaluator truth fields."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class GateInput:
    outcome: NDArray[np.float64]
    treatment: NDArray[np.int64]
    features: NDArray[np.float64]
    unit_id: NDArray[np.str_]
    split_key: NDArray[np.uint64]
    logged_propensity: NDArray[np.float64]
    mature: NDArray[np.bool_]
    action_cost: float
    per_unit_budget: float
    assignment_integrity_valid: bool = True
    support_valid: bool = True
    post_treatment_feature_present: bool = False
    assignment_contamination: bool = False

    def __post_init__(self) -> None:
        n = len(self.outcome)
        arrays = (
            self.treatment,
            self.features,
            self.unit_id,
            self.split_key,
            self.logged_propensity,
            self.mature,
        )
        if n == 0 or any(len(value) != n for value in arrays):
            raise ValueError("gate input arrays must be nonempty and row-aligned")
        if self.features.ndim != 2:
            raise ValueError("features must be a two-dimensional pretreatment matrix")
        if set(np.unique(self.treatment)) - {0, 1}:
            raise ValueError("stability gate currently requires a binary randomized action")
        if len(np.unique(self.unit_id)) != n:
            raise ValueError("randomization units must be disjoint and unique")
        if not np.all(np.isfinite(self.features)):
            raise ValueError("pretreatment features must be finite")
        if not np.all(np.isfinite(self.logged_propensity)):
            raise ValueError("logged propensities must be finite")
        if self.action_cost < 0 or self.per_unit_budget < 0:
            raise ValueError("costs and budgets must be nonnegative")
        mature_outcome = self.outcome[self.mature]
        if not np.all(np.isfinite(mature_outcome)):
            raise ValueError("mature outcomes must be finite")


@dataclass(frozen=True)
class GateDecision:
    gate: str
    act: bool
    point_net_value: float
    lower_bound: float
    confidence: float
    supported: bool
    reasons: tuple[str, ...]
