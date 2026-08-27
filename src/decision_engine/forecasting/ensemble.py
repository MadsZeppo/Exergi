from __future__ import annotations

from enum import StrEnum

import numpy as np


class EnsembleStrategy(StrEnum):
    EQUAL = "equal"
    RECENT_PERFORMANCE = "recent_performance"
    SINGLE_BEST = "single_best"


def historical_model_weights(
    losses: dict[str, np.ndarray],
    *,
    strategy: EnsembleStrategy = EnsembleStrategy.RECENT_PERFORMANCE,
    eta: float = 1.0,
    recent_window: int | None = None,
) -> dict[str, float]:
    """Compute weights solely from losses already observed at decision time."""
    if not losses:
        raise ValueError("at least one model is required")
    names = sorted(losses)
    recent = [
        np.asarray(losses[name], dtype=float)
        if recent_window is None
        else np.asarray(losses[name], dtype=float)[-recent_window:]
        for name in names
    ]
    if any(values.size == 0 or not np.all(np.isfinite(values)) for values in recent):
        raise ValueError("each model requires finite historical losses")
    mean_losses = np.array([values.mean() for values in recent])
    if strategy == EnsembleStrategy.EQUAL:
        weights = np.ones(len(names))
    elif strategy == EnsembleStrategy.SINGLE_BEST:
        weights = np.zeros(len(names))
        weights[int(np.argmin(mean_losses))] = 1
    else:
        centered = mean_losses - mean_losses.min()
        scale = max(float(np.median(np.abs(centered))), 1e-12)
        weights = np.exp(-eta * centered / scale)
    weights /= weights.sum()
    return dict(zip(names, map(float, weights), strict=True))


def weighted_prediction(
    predictions: dict[str, np.ndarray], weights: dict[str, float]
) -> np.ndarray:
    if set(predictions) != set(weights):
        raise ValueError("prediction and weight model names must match")
    if not np.isclose(sum(weights.values()), 1):
        raise ValueError("weights must sum to one")
    return sum(
        (weights[name] * predictions[name] for name in sorted(predictions)), start=np.array(0.0)
    )
