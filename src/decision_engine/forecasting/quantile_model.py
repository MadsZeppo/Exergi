from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def repair_crossing_quantiles(predictions: np.ndarray) -> tuple[np.ndarray, float]:
    """Sort each row (isotonic under equal weights) and report pre-repair crossing rate."""
    if predictions.ndim != 2:
        raise ValueError("predictions must be observations x quantiles")
    crossed = np.any(np.diff(predictions, axis=1) < 0, axis=1)
    return np.sort(predictions, axis=1), float(np.mean(crossed))


@dataclass
class LightGBMQuantileForecast:
    quantiles: tuple[float, ...] = (0.1, 0.5, 0.9)
    seed: int = 42

    def fit(self, x: np.ndarray, y: np.ndarray) -> LightGBMQuantileForecast:
        from lightgbm import LGBMRegressor

        self.models_ = []
        for quantile in self.quantiles:
            model = LGBMRegressor(
                objective="quantile",
                alpha=quantile,
                n_estimators=300,
                learning_rate=0.05,
                random_state=self.seed,
                deterministic=True,
                verbosity=-1,
            ).fit(x, y)
            self.models_.append(model)
        return self

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, float]:
        if not hasattr(self, "models_"):
            raise RuntimeError("model is not fitted")
        raw = np.column_stack([model.predict(x) for model in self.models_])
        return repair_crossing_quantiles(raw)
