from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class CausalEstimator(ABC):
    @abstractmethod
    def fit(self, x: np.ndarray, treatment: np.ndarray, outcome: np.ndarray) -> CausalEstimator: ...

    @abstractmethod
    def effect(self, x: np.ndarray, treatment: int = 1, baseline: int = 0) -> np.ndarray: ...
