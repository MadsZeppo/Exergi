"""Variance-adaptive anytime-valid challenger for bounded outcomes."""

from __future__ import annotations

import numpy as np

from decision_engine.decision.anytime import ConfidenceSequence


def empirical_bernstein_confidence_sequence(
    values: np.ndarray,
    *,
    alpha: float = 0.05,
    lower_bound: float,
    upper_bound: float,
) -> ConfidenceSequence:
    """Time-uniform empirical-Bernstein CS via per-time error spending.

    The bound assumes independent bounded observations. Adaptive logging is
    admissible only when the supplied values are valid bounded martingale
    differences constructed with exact predictable propensities.
    """
    x = np.asarray(values, dtype=float)
    if not len(x) or upper_bound <= lower_bound or not 0 < alpha < 1:
        raise ValueError("invalid confidence-sequence inputs")
    if np.any((x < lower_bound) | (x > upper_bound)):
        raise ValueError("observations violate preregistered bounds")
    times = np.arange(1, len(x) + 1)
    cumulative = np.cumsum(x)
    means = cumulative / times
    cumulative_squares = np.cumsum(x**2)
    variance = np.divide(
        cumulative_squares - times * means**2,
        np.maximum(times - 1, 1),
    )
    alpha_t = alpha / (times * (times + 1))
    log_term = np.log(3 / alpha_t)
    width = upper_bound - lower_bound
    # Freedman's bounded-increment correction.  The prior factor of three was
    # safe but needlessly nine times looser than the standard 1/3 correction.
    radius = np.sqrt(2 * variance * log_term / times) + width * log_term / (3 * times)
    radius[0] = width
    lower, upper = means - radius, means + radius
    promoted = np.flatnonzero(lower > 0)
    return ConfidenceSequence(
        times=times,
        means=means,
        lower=lower,
        upper=upper,
        promoted_at=int(promoted[0] + 1) if len(promoted) else None,
    )
