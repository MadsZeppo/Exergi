"""Reproducible V7.1 uplift challengers sharing one narrow fit/effect interface."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.tree import DecisionTreeRegressor


class EffectModel(Protocol):
    name: str

    def fit(
        self,
        x: np.ndarray,
        treatment: np.ndarray,
        outcome: np.ndarray,
        propensity: np.ndarray,
    ) -> EffectModel: ...

    def effect(self, x: np.ndarray) -> np.ndarray: ...


def _forest(seed: int, *, leaf: int = 30, depth: int | None = 7) -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=100,
        max_depth=depth,
        min_samples_leaf=leaf,
        random_state=seed,
        n_jobs=1,
    )


def _cross_fitted_outcomes(
    x: np.ndarray,
    treatment: np.ndarray,
    outcome: np.ndarray,
    *,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return honest nuisance predictions; no row is scored by its fitted nuisance model."""

    a = np.asarray(treatment, dtype=bool)
    prediction0 = np.empty(len(x), dtype=float)
    prediction1 = np.empty(len(x), dtype=float)
    folds = KFold(n_splits=3, shuffle=False)
    for fold, (train, holdout) in enumerate(folds.split(x)):
        train_a = a[train]
        if np.sum(train_a) < 2 or np.sum(~train_a) < 2:
            raise ValueError("cross-fit fold lacks both randomized arms")
        m0 = _forest(seed + 10 * fold + 1).fit(x[train][~train_a], outcome[train][~train_a])
        m1 = _forest(seed + 10 * fold + 2).fit(x[train][train_a], outcome[train][train_a])
        prediction0[holdout] = m0.predict(x[holdout])
        prediction1[holdout] = m1.predict(x[holdout])
    return prediction0, prediction1


def _dr_pseudo(
    x: np.ndarray,
    treatment: np.ndarray,
    outcome: np.ndarray,
    propensity: np.ndarray,
    *,
    seed: int,
) -> np.ndarray:
    a = np.asarray(treatment, dtype=bool)
    prediction0, prediction1 = _cross_fitted_outcomes(
        x, treatment, outcome, seed=seed
    )
    p = np.clip(propensity, 0.05, 0.95)
    pseudo = (
        prediction1
        - prediction0
        + a * (outcome - prediction1) / p
        - (~a) * (outcome - prediction0) / (1 - p)
    )
    return np.asarray(pseudo, dtype=float)


@dataclass
class TLearner:
    name: str
    seed: int
    forest: bool

    def fit(
        self,
        x: np.ndarray,
        treatment: np.ndarray,
        outcome: np.ndarray,
        propensity: np.ndarray,
    ) -> TLearner:
        del propensity
        a = np.asarray(treatment, dtype=bool)
        if self.forest:
            self.m0_ = _forest(self.seed + 1).fit(x[~a], outcome[~a])
            self.m1_ = _forest(self.seed + 2).fit(x[a], outcome[a])
        else:
            self.m0_ = Ridge(alpha=2.0).fit(x[~a], outcome[~a])
            self.m1_ = Ridge(alpha=2.0).fit(x[a], outcome[a])
        return self

    def effect(self, x: np.ndarray) -> np.ndarray:
        if not hasattr(self, "m0_") or not hasattr(self, "m1_"):
            raise RuntimeError("T-learner is not fitted")
        return np.asarray(self.m1_.predict(x) - self.m0_.predict(x), dtype=float)


@dataclass
class XLearner:
    name: str
    seed: int

    def fit(
        self,
        x: np.ndarray,
        treatment: np.ndarray,
        outcome: np.ndarray,
        propensity: np.ndarray,
    ) -> XLearner:
        a = np.asarray(treatment, dtype=bool)
        self.mean_propensity_ = float(np.mean(propensity))
        m0 = _forest(self.seed + 1).fit(x[~a], outcome[~a])
        m1 = _forest(self.seed + 2).fit(x[a], outcome[a])
        imputed_treated = outcome[a] - m0.predict(x[a])
        imputed_control = m1.predict(x[~a]) - outcome[~a]
        self.tau1_ = _forest(self.seed + 3, leaf=20).fit(x[a], imputed_treated)
        self.tau0_ = _forest(self.seed + 4, leaf=20).fit(x[~a], imputed_control)
        return self

    def effect(self, x: np.ndarray) -> np.ndarray:
        if not hasattr(self, "tau0_") or not hasattr(self, "tau1_"):
            raise RuntimeError("X-learner is not fitted")
        p = self.mean_propensity_
        return np.asarray(p * self.tau0_.predict(x) + (1 - p) * self.tau1_.predict(x))


@dataclass
class RLearner:
    name: str
    seed: int

    def fit(
        self,
        x: np.ndarray,
        treatment: np.ndarray,
        outcome: np.ndarray,
        propensity: np.ndarray,
    ) -> RLearner:
        folds = KFold(n_splits=3, shuffle=False)
        predicted_outcome = np.empty(len(x), dtype=float)
        for fold, (train, holdout) in enumerate(folds.split(x)):
            nuisance = _forest(self.seed + 10 * fold + 1).fit(x[train], outcome[train])
            predicted_outcome[holdout] = nuisance.predict(x[holdout])
        residual_outcome = outcome - predicted_outcome
        residual_treatment = treatment.astype(float) - propensity
        stable = np.abs(residual_treatment) >= 0.05
        pseudo = residual_outcome[stable] / residual_treatment[stable]
        weights = residual_treatment[stable] ** 2
        self.tau_ = _forest(self.seed + 2, leaf=25).fit(x[stable], pseudo, sample_weight=weights)
        return self

    def effect(self, x: np.ndarray) -> np.ndarray:
        if not hasattr(self, "tau_"):
            raise RuntimeError("R-learner is not fitted")
        return np.asarray(self.tau_.predict(x), dtype=float)


@dataclass
class DRLearner:
    name: str
    seed: int

    def fit(
        self,
        x: np.ndarray,
        treatment: np.ndarray,
        outcome: np.ndarray,
        propensity: np.ndarray,
    ) -> DRLearner:
        pseudo = _dr_pseudo(x, treatment, outcome, propensity, seed=self.seed)
        self.tau_ = _forest(self.seed + 3, leaf=30).fit(x, pseudo)
        return self

    def effect(self, x: np.ndarray) -> np.ndarray:
        if not hasattr(self, "tau_"):
            raise RuntimeError("DR-learner is not fitted")
        return np.asarray(self.tau_.predict(x), dtype=float)


@dataclass
class HonestPolicyTree:
    name: str
    seed: int

    def fit(
        self,
        x: np.ndarray,
        treatment: np.ndarray,
        outcome: np.ndarray,
        propensity: np.ndarray,
    ) -> HonestPolicyTree:
        pseudo = _dr_pseudo(x, treatment, outcome, propensity, seed=self.seed)
        self.tree_ = DecisionTreeRegressor(
            max_depth=2,
            min_samples_leaf=80,
            random_state=self.seed + 4,
        ).fit(x, pseudo)
        return self

    def effect(self, x: np.ndarray) -> np.ndarray:
        if not hasattr(self, "tree_"):
            raise RuntimeError("policy tree is not fitted")
        return np.asarray(self.tree_.predict(x), dtype=float)


@dataclass
class PredefinedSegmentModel:
    name: str
    seed: int

    @staticmethod
    def _masks(x: np.ndarray) -> tuple[np.ndarray, ...]:
        return (
            np.ones(len(x), dtype=bool),
            (x[:, 0] > 0.7) & (x[:, 3] > 0.3),
            x[:, 3] > 0.55,
            x[:, 4] > 0,
            (x[:, 3] + x[:, 4]) > 0.45,
            (x[:, 3] > 0.45) & (x[:, 4] > 0),
        )

    def fit(
        self,
        x: np.ndarray,
        treatment: np.ndarray,
        outcome: np.ndarray,
        propensity: np.ndarray,
    ) -> PredefinedSegmentModel:
        pseudo = _dr_pseudo(x, treatment, outcome, propensity, seed=self.seed)
        values = [float(np.mean(pseudo * mask)) for mask in self._masks(x)]
        self.selected_segment_ = int(np.argmax([0.0, *values])) - 1
        return self

    def effect(self, x: np.ndarray) -> np.ndarray:
        if not hasattr(self, "selected_segment_"):
            raise RuntimeError("segment policy is not fitted")
        if self.selected_segment_ < 0:
            return np.full(len(x), -1.0)
        mask = self._masks(x)[self.selected_segment_]
        return np.where(mask, 1.0, -1.0)


def candidate_models(seed: int) -> tuple[EffectModel, ...]:
    return (
        TLearner("ridge_t_learner", seed, False),
        TLearner("forest_t_learner", seed, True),
        XLearner("x_learner", seed),
        RLearner("r_learner", seed),
        DRLearner("dr_learner", seed),
        HonestPolicyTree("honest_policy_tree", seed),
        PredefinedSegmentModel("predefined_segment_policy", seed),
    )


def causal_forest_availability() -> dict[str, object]:
    available = importlib.util.find_spec("econml") is not None
    return {
        "candidate": "causal_forest_dml",
        "available": available,
        "status": "AVAILABLE_NOT_AUTO_SELECTED" if available else "NOT_INSTALLED",
        "reproducible_runtime": False if not available else "REQUIRES_SEPARATE_AUDIT",
    }
