"""Known-propensity IPW, Hajek and doubly robust multi-arm policy evaluation."""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

from .contracts import EconomicPolicyDataset, FloatArray, IntArray, PolicyEvaluation


def _cluster_standard_error(influence: FloatArray, cluster_id: np.ndarray | None) -> float:
    if cluster_id is None:
        return float(np.std(influence, ddof=1) / np.sqrt(len(influence)))
    unique, inverse = np.unique(cluster_id, return_inverse=True)
    totals = np.bincount(inverse, weights=influence - np.mean(influence))
    if len(unique) < 2:
        return float("inf")
    return float(np.sqrt(np.sum(totals**2) / (len(influence) ** 2)))


def evaluate_policy(
    data: EconomicPolicyDataset,
    policy: IntArray,
    nuisance_net: FloatArray,
    *,
    estimator: str = "dr",
    weight_clip: float | None = None,
) -> PolicyEvaluation:
    n = len(data.action)
    if policy.shape != (n,) or nuisance_net.shape != (n, data.arms):
        raise ValueError("policy and nuisance matrices do not align with evaluation rows")
    if np.any(~data.allowed_actions[np.arange(n), policy]):
        raise ValueError("evaluation policy selected a prohibited action")
    observed_p = data.propensity[np.arange(n), data.action]
    raw_weight = (data.action == policy) / observed_p
    weight = raw_weight.copy()
    if weight_clip is not None:
        if weight_clip <= 0:
            raise ValueError("weight_clip must be positive")
        weight = np.minimum(weight, weight_clip)
    observed = data.observed_net_outcome
    matched = data.action == policy
    if estimator == "ipw":
        influence = weight * observed
    elif estimator == "hajek":
        denominator = float(weight.sum())
        if denominator <= 0:
            raise ValueError("policy has no randomized support")
        value = float(np.sum(weight * observed) / denominator)
        influence = value + n * weight * (observed - value) / denominator
    elif estimator == "dr":
        selected = nuisance_net[np.arange(n), policy]
        observed_model = nuisance_net[np.arange(n), data.action]
        influence = selected + weight * (observed - observed_model)
    else:
        raise ValueError(f"unknown policy estimator: {estimator}")
    value = float(np.mean(influence))
    se = _cluster_standard_error(np.asarray(influence, dtype=float), data.cluster_id)
    critical = float(norm.ppf(0.975))
    positive = weight[matched]
    ess = float(positive.sum() ** 2 / np.sum(positive**2)) if len(positive) else 0.0
    clipped_fraction = float(np.mean(weight < raw_weight))
    return PolicyEvaluation(
        estimator,
        value,
        se,
        value - critical * se,
        value + critical * se,
        value * n,
        ess,
        float(np.max(weight, initial=0.0)),
        clipped_fraction,
        np.asarray(influence, dtype=float),
    )


def value_all_actions(
    data: EconomicPolicyDataset, nuisance_net: FloatArray
) -> tuple[PolicyEvaluation, ...]:
    return tuple(
        evaluate_policy(
            data,
            np.full(len(data.action), arm, dtype=np.int64),
            nuisance_net,
        )
        for arm in range(data.arms)
        if np.all(data.allowed_actions[:, arm])
    )
