"""Auditable off-policy estimators and weight/support diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OPEDiagnostics:
    effective_sample_size: float
    maximum_weight: float
    weight_quantiles: tuple[float, float, float]
    unsupported_fraction: float


def ope_diagnostics(weights: np.ndarray, target_probability: np.ndarray) -> OPEDiagnostics:
    w = np.asarray(weights, dtype=float)
    target = np.asarray(target_probability, dtype=float)
    if len(w) != len(target) or np.any(w < 0):
        raise ValueError("invalid OPE weights")
    denominator = float(np.sum(w**2))
    ess = 0.0 if denominator == 0 else float(np.sum(w) ** 2 / denominator)
    q = np.quantile(w, [0.5, 0.9, 0.99])
    return OPEDiagnostics(
        effective_sample_size=ess,
        maximum_weight=float(np.max(w)),
        weight_quantiles=(float(q[0]), float(q[1]), float(q[2])),
        unsupported_fraction=float(np.mean(target <= 0)),
    )


def direct_method(target_reward_prediction: np.ndarray) -> float:
    return float(np.mean(np.asarray(target_reward_prediction, dtype=float)))


def ips_value(reward: np.ndarray, weights: np.ndarray) -> float:
    return float(np.mean(np.asarray(reward, float) * np.asarray(weights, float)))


def snips_value(reward: np.ndarray, weights: np.ndarray) -> float:
    reward, weights = np.asarray(reward, float), np.asarray(weights, float)
    if np.sum(weights) <= 0:
        raise ValueError("zero policy support")
    return float(np.sum(reward * weights) / np.sum(weights))


def dr_value(
    reward: np.ndarray,
    weights: np.ndarray,
    factual_prediction: np.ndarray,
    target_prediction: np.ndarray,
) -> float:
    return float(
        np.mean(
            np.asarray(target_prediction, float)
            + np.asarray(weights, float)
            * (np.asarray(reward, float) - np.asarray(factual_prediction, float))
        )
    )


def clipped_dr_value(
    reward: np.ndarray,
    weights: np.ndarray,
    factual_prediction: np.ndarray,
    target_prediction: np.ndarray,
    *,
    clip: float,
) -> float:
    return dr_value(reward, np.minimum(weights, clip), factual_prediction, target_prediction)


def shrinkage_dr_value(
    reward: np.ndarray,
    weights: np.ndarray,
    factual_prediction: np.ndarray,
    target_prediction: np.ndarray,
    *,
    shrinkage: float,
) -> float:
    w = np.asarray(weights, float)
    shrunk = w / (1 + shrinkage * w**2)
    return dr_value(reward, shrunk, factual_prediction, target_prediction)


def switch_dr_value(
    reward: np.ndarray,
    weights: np.ndarray,
    factual_prediction: np.ndarray,
    target_prediction: np.ndarray,
    *,
    threshold: float,
) -> float:
    w = np.asarray(weights, float)
    switched = np.where(w <= threshold, w, 0.0)
    return dr_value(reward, switched, factual_prediction, target_prediction)
