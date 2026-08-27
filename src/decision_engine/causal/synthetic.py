from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import expit


@dataclass(frozen=True)
class SyntheticCausalData:
    x: np.ndarray
    treatment: np.ndarray
    outcome: np.ndarray
    true_effect: np.ndarray
    propensity: np.ndarray


def generate_confounded_treatment_data(n: int = 5000, seed: int = 42) -> SyntheticCausalData:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.binomial(1, 0.5, size=n)
    propensity = expit(0.8 * x1 - 0.6 * x2)
    treatment = rng.binomial(1, propensity)
    true_effect = 5 + 2 * x1
    outcome = 10 + 2 * x1 + 3 * x2 + treatment * true_effect + rng.normal(size=n)
    return SyntheticCausalData(
        np.column_stack([x1, x2]), treatment, outcome, true_effect, propensity
    )
