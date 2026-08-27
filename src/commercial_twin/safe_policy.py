"""Safe customer-level policy learning from randomized commerce experiments."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.base import clone
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold
from sklearn.tree import DecisionTreeRegressor


@dataclass(frozen=True)
class PolicyDiagnostics:
    value: float
    standard_error: float
    lower: float
    upper: float
    effective_sample_size: float
    clipped_fraction: float
    autoc: float
    autoc_lower: float
    heterogeneity_supported: bool
    promoted: bool


class SafeDRPolicyLearner:
    """Cross-fitted DR scores plus a shallow interpretable welfare tree.

    Propensities must come from randomized assignment. Control is action zero and
    is always available. Promotion requires a positive held-out lower confidence
    bound; otherwise ``predict`` returns control.
    """

    def __init__(
        self,
        *,
        max_depth: int = 3,
        min_leaf: int = 80,
        folds: int = 3,
        propensity_floor: float = 0.05,
        seed: int = 941,
    ) -> None:
        self.max_depth = max_depth
        self.min_leaf = min_leaf
        self.folds = folds
        self.propensity_floor = propensity_floor
        self.seed = seed
        self.models_: dict[int, DecisionTreeRegressor] = {}
        self.actions_: np.ndarray | None = None
        self.diagnostics_: PolicyDiagnostics | None = None

    def fit(
        self,
        x: np.ndarray,
        action: np.ndarray,
        outcome: np.ndarray,
        propensity: np.ndarray,
    ) -> SafeDRPolicyLearner:
        x = np.asarray(x, dtype=float)
        action = np.asarray(action, dtype=int)
        outcome = np.asarray(outcome, dtype=float)
        propensity = np.asarray(propensity, dtype=float)
        if len(x) != len(action) or len(x) < max(3 * self.min_leaf, 120):
            raise ValueError("insufficient randomized observations")
        actions = np.unique(action)
        if 0 not in actions or len(actions) < 2:
            raise ValueError("control and at least one treatment are required")
        clipped = np.maximum(propensity, self.propensity_floor)
        gamma = np.zeros((len(x), len(actions)))
        folds = KFold(n_splits=self.folds, shuffle=True, random_state=self.seed)
        base = RandomForestRegressor(
            n_estimators=40, min_samples_leaf=max(15, self.min_leaf // 4), random_state=self.seed
        )
        for train, test in folds.split(x):
            for column, candidate in enumerate(actions):
                mask = action[train] == candidate
                if np.sum(mask) < 20:
                    mu = np.full(len(test), np.mean(outcome[train]))
                else:
                    model = clone(base).set_params(random_state=self.seed + int(candidate))
                    model.fit(x[train][mask], outcome[train][mask])
                    mu = model.predict(x[test])
                residual = (action[test] == candidate) * (outcome[test] - mu) / clipped[test]
                gamma[test, column] = mu + residual
        control_col = int(np.where(actions == 0)[0][0])
        delta = gamma - gamma[:, [control_col]]
        # Honest split: trees train on one half; promotion/value uses the other.
        rng = np.random.default_rng(self.seed)
        order = rng.permutation(len(x))
        cut = len(x) // 2
        train, evaluate = order[:cut], order[cut:]
        predicted = np.zeros((len(evaluate), len(actions)))
        for column, candidate in enumerate(actions):
            if candidate == 0:
                continue
            tree = DecisionTreeRegressor(
                max_depth=self.max_depth,
                min_samples_leaf=self.min_leaf,
                random_state=self.seed + int(candidate),
            )
            tree.fit(x[train], delta[train, column])
            self.models_[int(candidate)] = tree
            predicted[:, column] = tree.predict(x[evaluate])
        choice_col = np.argmax(predicted, axis=1)
        chosen_delta = delta[evaluate, choice_col]
        value = float(np.mean(chosen_delta))
        se = float(np.std(chosen_delta, ddof=1) / np.sqrt(len(chosen_delta)))
        lower, upper = value - 1.96 * se, value + 1.96 * se
        priorities = np.max(predicted[:, actions != 0], axis=1)
        centered = delta[evaluate, choice_col] - np.mean(delta[evaluate, choice_col])
        ranks = (np.argsort(np.argsort(priorities)) + 1) / len(priorities)
        autoc_values = centered * (2 * ranks - 1)
        autoc = float(np.mean(autoc_values))
        autoc_se = float(np.std(autoc_values, ddof=1) / np.sqrt(len(autoc_values)))
        weights = 1 / clipped
        ess = float(np.sum(weights) ** 2 / np.sum(weights**2))
        heterogeneity = autoc - 1.96 * autoc_se > 0
        self.actions_ = actions
        self.diagnostics_ = PolicyDiagnostics(
            value=value,
            standard_error=se,
            lower=lower,
            upper=upper,
            effective_sample_size=ess,
            clipped_fraction=float(np.mean(propensity < self.propensity_floor)),
            autoc=autoc,
            autoc_lower=autoc - 1.96 * autoc_se,
            heterogeneity_supported=heterogeneity,
            promoted=lower > 0,
        )
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self.actions_ is None or self.diagnostics_ is None:
            raise RuntimeError("policy has not been fitted")
        if not self.diagnostics_.promoted:
            return np.zeros(len(x), dtype=np.int8)
        scores = np.zeros((len(x), len(self.actions_)))
        for column, candidate in enumerate(self.actions_):
            if candidate != 0:
                scores[:, column] = self.models_[int(candidate)].predict(x)
        # No personalization without demonstrated heterogeneity: use only a
        # positive population action, otherwise Control.
        if not self.diagnostics_.heterogeneity_supported:
            means = scores.mean(axis=0)
            chosen = int(np.argmax(means))
            return np.full(len(x), self.actions_[chosen] if means[chosen] > 0 else 0, dtype=np.int8)
        return self.actions_[np.argmax(scores, axis=1)].astype(np.int8)

    def score_actions(self, x: np.ndarray) -> np.ndarray:
        """Return estimated incremental welfare by fitted action (Control is zero)."""
        if self.actions_ is None:
            raise RuntimeError("policy has not been fitted")
        scores = np.zeros((len(x), len(self.actions_)))
        for column, candidate in enumerate(self.actions_):
            if candidate != 0:
                scores[:, column] = self.models_[int(candidate)].predict(x)
        return scores
