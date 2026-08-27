from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class RollingConformalCalibrator:
    """Chronological split conformal adjustment; evaluation outcomes must never enter fit."""

    miscoverage: float = 0.2
    max_window: int = 56

    def fit(
        self, y_cal: np.ndarray, lower_cal: np.ndarray, upper_cal: np.ndarray
    ) -> RollingConformalCalibrator:
        if not (y_cal.shape == lower_cal.shape == upper_cal.shape):
            raise ValueError("calibration arrays must have equal shapes")
        scores = np.maximum(lower_cal - y_cal, y_cal - upper_cal)[-self.max_window :]
        if not scores.size:
            raise ValueError("empty calibration window")
        level = min(1.0, (1 - self.miscoverage) * (1 + 1 / scores.size))
        self.adjustment_ = float(np.quantile(scores, level, method="higher"))
        return self

    def transform(self, lower: np.ndarray, upper: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if not hasattr(self, "adjustment_"):
            raise RuntimeError("calibrator is not fitted")
        return lower - max(0, self.adjustment_), upper + max(0, self.adjustment_)
