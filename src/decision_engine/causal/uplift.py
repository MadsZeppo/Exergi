from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier


class UpliftModel(Protocol):
    def fit(self, x: np.ndarray, treatment: np.ndarray, outcome: np.ndarray) -> UpliftModel: ...

    def predict_uplift(self, x: np.ndarray) -> np.ndarray: ...


@dataclass
class TLearnerUplift:
    seed: int = 42

    def fit(
        self, x: np.ndarray, treatment: np.ndarray, outcome: np.ndarray
    ) -> TLearnerUplift:
        base = HistGradientBoostingClassifier(
            max_iter=100, max_leaf_nodes=15, min_samples_leaf=30, random_state=self.seed
        )
        self.treated_ = clone(base).fit(x[treatment == 1], outcome[treatment == 1])
        self.control_ = clone(base).fit(x[treatment == 0], outcome[treatment == 0])
        return self

    def predict_uplift(self, x: np.ndarray) -> np.ndarray:
        return self.treated_.predict_proba(x)[:, 1] - self.control_.predict_proba(x)[:, 1]


def uplift_curve_metrics(
    outcome: np.ndarray, treatment: np.ndarray, uplift: np.ndarray
) -> dict[str, float]:
    order = np.argsort(-uplift, kind="stable")
    y = np.asarray(outcome, dtype=float)[order]
    t = np.asarray(treatment, dtype=int)[order]
    treated_count = np.cumsum(t)
    control_count = np.cumsum(1 - t)
    treated_outcome = np.cumsum(y * t)
    control_outcome = np.cumsum(y * (1 - t))
    expected_control = control_outcome * treated_count / np.maximum(control_count, 1)
    gain = treated_outcome - expected_control
    fraction = np.arange(1, len(y) + 1) / len(y)
    auuc = float(np.trapezoid(gain / max(len(y), 1), fraction))
    random_line = fraction * gain[-1]
    qini = float(np.trapezoid((gain - random_line) / max(len(y), 1), fraction))
    return {"auuc": auuc, "qini": qini, "final_incremental_conversions": float(gain[-1])}
