"""Cross-fitted one-stage and hurdle outcome models for sparse monetary outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from sklearn.base import RegressorMixin, clone
from sklearn.ensemble import (
    ExtraTreesRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.linear_model import HuberRegressor, LogisticRegression, Ridge, TweedieRegressor
from sklearn.model_selection import KFold

from .contracts import FloatArray, IntArray


class ActionOutcomeModel(Protocol):
    name: str

    def fit(
        self, features: FloatArray, action: IntArray, outcome: FloatArray, arms: int
    ) -> None: ...

    def predict_actions(self, features: FloatArray) -> FloatArray: ...


@dataclass
class _ArmRegressor:
    name: str
    estimator: RegressorMixin
    models: list[RegressorMixin | float] | None = None

    def fit(self, features: FloatArray, action: IntArray, outcome: FloatArray, arms: int) -> None:
        fitted: list[RegressorMixin | float] = []
        for arm in range(arms):
            mask = action == arm
            if int(mask.sum()) < 3:
                fitted.append(float(np.mean(outcome[mask])) if np.any(mask) else 0.0)
                continue
            model = clone(self.estimator)
            model.fit(features[mask], outcome[mask])
            fitted.append(model)
        self.models = fitted

    def predict_actions(self, features: FloatArray) -> FloatArray:
        if self.models is None:
            raise RuntimeError("model is not fitted")
        columns = [
            np.full(len(features), model, dtype=float)
            if isinstance(model, float)
            else np.asarray(model.predict(features), dtype=float)
            for model in self.models
        ]
        return np.column_stack(columns).astype(float)


@dataclass
class _TwoPartRegressor:
    name: str = "two_part_logit_log_ridge"
    classifiers: list[LogisticRegression | float] | None = None
    positive_models: list[Ridge | float] | None = None
    smearing: list[float] | None = None

    def fit(self, features: FloatArray, action: IntArray, outcome: FloatArray, arms: int) -> None:
        classifiers: list[LogisticRegression | float] = []
        positives: list[Ridge | float] = []
        smearing: list[float] = []
        for arm in range(arms):
            mask = action == arm
            x_arm, y_arm = features[mask], np.maximum(outcome[mask], 0.0)
            bought = y_arm > 0
            if len(y_arm) < 4 or np.unique(bought).size < 2:
                classifiers.append(float(np.mean(bought)) if len(y_arm) else 0.0)
            else:
                classifier = LogisticRegression(max_iter=1_000, random_state=0)
                classifier.fit(x_arm, bought)
                classifiers.append(classifier)
            if int(bought.sum()) < 3:
                positives.append(float(np.mean(y_arm[bought])) if np.any(bought) else 0.0)
                smearing.append(1.0)
            else:
                transformed = np.log1p(y_arm[bought])
                model = Ridge(alpha=10.0)
                model.fit(x_arm[bought], transformed)
                residual = transformed - model.predict(x_arm[bought])
                positives.append(model)
                smearing.append(float(np.mean(np.exp(residual))))
        self.classifiers, self.positive_models, self.smearing = classifiers, positives, smearing

    def predict_actions(self, features: FloatArray) -> FloatArray:
        if self.classifiers is None or self.positive_models is None or self.smearing is None:
            raise RuntimeError("model is not fitted")
        columns: list[FloatArray] = []
        for classifier, positive, smear in zip(
            self.classifiers, self.positive_models, self.smearing, strict=True
        ):
            probability = (
                np.full(len(features), classifier)
                if isinstance(classifier, float)
                else classifier.predict_proba(features)[:, 1]
            )
            positive_mean = (
                np.full(len(features), positive)
                if isinstance(positive, float)
                else np.maximum(np.exp(positive.predict(features)) * smear - 1.0, 0.0)
            )
            columns.append(np.asarray(probability * positive_mean, dtype=float))
        return np.column_stack(columns)


@dataclass
class CrossFittedOutcomeModel:
    """Strict OOF nuisance predictions plus a full model for unseen holdouts."""

    base_model: ActionOutcomeModel
    folds: int = 5
    seed: int = 72_001
    full_model: ActionOutcomeModel | None = None
    fold_id_: IntArray | None = None

    @property
    def name(self) -> str:
        return self.base_model.name

    def fit_predict_oof(
        self, features: FloatArray, action: IntArray, outcome: FloatArray, arms: int
    ) -> FloatArray:
        if self.folds < 2 or self.folds > len(features):
            raise ValueError("cross-fitting requires between 2 and n folds")
        splitter = KFold(self.folds, shuffle=True, random_state=self.seed)
        predictions = np.empty((len(features), arms), dtype=float)
        fold_ids = np.full(len(features), -1, dtype=np.int64)
        for fold, (train, held_out) in enumerate(splitter.split(features)):
            model = clone_action_model(self.base_model)
            model.fit(features[train], action[train], outcome[train], arms)
            predictions[held_out] = model.predict_actions(features[held_out])
            fold_ids[held_out] = fold
        if np.any(fold_ids < 0) or not np.all(np.isfinite(predictions)):
            raise RuntimeError("cross-fitting did not produce finite OOF predictions")
        self.fold_id_ = fold_ids
        self.full_model = clone_action_model(self.base_model)
        self.full_model.fit(features, action, outcome, arms)
        return predictions

    def predict_actions(self, features: FloatArray) -> FloatArray:
        if self.full_model is None:
            raise RuntimeError("cross-fitted model is not fitted")
        return self.full_model.predict_actions(features)


def clone_action_model(model: ActionOutcomeModel) -> ActionOutcomeModel:
    if isinstance(model, _ArmRegressor):
        return _ArmRegressor(model.name, clone(model.estimator))
    if isinstance(model, _TwoPartRegressor):
        return _TwoPartRegressor(model.name)
    raise TypeError(f"unsupported action model: {type(model)!r}")


def model_candidates(seed: int = 72_001) -> tuple[ActionOutcomeModel, ...]:
    return (
        _ArmRegressor("ridge_t", Ridge(alpha=10.0)),
        _ArmRegressor(
            "random_forest_t",
            RandomForestRegressor(
                n_estimators=160,
                min_samples_leaf=30,
                max_features=0.8,
                n_jobs=-1,
                random_state=seed,
            ),
        ),
        _ArmRegressor(
            "extra_trees_t",
            ExtraTreesRegressor(
                n_estimators=160,
                min_samples_leaf=30,
                max_features=0.8,
                n_jobs=-1,
                random_state=seed,
            ),
        ),
        _ArmRegressor(
            "hist_gradient_t",
            HistGradientBoostingRegressor(
                max_iter=160,
                max_leaf_nodes=15,
                l2_regularization=2.0,
                random_state=seed,
            ),
        ),
        _ArmRegressor(
            "tweedie_t", TweedieRegressor(power=1.5, alpha=1.0, link="log", max_iter=1_000)
        ),
        _ArmRegressor("huber_t", HuberRegressor(epsilon=1.5, alpha=1.0, max_iter=1_000)),
        _TwoPartRegressor(),
    )
