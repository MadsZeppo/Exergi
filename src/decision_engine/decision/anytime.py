"""Anytime-valid confidence sequences for bounded policy-value differences."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ConfidenceSequence:
    times: np.ndarray
    means: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    promoted_at: int | None


def hoeffding_confidence_sequence(
    values: np.ndarray,
    *,
    alpha: float = 0.05,
    lower_bound: float,
    upper_bound: float,
) -> ConfidenceSequence:
    """Union-bound Hoeffding CS valid at every inspected finite time.

    At time ``t`` the error allocation is ``alpha/(t*(t+1))``. The allocations
    sum to alpha, so optional stopping/continuous monitoring does not inflate
    the family-wise error under the stated bounded-i.i.d. assumption.
    """
    x = np.asarray(values, dtype=float)
    if not len(x) or not 0 < alpha < 1 or upper_bound <= lower_bound:
        raise ValueError("invalid confidence-sequence inputs")
    if np.any((x < lower_bound) | (x > upper_bound)):
        raise ValueError("observations violate preregistered bounds")
    times = np.arange(1, len(x) + 1)
    means = np.cumsum(x) / times
    alpha_t = alpha / (times * (times + 1))
    radius = (upper_bound - lower_bound) * np.sqrt(np.log(2 / alpha_t) / (2 * times))
    lower, upper = means - radius, means + radius
    promoted = np.flatnonzero(lower > 0)
    return ConfidenceSequence(
        times=times,
        means=means,
        lower=lower,
        upper=upper,
        promoted_at=int(promoted[0] + 1) if len(promoted) else None,
    )
