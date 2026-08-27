from __future__ import annotations

import numpy as np


def ate_error(estimated_effect: np.ndarray, true_effect: np.ndarray) -> float:
    return float(abs(np.mean(estimated_effect) - np.mean(true_effect)))


def pehe(estimated_effect: np.ndarray, true_effect: np.ndarray) -> float:
    return float(np.sqrt(np.mean((estimated_effect - true_effect) ** 2)))
