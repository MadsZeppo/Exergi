"""Proper scoring rules: lower values are better."""

from __future__ import annotations

import numpy as np


def interval_score(y: np.ndarray, lower: np.ndarray, upper: np.ndarray, alpha: float) -> np.ndarray:
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie strictly between zero and one")
    if not (y.shape == lower.shape == upper.shape):
        raise ValueError("arrays must have equal shapes")
    if np.any(lower > upper):
        raise ValueError("lower interval endpoint exceeds upper endpoint")
    below = (2 / alpha) * (lower - y) * (y < lower)
    above = (2 / alpha) * (y - upper) * (y > upper)
    return (upper - lower) + below + above


def weighted_interval_score(
    y: np.ndarray,
    median: np.ndarray,
    intervals: dict[float, tuple[np.ndarray, np.ndarray]],
) -> float:
    """Forecast-hub WIS using alpha/2 weights plus median absolute error."""
    if y.shape != median.shape or not intervals:
        raise ValueError("targets, medians, and at least one interval are required")
    total = 0.5 * np.abs(y - median)
    for alpha, (lower, upper) in intervals.items():
        total += (alpha / 2) * interval_score(y, lower, upper, alpha)
    return float(np.mean(total / (len(intervals) + 0.5)))


def crps_ensemble(observations: np.ndarray, samples: np.ndarray) -> float:
    """Empirical CRPS: E|X-y| - 0.5 E|X-X'|, averaged over observations."""
    y = np.asarray(observations, dtype=float).reshape(-1)
    draws = np.asarray(samples, dtype=float)
    if draws.ndim == 1:
        draws = draws.reshape(1, -1)
    if draws.shape[0] != y.size or draws.shape[1] == 0:
        raise ValueError("samples must have shape observations x non-empty draws")
    first = np.mean(np.abs(draws - y[:, None]), axis=1)
    pairwise = np.mean(np.abs(draws[:, :, None] - draws[:, None, :]), axis=(1, 2))
    return float(np.mean(first - 0.5 * pairwise))
