from __future__ import annotations

import numpy as np


def interval_coverage(y: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    if not (y.shape == lower.shape == upper.shape):
        raise ValueError("arrays must have equal shapes")
    return float(np.mean((y >= lower) & (y <= upper)))


def calibration_report(
    y: np.ndarray, intervals: dict[str, tuple[np.ndarray, np.ndarray]]
) -> dict[str, dict[str, float]]:
    return {
        name: {
            "coverage": interval_coverage(y, bounds[0], bounds[1]),
            "average_width": float(np.mean(bounds[1] - bounds[0])),
        }
        for name, bounds in intervals.items()
    }
