from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PlaceboResult:
    name: str
    observed_effect: float
    placebo_effects: tuple[float, ...]
    empirical_p_value: float
    status: str


def grouped_treatment_shuffle_placebo(
    treatment: np.ndarray,
    outcome: np.ndarray,
    groups: np.ndarray,
    estimator: Callable[[np.ndarray, np.ndarray], float],
    *,
    repetitions: int = 200,
    seed: int = 42,
) -> PlaceboResult:
    """Shuffle labels within configured groups; the grouping must be scientifically defensible."""
    treatment, outcome, groups = map(np.asarray, (treatment, outcome, groups))
    observed = float(estimator(treatment, outcome))
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(repetitions):
        shuffled = treatment.copy()
        for group in np.unique(groups):
            indices = np.flatnonzero(groups == group)
            shuffled[indices] = rng.permutation(shuffled[indices])
        values.append(float(estimator(shuffled, outcome)))
    placebo = np.asarray(values)
    p_value = float((1 + np.sum(np.abs(placebo) >= abs(observed))) / (repetitions + 1))
    status = "PASS" if p_value < 0.05 else "WARNING" if p_value < 0.2 else "FAIL"
    return PlaceboResult("grouped_treatment_shuffle", observed, tuple(values), p_value, status)
