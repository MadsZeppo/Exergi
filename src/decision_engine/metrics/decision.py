from __future__ import annotations

import numpy as np


def direct_policy_value(policy: np.ndarray, predicted_outcomes: np.ndarray) -> float:
    return float(np.mean(predicted_outcomes[np.arange(policy.size), policy]))


def ipw_policy_value(
    policy: np.ndarray, treatment: np.ndarray, outcome: np.ndarray, propensity: np.ndarray
) -> float:
    matched = policy == treatment
    return float(np.mean(matched * outcome / np.clip(propensity, 1e-9, 1)))


def doubly_robust_policy_value(
    policy: np.ndarray,
    treatment: np.ndarray,
    outcome: np.ndarray,
    action_propensity: np.ndarray,
    predicted_outcomes: np.ndarray,
) -> float:
    idx = np.arange(policy.size)
    direct = predicted_outcomes[idx, policy]
    matched = policy == treatment
    correction = (
        matched
        * (outcome - predicted_outcomes[idx, treatment])
        / np.clip(action_propensity, 1e-9, 1)
    )
    return float(np.mean(direct + correction))
