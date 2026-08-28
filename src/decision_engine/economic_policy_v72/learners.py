"""Development challengers for randomized multi-arm economic policy learning."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.base import RegressorMixin, clone
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.tree import DecisionTreeRegressor

from .contracts import FloatArray, IntArray
from .models import CrossFittedOutcomeModel, _ArmRegressor


@dataclass
class DRPseudoOutcomeModel:
    """Known-propensity DR learner with swappable final-stage policy model."""

    name: str
    final_estimator: RegressorMixin
    folds: int = 5
    seed: int = 72_001
    propensity: float = 0.125
    nuisance_: CrossFittedOutcomeModel | None = None
    final_: RegressorMixin | None = None

    def fit(self, features: FloatArray, action: IntArray, outcome: FloatArray, arms: int) -> None:
        nuisance = CrossFittedOutcomeModel(
            _ArmRegressor("dr_nuisance_ridge_t", Ridge(alpha=10.0)),
            folds=self.folds,
            seed=self.seed,
        )
        oof = nuisance.fit_predict_oof(features, action, outcome, arms)
        pseudo = oof.copy()
        rows = np.arange(len(action))
        pseudo[rows, action] += (outcome - oof[rows, action]) / self.propensity
        final = clone(self.final_estimator)
        final.fit(features, pseudo)
        self.nuisance_, self.final_ = nuisance, final

    def predict_actions(self, features: FloatArray) -> FloatArray:
        if self.final_ is None:
            raise RuntimeError("DR learner is not fitted")
        return np.asarray(self.final_.predict(features), dtype=float)


@dataclass
class XLearnerModel:
    """Multi-arm X learner, fitting each active arm against the BAU arm."""

    name: str = "x_learner_ridge"
    folds: int = 5
    seed: int = 72_001
    bau_action: int = 7
    nuisance_: CrossFittedOutcomeModel | None = None
    treated_models_: list[Ridge | None] | None = None
    control_models_: list[Ridge | None] | None = None

    def fit(self, features: FloatArray, action: IntArray, outcome: FloatArray, arms: int) -> None:
        nuisance = CrossFittedOutcomeModel(
            _ArmRegressor("x_nuisance_ridge_t", Ridge(alpha=10.0)),
            folds=self.folds,
            seed=self.seed,
        )
        oof = nuisance.fit_predict_oof(features, action, outcome, arms)
        treated: list[Ridge | None] = []
        controls: list[Ridge | None] = []
        control_mask = action == self.bau_action
        for arm in range(arms):
            if arm == self.bau_action:
                treated.append(None)
                controls.append(None)
                continue
            arm_mask = action == arm
            treated_model = Ridge(alpha=10.0).fit(
                features[arm_mask], outcome[arm_mask] - oof[arm_mask, self.bau_action]
            )
            control_model = Ridge(alpha=10.0).fit(
                features[control_mask], oof[control_mask, arm] - outcome[control_mask]
            )
            treated.append(treated_model)
            controls.append(control_model)
        self.nuisance_ = nuisance
        self.treated_models_ = treated
        self.control_models_ = controls

    def predict_actions(self, features: FloatArray) -> FloatArray:
        if (
            self.nuisance_ is None
            or self.treated_models_ is None
            or self.control_models_ is None
        ):
            raise RuntimeError("X learner is not fitted")
        base = self.nuisance_.predict_actions(features)
        prediction = base.copy()
        for arm, (treated, control) in enumerate(
            zip(self.treated_models_, self.control_models_, strict=True)
        ):
            if arm == self.bau_action:
                continue
            if treated is None or control is None:
                raise RuntimeError("X learner arm model is missing")
            effect = 0.5 * (treated.predict(features) + control.predict(features))
            prediction[:, arm] = base[:, self.bau_action] + effect
        return np.asarray(prediction, dtype=float)


@dataclass
class RLearnerModel:
    """Pairwise randomized R learner with an OOF pooled outcome nuisance."""

    name: str = "r_learner_ridge"
    folds: int = 5
    seed: int = 72_001
    bau_action: int = 7
    baseline_: Ridge | None = None
    effects_: list[Ridge | None] | None = None

    def fit(self, features: FloatArray, action: IntArray, outcome: FloatArray, arms: int) -> None:
        splitter = KFold(self.folds, shuffle=True, random_state=self.seed)
        oof = np.empty(len(outcome), dtype=float)
        for train, held_out in splitter.split(features):
            model = Ridge(alpha=10.0).fit(features[train], outcome[train])
            oof[held_out] = model.predict(features[held_out])
        control_mask = action == self.bau_action
        baseline = Ridge(alpha=10.0).fit(features[control_mask], outcome[control_mask])
        effects: list[Ridge | None] = []
        for arm in range(arms):
            if arm == self.bau_action:
                effects.append(None)
                continue
            pair = (action == arm) | (action == self.bau_action)
            centered_treatment = (action[pair] == arm).astype(float) - 0.5
            pseudo = (outcome[pair] - oof[pair]) / centered_treatment
            effects.append(Ridge(alpha=10.0).fit(features[pair], pseudo))
        self.baseline_, self.effects_ = baseline, effects

    def predict_actions(self, features: FloatArray) -> FloatArray:
        if self.baseline_ is None or self.effects_ is None:
            raise RuntimeError("R learner is not fitted")
        control = self.baseline_.predict(features)
        result = np.tile(control[:, None], (1, len(self.effects_)))
        for arm, model in enumerate(self.effects_):
            if model is not None:
                result[:, arm] = control + model.predict(features)
        return np.asarray(result, dtype=float)


def causal_challengers(
    seed: int = 72_001,
    bau_action: int = 7,
) -> tuple[XLearnerModel | RLearnerModel | DRPseudoOutcomeModel, ...]:
    return (
        XLearnerModel(seed=seed, bau_action=bau_action),
        RLearnerModel(seed=seed, bau_action=bau_action),
        DRPseudoOutcomeModel("dr_learner_ridge", Ridge(alpha=10.0), seed=seed),
        DRPseudoOutcomeModel(
            "causal_forest_dr",
            RandomForestRegressor(
                n_estimators=200,
                min_samples_leaf=500,
                max_features=1.0,
                n_jobs=-1,
                random_state=seed,
            ),
            seed=seed,
        ),
        DRPseudoOutcomeModel(
            "honest_dr_policy_tree",
            DecisionTreeRegressor(max_depth=3, min_samples_leaf=5_000, random_state=seed),
            seed=seed,
        ),
    )
