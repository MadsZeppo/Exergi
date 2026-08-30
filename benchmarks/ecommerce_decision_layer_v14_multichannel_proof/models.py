from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
from lightgbm import LGBMRegressor
from scipy.stats import norm
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.tree import DecisionTreeRegressor

from .observed import ACTION_NAMES

FOLDS = 5
MODEL_SEED = 141_001


@dataclass(frozen=True)
class ObservedTrainingData:
    features: np.ndarray
    outcome: np.ndarray
    gross_revenue: np.ndarray
    assignment: np.ndarray
    logged_propensity: np.ndarray
    candidate_propensity: np.ndarray
    eligible_actions: np.ndarray
    cost_complete: np.ndarray
    data_valid: np.ndarray
    customer_ids: np.ndarray
    merchant_ids: np.ndarray
    merchant_families: np.ndarray
    weeks: np.ndarray
    maturity_weeks: np.ndarray

    def subset(self, rows: np.ndarray) -> ObservedTrainingData:
        return ObservedTrainingData(
            **{
                name: getattr(self, name)[rows]
                for name in self.__dataclass_fields__
            }
        )


@dataclass(frozen=True)
class Estimate:
    point: float
    standard_error: float
    lower_95: float
    upper_95: float
    p_value_two_sided: float


@dataclass(frozen=True)
class TournamentPredictions:
    effects: dict[str, np.ndarray]
    nuisance_outcome: np.ndarray
    action_standard_errors: np.ndarray
    fold_ids: np.ndarray


def customer_fold(customer_ids: np.ndarray) -> np.ndarray:
    output = np.empty(len(customer_ids), dtype=np.int8)
    for index, value in enumerate(customer_ids):
        digest = hashlib.sha256(str(value).encode()).digest()
        output[index] = digest[0] % FOLDS
    return output


def _ridge() -> Ridge:
    return Ridge(alpha=20.0, solver="lsqr")


def _lgbm(seed: int) -> LGBMRegressor:
    return LGBMRegressor(
        colsample_bytree=0.8,
        deterministic=True,
        learning_rate=0.04,
        max_depth=3,
        min_child_samples=100,
        n_estimators=60,
        n_jobs=1,
        num_leaves=15,
        random_state=seed,
        reg_lambda=10.0,
        subsample=0.8,
        subsample_freq=1,
        verbosity=-1,
    )


def _fit_arm_models(
    x: np.ndarray,
    y: np.ndarray,
    assignment: np.ndarray,
    factory: Any,
) -> list[Any]:
    models: list[Any] = []
    for action in range(len(ACTION_NAMES)):
        rows = assignment == action
        if rows.sum() < 20:
            raise RuntimeError(f"insufficient V14 training rows for action {action}")
        models.append(factory(action).fit(x[rows], y[rows]))
    return models


def _predict_arms(models: list[Any], x: np.ndarray) -> np.ndarray:
    return np.column_stack([model.predict(x) for model in models])


def _cross_fitted_linear_nuisance(data: ObservedTrainingData) -> np.ndarray:
    folds = customer_fold(data.customer_ids)
    predictions = np.empty((len(data.outcome), len(ACTION_NAMES)))
    for fold in range(FOLDS):
        train = folds != fold
        test = ~train
        models = _fit_arm_models(
            data.features[train],
            data.outcome[train],
            data.assignment[train],
            lambda _action: _ridge(),
        )
        predictions[test] = _predict_arms(models, data.features[test])
    return predictions


def _hajek_action_means(data: ObservedTrainingData) -> np.ndarray:
    means = np.empty(len(ACTION_NAMES))
    for action in range(len(ACTION_NAMES)):
        rows = data.assignment == action
        weights = 1 / data.logged_propensity[rows]
        means[action] = np.sum(weights * data.outcome[rows]) / np.sum(weights)
    return means


def _segment_effects(train: ObservedTrainingData, test_x: np.ndarray) -> np.ndarray:
    train_segment = (
        (train.features[:, 12] > 0.5).astype(int)
        + 2 * (train.features[:, 13] > 0.5).astype(int)
        + 4 * (train.features[:, 11] > 0.45).astype(int)
    )
    test_segment = (
        (test_x[:, 12] > 0.5).astype(int)
        + 2 * (test_x[:, 13] > 0.5).astype(int)
        + 4 * (test_x[:, 11] > 0.45).astype(int)
    )
    global_means = _hajek_action_means(train)
    output = np.empty((len(test_x), len(ACTION_NAMES)))
    for segment in range(8):
        target = test_segment == segment
        source = train_segment == segment
        means = global_means.copy()
        for action in range(len(ACTION_NAMES)):
            rows = source & (train.assignment == action)
            if rows.sum() >= 100:
                weights = 1 / train.logged_propensity[rows]
                means[action] = np.sum(weights * train.outcome[rows]) / np.sum(weights)
        output[target] = means - means[0]
    return output


def fit_tournament(
    train: ObservedTrainingData, test: ObservedTrainingData
) -> TournamentPredictions:
    nuisance_oof = _cross_fitted_linear_nuisance(train)
    linear_models = _fit_arm_models(
        train.features,
        train.outcome,
        train.assignment,
        lambda _action: _ridge(),
    )
    nuisance_test = _predict_arms(linear_models, test.features)
    linear_effect = nuisance_test - nuisance_test[:, [0]]

    tree_models = _fit_arm_models(
        train.features,
        train.outcome,
        train.assignment,
        lambda action: DecisionTreeRegressor(
            max_depth=5,
            min_samples_leaf=100,
            random_state=MODEL_SEED + action,
        ),
    )
    tree_outcome = _predict_arms(tree_models, test.features)
    tree_effect = tree_outcome - tree_outcome[:, [0]]

    forest_models = _fit_arm_models(
        train.features,
        train.outcome,
        train.assignment,
        lambda action: RandomForestRegressor(
            n_estimators=30,
            max_depth=7,
            min_samples_leaf=80,
            n_jobs=1,
            random_state=MODEL_SEED + 100 + action,
        ),
    )
    forest_outcome = _predict_arms(forest_models, test.features)
    forest_effect = forest_outcome - forest_outcome[:, [0]]

    static_means = _hajek_action_means(train)
    static_effect = np.broadcast_to(static_means - static_means[0], nuisance_test.shape).copy()
    segment_effect = _segment_effects(train, test.features)

    x_effect = np.zeros_like(nuisance_test)
    r_effect = np.zeros_like(nuisance_test)
    dr_effect = np.zeros_like(nuisance_test)
    causal_forest = np.zeros_like(nuisance_test)
    action_se = np.zeros(len(ACTION_NAMES))
    m0 = nuisance_oof[:, 0]
    for action in range(1, len(ACTION_NAMES)):
        ma = nuisance_oof[:, action]
        dr_pseudo = (
            ma
            - m0
            + (train.assignment == action)
            * (train.outcome - ma)
            / train.logged_propensity
            - (train.assignment == 0)
            * (train.outcome - m0)
            / train.logged_propensity
        )
        dr_model = _lgbm(MODEL_SEED + 200 + action).fit(train.features, dr_pseudo)
        dr_effect[:, action] = dr_model.predict(test.features)
        causal_model = ExtraTreesRegressor(
            n_estimators=30,
            max_depth=7,
            min_samples_leaf=80,
            n_jobs=1,
            random_state=MODEL_SEED + 300 + action,
        ).fit(train.features, dr_pseudo)
        causal_forest[:, action] = causal_model.predict(test.features)
        action_se[action] = float(np.std(dr_pseudo, ddof=1) / np.sqrt(len(dr_pseudo)))

        binary = (train.assignment == 0) | (train.assignment == action)
        treated = train.assignment[binary] == action
        x_pseudo = np.where(
            treated,
            train.outcome[binary] - m0[binary],
            ma[binary] - train.outcome[binary],
        )
        x_effect[:, action] = _ridge().fit(train.features[binary], x_pseudo).predict(test.features)

        denominator = (
            train.candidate_propensity[binary, action]
            + train.candidate_propensity[binary, 0]
        )
        propensity = np.divide(
            train.candidate_propensity[binary, action],
            denominator,
            out=np.full(binary.sum(), 0.5),
            where=denominator > 0,
        )
        pooled = propensity * ma[binary] + (1 - propensity) * m0[binary]
        residual_treatment = treated.astype(float) - propensity
        valid = np.abs(residual_treatment) >= 0.02
        r_pseudo = (train.outcome[binary][valid] - pooled[valid]) / residual_treatment[valid]
        r_weight = np.square(residual_treatment[valid])
        r_effect[:, action] = _ridge().fit(
            train.features[binary][valid],
            r_pseudo,
            sample_weight=r_weight,
        ).predict(test.features)

    effects = {
        "BEST_STATIC": static_effect,
        "RULE_SEGMENT_POLICY": segment_effect,
        "REGULARIZED_LINEAR_T_LEARNER": linear_effect,
        "TREE_T_LEARNER": tree_effect,
        "FOREST_T_LEARNER": forest_effect,
        "X_LEARNER": x_effect,
        "R_LEARNER": r_effect,
        "DR_LEARNER": dr_effect,
        "CAUSAL_FOREST_EQUIVALENT": causal_forest,
        "CONSERVATIVE_ENSEMBLE": np.median(
            np.stack([linear_effect, dr_effect, causal_forest]), axis=0
        ),
    }
    return TournamentPredictions(
        effects=effects,
        nuisance_outcome=nuisance_test,
        action_standard_errors=action_se,
        fold_ids=customer_fold(test.customer_ids),
    )


def policy_from_effects(
    effects: np.ndarray,
    data: ObservedTrainingData,
    family_materiality: dict[str, float],
) -> np.ndarray:
    allowed = (
        data.eligible_actions
        & data.cost_complete
        & (data.candidate_propensity >= 0.02)
        & data.data_valid[:, None]
    )
    constrained = np.where(allowed, effects, -np.inf)
    constrained[:, 0] = 0.0
    policy = np.argmax(constrained, axis=1).astype(np.int8)
    thresholds = np.asarray([family_materiality[str(value)] for value in data.merchant_families])
    best = constrained[np.arange(len(policy)), policy]
    policy[best <= thresholds] = 0
    return policy


def _hajek_value(policy: np.ndarray, data: ObservedTrainingData) -> tuple[float, np.ndarray]:
    match = policy == data.assignment
    weight = match / data.logged_propensity
    denominator = float(weight.mean())
    value = float(np.mean(weight * data.outcome) / denominator)
    influence = weight * (data.outcome - value) / denominator
    return value, influence


def _estimate(point: float, influence: np.ndarray) -> Estimate:
    standard_error = float(np.std(influence, ddof=1) / np.sqrt(len(influence)))
    lower = point - float(norm.ppf(0.975)) * standard_error
    upper = point + float(norm.ppf(0.975)) * standard_error
    z = abs(point / standard_error) if standard_error > 0 else float("inf")
    return Estimate(point, standard_error, lower, upper, float(2 * norm.sf(z)))


def evaluate_policy(
    policy: np.ndarray,
    comparator: np.ndarray,
    data: ObservedTrainingData,
    nuisance: np.ndarray,
) -> dict[str, Estimate | np.ndarray]:
    policy_value, policy_if = _hajek_value(policy, data)
    comparator_value, comparator_if = _hajek_value(comparator, data)
    ipw = _estimate(policy_value - comparator_value, policy_if - comparator_if)
    rows = np.arange(len(policy))
    observed_prediction = nuisance[rows, data.assignment]
    policy_score = nuisance[rows, policy] + (policy == data.assignment) * (
        data.outcome - observed_prediction
    ) / data.logged_propensity
    comparator_score = nuisance[rows, comparator] + (comparator == data.assignment) * (
        data.outcome - observed_prediction
    ) / data.logged_propensity
    difference = policy_score - comparator_score
    dr = _estimate(float(np.mean(difference)), difference - np.mean(difference))
    return {"hajek_ipw": ipw, "doubly_robust": dr, "dr_rows": difference}
