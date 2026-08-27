from __future__ import annotations

import numpy as np


def risk_adjusted_utility(
    samples: np.ndarray, risk_aversion: float = 0.0, alpha: float = 0.1
) -> float:
    mean = float(np.mean(samples))
    cutoff = np.quantile(samples, alpha)
    downside = (
        float(np.mean(np.maximum(0, mean - samples[samples <= cutoff])))
        if np.any(samples <= cutoff)
        else 0.0
    )
    return mean - risk_aversion * downside


def expected_shortfall_lower(samples: np.ndarray, alpha: float = 0.1) -> float:
    """Mean profit in the lower alpha tail; lower values indicate worse downside."""
    if not 0 < alpha <= 1:
        raise ValueError("alpha must lie in (0, 1]")
    values = np.asarray(samples, dtype=float)
    if not values.size:
        raise ValueError("samples cannot be empty")
    cutoff = np.quantile(values, alpha)
    return float(np.mean(values[values <= cutoff]))


def downside_cvar_loss(samples: np.ndarray, alpha: float = 0.1) -> float:
    """Positive loss relative to zero in the lower tail of incremental profit."""
    tail_mean = expected_shortfall_lower(samples, alpha)
    return max(0.0, -tail_mean)


def contribution_profit_utility(
    incremental_profit_samples: np.ndarray,
    *,
    risk_aversion: float,
    alpha: float = 0.1,
) -> float:
    """Mean incremental CP minus lambda times lower-tail CVaR loss."""
    if risk_aversion < 0:
        raise ValueError("risk aversion cannot be negative")
    values = np.asarray(incremental_profit_samples, dtype=float)
    return float(np.mean(values) - risk_aversion * downside_cvar_loss(values, alpha))
