from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class LightGBMPointForecast:
    seed: int = 42
    n_estimators: int = 300
    learning_rate: float = 0.05

    def fit(self, x: np.ndarray, y: np.ndarray) -> LightGBMPointForecast:
        from lightgbm import LGBMRegressor

        self.model_ = LGBMRegressor(
            objective="regression_l1",
            n_estimators=self.n_estimators,
            learning_rate=self.learning_rate,
            random_state=self.seed,
            deterministic=True,
            verbosity=-1,
        ).fit(x, y)
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        if not hasattr(self, "model_"):
            raise RuntimeError("model is not fitted")
        return np.asarray(self.model_.predict(x), dtype=float)
