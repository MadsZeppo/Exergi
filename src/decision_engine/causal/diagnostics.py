from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OverlapDiagnostics:
    min_propensity: float
    max_propensity: float
    effective_sample_size: float
    treatment_count: int
    nearest_comparable_count: int
    status: str


def overlap_diagnostics(
    propensity: np.ndarray,
    treatment: np.ndarray,
    *,
    action: int = 1,
    low_threshold: float = 0.05,
    insufficient_threshold: float = 0.01,
) -> OverlapDiagnostics:
    propensity = np.asarray(propensity, dtype=float)
    if np.any((propensity < 0) | (propensity > 1)):
        raise ValueError("propensities must be probabilities")
    weights = np.where(treatment == action, 1 / np.clip(propensity, 1e-9, 1), 0)
    nonzero = weights[weights > 0]
    ess = float(nonzero.sum() ** 2 / np.sum(nonzero**2)) if nonzero.size else 0.0
    minimum = float(propensity.min())
    status = (
        "INSUFFICIENT_EVIDENCE"
        if minimum < insufficient_threshold
        else "LOW_SUPPORT"
        if minimum < low_threshold
        else "GOOD"
    )
    comparable = int(np.sum((propensity >= low_threshold) & (propensity <= 1 - low_threshold)))
    return OverlapDiagnostics(
        minimum, float(propensity.max()), ess, int(np.sum(treatment == action)), comparable, status
    )


def standardized_mean_differences(x: np.ndarray, treatment: np.ndarray) -> np.ndarray:
    treated, control = x[treatment == 1], x[treatment == 0]
    pooled = np.sqrt((treated.var(axis=0) + control.var(axis=0)) / 2)
    return np.divide(
        treated.mean(axis=0) - control.mean(axis=0),
        pooled,
        out=np.zeros_like(pooled),
        where=pooled > 0,
    )
