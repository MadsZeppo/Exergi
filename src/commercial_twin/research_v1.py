"""Shared scientific primitives for Customer Twin Research V1.

Prediction, causal response, policy value, and economics deliberately use
different contracts.  Dataset runners must obtain explicit authority before
touching an official outcome store.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class ResearchMode(StrEnum):
    AUDIT = "audit"
    QUICK = "quick"
    DEVELOPMENT = "development"
    FREEZE = "freeze"
    OFFICIAL = "official"


class EvidenceLevel(StrEnum):
    OBSERVED = "OBSERVED"
    PREDICTED = "PREDICTED"
    RANDOMIZED_CAUSAL = "RANDOMIZED_CAUSAL"
    OBSERVATIONAL_CAUSAL = "OBSERVATIONAL_CAUSAL"
    EXPERIMENTAL_POLICY_VALUE = "EXPERIMENTAL_POLICY_VALUE"
    SIMULATED_ONLY = "SIMULATED_ONLY"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class ObservedTransition:
    customer_key: str
    state_before: tuple[float, ...]
    action: str
    state_after: tuple[float, ...]
    outcome: float
    evidence: EvidenceLevel = EvidenceLevel.OBSERVED


@dataclass(frozen=True)
class PotentialOutcomeQuery:
    customer_key: str
    state: tuple[float, ...]
    actions: tuple[str, ...]
    horizon: int


@dataclass(frozen=True)
class CausalTransitionEstimate:
    query: PotentialOutcomeQuery
    expected_outcomes: dict[str, float]
    standard_errors: dict[str, float]
    support: dict[str, bool]
    evidence: EvidenceLevel


@dataclass(frozen=True)
class PolicyValueEstimate:
    policy_name: str
    value: float
    standard_error: float
    effective_sample_size: float
    evidence: EvidenceLevel
    economics_status: str = "ECONOMICS_NOT_IDENTIFIED"


@dataclass(frozen=True)
class BenchmarkAuthority:
    mode: ResearchMode

    def require(self, operation: str, allowed: frozenset[ResearchMode]) -> None:
        if self.mode not in allowed:
            raise PermissionError(f"{self.mode.value} mode cannot {operation}")

    def require_official(self, operation: str) -> None:
        self.require(operation, frozenset({ResearchMode.OFFICIAL}))

    def require_freeze(self, operation: str) -> None:
        self.require(operation, frozenset({ResearchMode.FREEZE}))


def exponential_point_process_nll(
    inter_event_times: np.ndarray,
    intensities: np.ndarray,
    censoring_time: float = 0.0,
) -> float:
    """Constant-between-events marked-process NLL including right censoring."""
    delta = np.asarray(inter_event_times, dtype=float)
    rate = np.asarray(intensities, dtype=float)
    if delta.shape != rate.shape or np.any(delta < 0) or np.any(rate <= 0):
        raise ValueError("times and positive intensities must have equal shape")
    if censoring_time < 0:
        raise ValueError("censoring time must be nonnegative")
    return float(np.sum(rate * delta - np.log(rate)) + rate[-1] * censoring_time)


def time_rescaling_residuals(inter_event_times: np.ndarray, intensities: np.ndarray) -> np.ndarray:
    delta = np.asarray(inter_event_times, dtype=float)
    rate = np.asarray(intensities, dtype=float)
    if delta.shape != rate.shape or np.any(delta < 0) or np.any(rate < 0):
        raise ValueError("invalid time-rescaling inputs")
    return delta * rate


def expected_calibration_error(
    outcomes: np.ndarray, probabilities: np.ndarray, bins: int = 10
) -> float:
    y = np.asarray(outcomes, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    if y.shape != p.shape or np.any((p < 0) | (p > 1)):
        raise ValueError("outcomes/probabilities invalid")
    edges = np.linspace(0, 1, bins + 1)
    result = 0.0
    for index in range(bins):
        mask = (p >= edges[index]) & (
            p < edges[index + 1] if index < bins - 1 else p <= edges[index + 1]
        )
        if mask.any():
            result += float(mask.mean()) * abs(float(y[mask].mean() - p[mask].mean()))
    return result


def energy_score(samples: np.ndarray, actual: np.ndarray) -> float:
    draws = np.asarray(samples, dtype=float)
    observed = np.asarray(actual, dtype=float)
    if draws.ndim != 2 or observed.shape != (draws.shape[1],):
        raise ValueError("samples must be [draw, dimension] and actual one vector")
    first = np.linalg.norm(draws - observed, axis=1).mean()
    pairwise = np.linalg.norm(draws[:, None, :] - draws[None, :, :], axis=2).mean()
    return float(first - 0.5 * pairwise)


def effective_sample_size(weights: np.ndarray) -> float:
    values = np.asarray(weights, dtype=float)
    denominator = float(np.sum(values**2))
    return 0.0 if denominator == 0 else float(np.sum(values) ** 2 / denominator)


def importance_weights(
    logged_action_probability: np.ndarray,
    target_action_probability: np.ndarray,
) -> np.ndarray:
    behavior = np.asarray(logged_action_probability, dtype=float)
    target = np.asarray(target_action_probability, dtype=float)
    if behavior.shape != target.shape or np.any(behavior <= 0):
        raise ValueError("logged propensities must be positive and aligned")
    return target / behavior


def ips(reward: np.ndarray, weights: np.ndarray) -> float:
    return float(np.mean(np.asarray(reward, dtype=float) * np.asarray(weights, dtype=float)))


def snips(reward: np.ndarray, weights: np.ndarray) -> float:
    reward_array, weight_array = np.asarray(reward, float), np.asarray(weights, float)
    total = float(weight_array.sum())
    if total <= 0:
        raise ValueError("SNIPS has zero target-policy support")
    return float(np.sum(reward_array * weight_array) / total)


def doubly_robust_policy_value(
    reward: np.ndarray,
    weights: np.ndarray,
    factual_reward_prediction: np.ndarray,
    target_reward_prediction: np.ndarray,
) -> float:
    reward_array = np.asarray(reward, float)
    return float(
        np.mean(
            np.asarray(target_reward_prediction, float)
            + np.asarray(weights, float)
            * (reward_array - np.asarray(factual_reward_prediction, float))
        )
    )


def multiarm_aipw_components(
    outcome: np.ndarray,
    treatment: np.ndarray,
    outcome_predictions: np.ndarray,
    propensities: np.ndarray,
) -> np.ndarray:
    """Return per-row phi_a for every action; nuisances must be cross-fitted."""
    y, action = np.asarray(outcome, float), np.asarray(treatment, int)
    mu, propensity = np.asarray(outcome_predictions, float), np.asarray(propensities, float)
    if mu.shape != propensity.shape or mu.shape[0] != len(y):
        raise ValueError("multi-arm nuisance arrays are not aligned")
    if np.any(propensity <= 0) or np.any(action < 0) or np.any(action >= mu.shape[1]):
        raise ValueError("invalid treatment support or propensity")
    score = mu.copy()
    rows = np.arange(len(y))
    score[rows, action] += (y - mu[rows, action]) / propensity[rows, action]
    return score
