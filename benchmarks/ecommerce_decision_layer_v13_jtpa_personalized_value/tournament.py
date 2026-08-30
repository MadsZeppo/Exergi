from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeRegressor

from .generate_timing_dictionary import POLICY_ALLOWLIST
from .materialize import DEVELOPMENT_ACCESS, development_frame
from .qualification import ROOT

PROPENSITY = 2.0 / 3.0
FOLDS = 5
PRIMARY_SEED = 1301
FEATURES = tuple(sorted(POLICY_ALLOWLIST))
MODEL_RESULTS = ROOT / "V13_MODEL_TOURNAMENT.json"


@dataclass(frozen=True)
class Estimate:
    point: float
    standard_error: float
    lower_95: float
    upper_95: float
    p_value_two_sided: float


def estimate_from_influence(point: float, influence: np.ndarray) -> Estimate:
    standard_error = float(np.std(influence, ddof=1) / np.sqrt(len(influence)))
    lower = point - float(norm.ppf(0.975)) * standard_error
    upper = point + float(norm.ppf(0.975)) * standard_error
    z = abs(point / standard_error) if standard_error > 0 else float("inf")
    return Estimate(
        point=float(point),
        standard_error=standard_error,
        lower_95=float(lower),
        upper_95=float(upper),
        p_value_two_sided=float(2 * norm.sf(z)),
    )


def encoder() -> OneHotEncoder:
    return OneHotEncoder(
        dtype=np.float32,
        handle_unknown="infrequent_if_exist",
        max_categories=64,
        min_frequency=25,
    )


def feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(FEATURES) - set(frame.columns)
    if missing:
        raise RuntimeError(f"missing V13 policy features: {sorted(missing)}")
    return frame.loc[:, FEATURES].fillna("<NA>").astype(str)


def lgbm(seed: int) -> LGBMRegressor:
    return LGBMRegressor(
        colsample_bytree=0.8,
        deterministic=True,
        learning_rate=0.03,
        max_depth=3,
        min_child_samples=100,
        n_estimators=80,
        n_jobs=1,
        num_leaves=15,
        random_state=seed,
        reg_lambda=10.0,
        subsample=0.8,
        subsample_freq=1,
        verbosity=-1,
    )


def folds_for(frame: pd.DataFrame, seed: int, folds: int = FOLDS) -> np.ndarray:
    labels = frame["site"].astype(str) + "_" + frame["treatment"].astype(str)
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    output = np.empty(len(frame), dtype=np.int8)
    for fold, (_, test) in enumerate(splitter.split(np.zeros(len(frame)), labels)):
        output[test] = fold
    return output


def _fit_arm_models(
    matrix: Any,
    y: np.ndarray,
    treatment: np.ndarray,
    seed: int,
) -> tuple[LGBMRegressor, LGBMRegressor]:
    models: list[LGBMRegressor] = []
    for arm in (0, 1):
        rows = treatment == arm
        model = lgbm(seed + arm).fit(matrix[rows], y[rows])
        models.append(model)
    return models[0], models[1]


def internal_crossfit_nuisance(
    raw: pd.DataFrame,
    y: np.ndarray,
    treatment: np.ndarray,
    site: np.ndarray,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    labels = np.char.add(np.char.add(site.astype(str), "_"), treatment.astype(str))
    splitter = StratifiedKFold(n_splits=3, shuffle=True, random_state=seed)
    m0, m1, m = np.empty(len(y)), np.empty(len(y)), np.empty(len(y))
    for fold, (train, test) in enumerate(splitter.split(np.zeros(len(y)), labels)):
        transform = encoder().fit(raw.iloc[train])
        x_train = transform.transform(raw.iloc[train])
        x_test = transform.transform(raw.iloc[test])
        for arm, target in ((0, m0), (1, m1)):
            rows = treatment[train] == arm
            model = lgbm(seed + fold * 10 + arm).fit(x_train[rows], y[train][rows])
            target[test] = model.predict(x_test)
        pooled = lgbm(seed + fold * 10 + 5).fit(x_train, y[train])
        m[test] = pooled.predict(x_test)
    return m0, m1, m


def _direct_score(
    matrix: Any, pseudo: np.ndarray, threshold: float
) -> np.ndarray | LogisticRegression:
    label = (pseudo > threshold).astype(np.int8)
    if len(np.unique(label)) < 2:
        return np.full(matrix.shape[0], 1.0 if label[0] else -1.0)
    weight = np.minimum(np.abs(pseudo - threshold), np.quantile(np.abs(pseudo), 0.99))
    model = LogisticRegression(C=0.1, max_iter=500, random_state=PRIMARY_SEED)
    model.fit(matrix, label, sample_weight=np.maximum(weight, 1.0))
    return model


def cross_fitted_predictions(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    raw = feature_frame(frame)
    y = frame["earnings_30m"].to_numpy(dtype=float)
    treatment = frame["treatment"].to_numpy(dtype=np.int8)
    fold_id = folds_for(frame, PRIMARY_SEED)
    output = {
        name: np.empty(len(frame), dtype=float)
        for name in (
            "linear_t_learner",
            "lgbm_t_learner",
            "x_learner",
            "r_learner",
            "dr_learner",
            "policy_tree_depth_2",
            "direct_dr_policy",
            "cost_sensitive_dr_500",
            "simple_service_strategy_segment",
        )
    }
    m0_eval, m1_eval = np.empty(len(frame)), np.empty(len(frame))

    for fold in range(FOLDS):
        test = fold_id == fold
        train = ~test
        transform = encoder().fit(raw.loc[train])
        x_train = transform.transform(raw.loc[train])
        x_test = transform.transform(raw.loc[test])
        y_train = y[train]
        a_train = treatment[train]

        l0, l1 = _fit_arm_models(x_train, y_train, a_train, PRIMARY_SEED + fold * 100)
        m0_test, m1_test = l0.predict(x_test), l1.predict(x_test)
        m0_eval[test], m1_eval[test] = m0_test, m1_test
        output["lgbm_t_learner"][test] = m1_test - m0_test

        ridge_models: list[Ridge] = []
        for arm in (0, 1):
            rows = a_train == arm
            ridge_models.append(
                Ridge(alpha=100.0, solver="lsqr").fit(x_train[rows], y_train[rows])
            )
        output["linear_t_learner"][test] = (
            ridge_models[1].predict(x_test) - ridge_models[0].predict(x_test)
        )

        d1 = y_train[a_train == 1] - l0.predict(x_train[a_train == 1])
        d0 = l1.predict(x_train[a_train == 0]) - y_train[a_train == 0]
        tau1 = lgbm(PRIMARY_SEED + fold * 100 + 20).fit(x_train[a_train == 1], d1)
        tau0 = lgbm(PRIMARY_SEED + fold * 100 + 21).fit(x_train[a_train == 0], d0)
        output["x_learner"][test] = (
            (1 - PROPENSITY) * tau1.predict(x_test) + PROPENSITY * tau0.predict(x_test)
        )

        inner_m0, inner_m1, inner_m = internal_crossfit_nuisance(
            raw.loc[train].reset_index(drop=True),
            y_train,
            a_train,
            frame.loc[train, "site"].to_numpy(),
            PRIMARY_SEED + fold * 100 + 30,
        )
        dr = (
            inner_m1
            - inner_m0
            + a_train * (y_train - inner_m1) / PROPENSITY
            - (1 - a_train) * (y_train - inner_m0) / (1 - PROPENSITY)
        )
        r_pseudo = (y_train - inner_m) / (a_train - PROPENSITY)
        r_weight = np.square(a_train - PROPENSITY)

        dr_model = lgbm(PRIMARY_SEED + fold * 100 + 40).fit(x_train, dr)
        r_model = lgbm(PRIMARY_SEED + fold * 100 + 41).fit(
            x_train,
            r_pseudo,
            sample_weight=r_weight,
        )
        output["dr_learner"][test] = dr_model.predict(x_test)
        output["r_learner"][test] = r_model.predict(x_test)

        tree = DecisionTreeRegressor(
            max_depth=2,
            min_samples_leaf=250,
            random_state=PRIMARY_SEED,
        ).fit(x_train, dr)
        output["policy_tree_depth_2"][test] = tree.predict(x_test)

        direct = _direct_score(x_train, dr, 0.0)
        if isinstance(direct, np.ndarray):
            output["direct_dr_policy"][test] = direct[0]
        else:
            output["direct_dr_policy"][test] = direct.decision_function(x_test)
        cost_sensitive = _direct_score(x_train, dr, 500.0)
        if isinstance(cost_sensitive, np.ndarray):
            output["cost_sensitive_dr_500"][test] = cost_sensitive[0]
        else:
            output["cost_sensitive_dr_500"][test] = cost_sensitive.decision_function(x_test)

        train_segments = frame.loc[train, "trtmnt"].astype(str).to_numpy()
        test_segments = frame.loc[test, "trtmnt"].astype(str).to_numpy()
        overall = y_train[a_train == 1].mean() - y_train[a_train == 0].mean()
        segment_effect: dict[str, float] = {}
        for segment in sorted(set(train_segments)):
            rows = train_segments == segment
            treated = rows & (a_train == 1)
            control = rows & (a_train == 0)
            segment_effect[segment] = (
                float(y_train[treated].mean() - y_train[control].mean())
                if treated.sum() >= 50 and control.sum() >= 50
                else float(overall)
            )
        output["simple_service_strategy_segment"][test] = np.asarray(
            [segment_effect.get(segment, overall) for segment in test_segments]
        )

    output["m0_eval"] = m0_eval
    output["m1_eval"] = m1_eval
    output["fold_id"] = fold_id
    return output


def dr_score(
    policy: np.ndarray,
    y: np.ndarray,
    treatment: np.ndarray,
    m0: np.ndarray,
    m1: np.ndarray,
) -> np.ndarray:
    policy = np.asarray(policy, dtype=np.int8)
    observed_probability = np.where(treatment == 1, PROPENSITY, 1 - PROPENSITY)
    observed_prediction = np.where(treatment == 1, m1, m0)
    policy_prediction = np.where(policy == 1, m1, m0)
    return policy_prediction + (policy == treatment) * (
        y - observed_prediction
    ) / observed_probability


def hajek_value(
    policy: np.ndarray,
    y: np.ndarray,
    treatment: np.ndarray,
) -> tuple[float, np.ndarray]:
    probability = np.where(treatment == 1, PROPENSITY, 1 - PROPENSITY)
    weight = (policy == treatment) / probability
    denominator = float(weight.mean())
    point = float(np.mean(weight * y) / denominator)
    influence = weight * (y - point) / denominator
    return point, influence


def comparison(
    policy: np.ndarray,
    comparator: np.ndarray,
    y: np.ndarray,
    treatment: np.ndarray,
    m0: np.ndarray,
    m1: np.ndarray,
) -> dict[str, Any]:
    point_policy, if_policy = hajek_value(policy, y, treatment)
    point_comparator, if_comparator = hajek_value(comparator, y, treatment)
    ipw = estimate_from_influence(
        point_policy - point_comparator,
        if_policy - if_comparator,
    )
    dr_delta = dr_score(policy, y, treatment, m0, m1) - dr_score(
        comparator, y, treatment, m0, m1
    )
    dr = estimate_from_influence(float(dr_delta.mean()), dr_delta - dr_delta.mean())
    return {"hajek_ipw": asdict(ipw), "doubly_robust": asdict(dr), "dr_rows": dr_delta}


def effective_sample_size(weights: np.ndarray) -> float:
    denominator = float(np.square(weights).sum())
    return float(weights.sum() ** 2 / denominator) if denominator > 0 else 0.0


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def run_tournament() -> dict[str, Any]:
    frame, access = development_frame()
    if access["validation_outcomes_opened"]:
        raise RuntimeError("V13 validation outcome access during development")
    y = frame["earnings_30m"].to_numpy(dtype=float)
    treatment = frame["treatment"].to_numpy(dtype=np.int8)
    predictions = cross_fitted_predictions(frame)
    m0, m1 = predictions.pop("m0_eval"), predictions.pop("m1_eval")
    fold_id = predictions.pop("fold_id").astype(np.int8)
    bau = np.zeros(len(frame), dtype=np.int8)
    treat_all = np.ones(len(frame), dtype=np.int8)
    static_comparison = comparison(treat_all, bau, y, treatment, m0, m1)
    best_static_name = (
        "TREAT_ALL"
        if static_comparison["hajek_ipw"]["point"] > 0
        else "BAU_TREAT_NONE"
    )
    best_static = treat_all if best_static_name == "TREAT_ALL" else bau
    materiality = max(0.01 * float(y[treatment == 0].mean()), 100.0)

    models: dict[str, Any] = {}
    for name, score in predictions.items():
        policy = (score > 0).astype(np.int8)
        versus_bau = comparison(policy, bau, y, treatment, m0, m1)
        versus_static = comparison(policy, best_static, y, treatment, m0, m1)
        dr_rows = versus_static.pop("dr_rows")
        versus_bau.pop("dr_rows")
        fold_values = [float(dr_rows[fold_id == fold].mean()) for fold in range(FOLDS)]
        site_values = {
            str(site): float(dr_rows[frame["site"].astype(str).to_numpy() == str(site)].mean())
            for site in sorted(frame["site"].astype(str).unique())
        }
        probability = np.where(treatment == 1, PROPENSITY, 1 - PROPENSITY)
        match_weight = (policy == treatment) / probability
        treated_weight = match_weight * (policy == 1)
        control_weight = match_weight * (policy == 0)
        ipw_result = versus_static["hajek_ipw"]
        dr_result = versus_static["doubly_robust"]
        gates = {
            "beats_static_point": ipw_result["point"] > 0 and dr_result["point"] > 0,
            "conservative_lower_bound_positive": min(
                ipw_result["lower_95"], dr_result["lower_95"]
            )
            > 0,
            "ess": effective_sample_size(treated_weight) >= 400
            and effective_sample_size(control_weight) >= 400,
            "estimator_agreement": ipw_result["point"] > 0 and dr_result["point"] > 0,
            "fold_stability": sum(value > 0 for value in fold_values) >= 4,
            "materiality": min(ipw_result["point"], dr_result["point"]) >= materiality,
            "site_stability": sum(value >= 0 for value in site_values.values()) >= 8
            and min(site_values.values()) >= -2 * materiality,
            "treatment_rate": 0.05 <= float(policy.mean()) <= 0.95,
            "timing_and_leakage": True,
        }
        pre_placebo_pass = all(gates.values())
        gates["placebo"] = False
        models[name] = {
            "break_even_offer_cost_usd": (
                float(dr_result["point"] / policy.mean()) if policy.mean() > 0 else 0.0
            ),
            "cost_sensitivity_dr_value_vs_static": {
                str(cost): float(dr_result["point"] - cost * policy.mean())
                for cost in [0, 100, 250, 500, 750, 1000, 1500, 2000, 3000]
            },
            "fold_value_vs_static": fold_values,
            "gates": gates,
            "ipw_ess_control_action": effective_sample_size(control_weight),
            "ipw_ess_treated_action": effective_sample_size(treated_weight),
            "pre_placebo_pass": pre_placebo_pass,
            "site_value_vs_static": site_values,
            "treatment_rate": float(policy.mean()),
            "total_incremental_value_dr": float(dr_result["point"] * len(frame)),
            "versus_bau": versus_bau,
            "versus_best_static": versus_static,
        }

    ranked = sorted(
        models,
        key=lambda name: (
            models[name]["versus_best_static"]["doubly_robust"]["point"],
            -models[name]["treatment_rate"],
        ),
        reverse=True,
    )
    best_challenger = ranked[0]
    earned_reveal = any(result["pre_placebo_pass"] for result in models.values())
    if earned_reveal:
        raise RuntimeError(
            "V13 candidate reached placebo stage; explicit placebo refit is required"
        )

    best_policy = (predictions[best_challenger] > 0).astype(np.int8)
    best_dr_delta = dr_score(best_policy, y, treatment, m0, m1) - dr_score(
        best_static, y, treatment, m0, m1
    )
    rng = np.random.default_rng(1301)
    bootstrap = np.empty(1_000, dtype=float)
    for index in range(len(bootstrap)):
        sample = rng.integers(0, len(best_dr_delta), size=len(best_dr_delta))
        bootstrap[index] = float(best_dr_delta[sample].mean())

    group = np.where(
        pd.to_numeric(frame["age"]) >= 22,
        np.where(frame["sex"] == "1", "adult_men", "adult_women"),
        np.where(frame["sex"] == "1", "male_youth", "female_youth"),
    )
    fairness = {
        str(name): {
            "n": int((group == name).sum()),
            "treatment_rate": float(best_policy[group == name].mean()),
            "value_vs_static_dr": float(best_dr_delta[group == name].mean()),
        }
        for name in sorted(set(group))
    }

    result: dict[str, Any] = {
        "access_control": {
            "development_outcomes_opened": True,
            "validation_outcomes_opened": False,
            "validation_reveal_started": False,
        },
        "best_challenger": best_challenger,
        "best_challenger_bootstrap": {
            "lower_95": float(np.quantile(bootstrap, 0.025)),
            "replicates": 1_000,
            "seed": 1301,
            "standard_error": float(bootstrap.std(ddof=1)),
            "upper_95": float(np.quantile(bootstrap, 0.975)),
        },
        "best_static": best_static_name,
        "cost_sensitivity_usd": [0, 100, 250, 500, 750, 1000, 1500, 2000, 3000],
        "development": {
            "control_mean": float(y[treatment == 0].mean()),
            "materiality_usd": materiality,
            "n": len(frame),
            "offer_mean": float(y[treatment == 1].mean()),
            "raw_offer_minus_control": float(
                y[treatment == 1].mean() - y[treatment == 0].mean()
            ),
        },
        "development_status": "V13_DEVELOPMENT_NO_PERSONALIZED_POLICY_EARNED_REVEAL",
        "earned_validation_reveal": False,
        "fairness_audit_best_challenger": fairness,
        "features": list(FEATURES),
        "models": models,
        "primary_outcome": "SUM_UIERN01_TO_UIERN30_NOMINAL_USD",
        "schema_version": 1,
        "static_treat_all_vs_bau": {
            key: value
            for key, value in static_comparison.items()
            if key != "dr_rows"
        },
        "unavailable_models": {
            "honest_causal_forest": "DEPENDENCY_NOT_INSTALLED_AT_PREREGISTRATION"
        },
    }
    MODEL_RESULTS.write_text(
        json.dumps(_json_safe(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not DEVELOPMENT_ACCESS.exists():
        raise RuntimeError("V13 development access record missing")
    return result


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    run_tournament()
