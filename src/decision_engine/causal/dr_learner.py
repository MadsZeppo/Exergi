"""Cross-fitted doubly robust learner with an EconML implementation when available."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

from decision_engine.causal.base import CausalEstimator


@dataclass
class CrossFittedDRLearner(CausalEstimator):
    seed: int = 42
    cv: int = 3

    def fit(
        self, x: np.ndarray, treatment: np.ndarray, outcome: np.ndarray
    ) -> CrossFittedDRLearner:
        try:
            from econml.dr import DRLearner
        except ImportError as exc:
            raise ImportError("Install decision-engine[causal] to use DRLearner") from exc
        self.model_ = DRLearner(
            model_propensity=RandomForestClassifier(
                n_estimators=150, min_samples_leaf=10, random_state=self.seed
            ),
            model_regression=RandomForestRegressor(
                n_estimators=150, min_samples_leaf=10, random_state=self.seed
            ),
            model_final=RandomForestRegressor(
                n_estimators=150, min_samples_leaf=10, random_state=self.seed
            ),
            discrete_treatment=True,
            cv=self.cv,
            random_state=self.seed,
        )
        self.model_.fit(outcome, treatment, X=x)
        return self

    def effect(self, x: np.ndarray, treatment: int = 1, baseline: int = 0) -> np.ndarray:
        if not hasattr(self, "model_"):
            raise RuntimeError("estimator is not fitted")
        return np.asarray(self.model_.effect(x, T0=baseline, T1=treatment), dtype=float)
