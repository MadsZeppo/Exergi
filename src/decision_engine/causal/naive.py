from __future__ import annotations

import numpy as np


def difference_in_means(
    treatment: np.ndarray, outcome: np.ndarray, action: int = 1, baseline: int = 0
) -> float:
    treated = outcome[treatment == action]
    control = outcome[treatment == baseline]
    if not treated.size or not control.size:
        raise ValueError("both treatment groups require observations")
    return float(treated.mean() - control.mean())
