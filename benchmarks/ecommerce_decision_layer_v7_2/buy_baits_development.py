"""Development-only Buy Baits tournament; validation and sealed outcomes are inaccessible."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd
from scipy.stats import norm

from decision_engine.datasets.buy_baits import (
    ENTERPRISE_ALLOWED_ARMS,
    policy_dataset_from_development,
)
from decision_engine.economic_policy_v72 import (
    CrossFittedOutcomeModel,
    EconomicPolicyDataset,
    causal_challengers,
    evaluate_policy,
    model_candidates,
)

ROOT = Path(__file__).resolve().parent
DEVELOPMENT = Path("data/processed/buy_baits/v7_2/development.parquet")
LOCK = ROOT / "BUY_BAITS_DEVELOPMENT_LOCK.json"
SEED = 72_2011
FOLDS = 5


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_lock() -> bool:
    payload = json.loads(LOCK.read_text())
    for relative, expected in payload["immutable_artifacts"].items():
        if _sha256(ROOT / relative) != expected:
            raise RuntimeError(f"immutable Buy Baits artifact changed: {relative}")
    return True


@runtime_checkable
class FittablePolicyModel(Protocol):
    name: str

    def fit(
        self, features: np.ndarray, action: np.ndarray, outcome: np.ndarray, arms: int
    ) -> None: ...

    def predict_actions(self, features: np.ndarray) -> np.ndarray: ...


def _inner_holdout(unit_id: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            int.from_bytes(hashlib.sha256(f"{SEED}\0{value}".encode()).digest()[:8], "big")
            / 2**64
            < 0.25
            for value in unit_id
        ],
        dtype=bool,
    )


def _subset(data: EconomicPolicyDataset, mask: np.ndarray) -> EconomicPolicyDataset:
    return replace(
        data,
        features=data.features[mask],
        action=data.action[mask],
        monetary_outcome=data.monetary_outcome[mask],
        propensity=data.propensity[mask],
        action_cost=data.action_cost[mask],
        allowed_actions=data.allowed_actions[mask],
        unit_id=data.unit_id[mask],
        mature=data.mature[mask] if data.mature is not None else None,
    )


def _policy_from_prediction(prediction: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    return np.argmax(np.where(allowed, prediction, -np.inf), axis=1).astype(np.int64)


def _evaluation_record(
    name: str,
    data: EconomicPolicyDataset,
    policy: np.ndarray,
    evaluator_nuisance: np.ndarray,
    static_influence: np.ndarray,
) -> dict[str, Any]:
    evaluation = evaluate_policy(data, policy, evaluator_nuisance, estimator="dr")
    difference = evaluation.influence - static_influence
    difference_se = float(np.std(difference, ddof=1) / np.sqrt(len(difference)))
    critical = float(norm.ppf(0.975))
    return {
        "name": name,
        "value_per_visitor": evaluation.value_per_unit,
        "standard_error": evaluation.standard_error,
        "lower_95": evaluation.lower_95,
        "upper_95": evaluation.upper_95,
        "effective_sample_size": evaluation.effective_sample_size,
        "increment_vs_best_static": float(np.mean(difference)),
        "increment_standard_error": difference_se,
        "increment_lower_95": float(np.mean(difference) - critical * difference_se),
        "increment_upper_95": float(np.mean(difference) + critical * difference_se),
        "distinct_from_static_fraction": float(np.mean(policy != np.argmax(np.bincount(policy)))),
        "action_counts": {
            str(int(arm + 1)): int(count)
            for arm, count in zip(*np.unique(policy, return_counts=True), strict=True)
        },
        "unsupported_or_prohibited_selections": int(
            np.sum(~data.allowed_actions[np.arange(len(policy)), policy])
        ),
    }


def _fit_candidate(
    candidate: CrossFittedOutcomeModel | FittablePolicyModel,
    train: EconomicPolicyDataset,
    test: EconomicPolicyDataset,
) -> tuple[str, np.ndarray, np.ndarray]:
    if isinstance(candidate, CrossFittedOutcomeModel):
        model = candidate
        oof = model.fit_predict_oof(
            train.features, train.action, train.monetary_outcome, train.arms
        )
        prediction = model.predict_actions(test.features)
        return model.name, oof, prediction
    policy_model = candidate
    if not isinstance(policy_model, FittablePolicyModel):
        raise TypeError("candidate does not implement policy-model protocol")
    policy_model.fit(train.features, train.action, train.monetary_outcome, train.arms)
    prediction = policy_model.predict_actions(test.features)
    return policy_model.name, np.empty((0, train.arms)), prediction


def run() -> dict[str, Any]:
    if LOCK.exists():
        verify_lock()
        raise RuntimeError(
            "Buy Baits development is immutable; no rerun or retuning is permitted"
        )
    started = time.perf_counter()
    frame = pd.read_parquet(DEVELOPMENT)
    if "id" in frame.columns:
        raise RuntimeError("raw cookie ID persisted into development data")
    data = policy_dataset_from_development(frame)
    held_out = _inner_holdout(data.unit_id)
    train, test = _subset(data, ~held_out), _subset(data, held_out)
    if set(train.unit_id) & set(test.unit_id):
        raise RuntimeError("inner development leakage")

    evaluator = CrossFittedOutcomeModel(model_candidates(SEED)[0], folds=FOLDS, seed=SEED)
    evaluator_train_oof = evaluator.fit_predict_oof(
        train.features, train.action, train.monetary_outcome, train.arms
    )
    evaluator_test = evaluator.predict_actions(test.features)
    allowed_indexes = tuple(arm - 1 for arm in ENTERPRISE_ALLOWED_ARMS)

    training_static = {}
    for arm in allowed_indexes:
        evaluation = evaluate_policy(
            train,
            np.full(len(train.action), arm, dtype=np.int64),
            evaluator_train_oof,
        )
        training_static[arm] = evaluation.value_per_unit
    best_static_arm = max(training_static, key=lambda arm: training_static[arm])
    static_policy = np.full(len(test.action), best_static_arm, dtype=np.int64)
    static_evaluation = evaluate_policy(test, static_policy, evaluator_test)

    records: list[dict[str, Any]] = []
    bau_policy = np.full(len(test.action), test.bau_action, dtype=np.int64)
    records.append(
        _evaluation_record(
            "BAU_control", test, bau_policy, evaluator_test, static_evaluation.influence
        )
    )
    for arm in allowed_indexes:
        policy = np.full(len(test.action), arm, dtype=np.int64)
        records.append(
            _evaluation_record(
                f"treat_all_arm_{arm + 1}",
                test,
                policy,
                evaluator_test,
                static_evaluation.influence,
            )
        )

    segment_actions = np.full(3, best_static_arm, dtype=np.int64)
    for segment in range(3):
        segment_mask = train.features[:, segment] == 1
        arm_means = {
            arm: float(
                np.mean(train.monetary_outcome[segment_mask & (train.action == arm)])
            )
            for arm in allowed_indexes
        }
        segment_actions[segment] = max(arm_means, key=lambda arm: arm_means[arm])
    segment_policy = segment_actions[np.argmax(test.features, axis=1)]
    records.append(
        _evaluation_record(
            "simple_device_segment",
            test,
            segment_policy,
            evaluator_test,
            static_evaluation.influence,
        )
    )

    skipped: list[dict[str, str]] = []
    base_candidates = []
    for base_candidate in model_candidates(SEED):
        if base_candidate.name == "tweedie_t" and np.any(train.monetary_outcome < 0):
            skipped.append(
                {
                    "name": base_candidate.name,
                    "reason": "invalid support: observed retailer profit contains negative values",
                }
            )
            continue
        base_candidates.append(
            CrossFittedOutcomeModel(base_candidate, folds=FOLDS, seed=SEED)
        )

    calibration: dict[str, dict[str, float]] = {}
    for policy_candidate in (*base_candidates, *causal_challengers(SEED)):
        name, _, prediction = _fit_candidate(policy_candidate, train, test)
        if prediction.shape != (len(test.action), test.arms) or not np.all(
            np.isfinite(prediction)
        ):
            raise RuntimeError(f"{name} produced invalid predictions")
        policy = _policy_from_prediction(prediction, test.allowed_actions)
        records.append(
            _evaluation_record(
                name, test, policy, evaluator_test, static_evaluation.influence
            )
        )
        observed_prediction = prediction[np.arange(len(test.action)), test.action]
        residual = test.monetary_outcome - observed_prediction
        calibration[name] = {
            "observed_action_mean_error": float(np.mean(residual)),
            "observed_action_mae": float(np.mean(np.abs(residual))),
            "observed_action_rmse": float(np.sqrt(np.mean(residual**2))),
        }

    personalized = [
        row
        for row in records
        if row["name"]
        not in {"BAU_control", *(f"treat_all_arm_{arm + 1}" for arm in allowed_indexes)}
    ]
    provisional_best = max(personalized, key=lambda row: row["value_per_visitor"])
    materiality = max(0.0001, 0.01 * abs(static_evaluation.value_per_unit))
    personalization_material = bool(
        provisional_best["increment_vs_best_static"] > materiality
        and provisional_best["increment_lower_95"] > 0
    )

    rng = np.random.default_rng(SEED)
    shuffled_action = train.action.copy()
    rng.shuffle(shuffled_action)
    shuffle_model = CrossFittedOutcomeModel(model_candidates(SEED)[0], folds=FOLDS, seed=SEED)
    shuffle_model.fit_predict_oof(
        train.features, shuffled_action, train.monetary_outcome, train.arms
    )
    shuffle_policy = _policy_from_prediction(
        shuffle_model.predict_actions(test.features), test.allowed_actions
    )
    shuffle_record = _evaluation_record(
        "treatment_shuffle_placebo",
        test,
        shuffle_policy,
        evaluator_test,
        static_evaluation.influence,
    )

    shuffled_outcome = train.monetary_outcome.copy()
    rng.shuffle(shuffled_outcome)
    outcome_placebo = CrossFittedOutcomeModel(
        model_candidates(SEED)[0], folds=FOLDS, seed=SEED
    )
    outcome_placebo.fit_predict_oof(
        train.features, train.action, shuffled_outcome, train.arms
    )
    outcome_placebo_policy = _policy_from_prediction(
        outcome_placebo.predict_actions(test.features), test.allowed_actions
    )
    outcome_placebo_record = _evaluation_record(
        "outcome_shuffle_placebo",
        test,
        outcome_placebo_policy,
        evaluator_test,
        static_evaluation.influence,
    )

    lower, upper = np.quantile(train.monetary_outcome, [0.005, 0.995])
    winsorized = np.clip(train.monetary_outcome, lower, upper)
    winsorized_values = {
        arm: float(np.mean(winsorized[train.action == arm])) for arm in allowed_indexes
    }
    winsorized_best = max(winsorized_values, key=lambda arm: winsorized_values[arm])
    cost_sensitivity: dict[str, dict[str, float | int]] = {}
    for extra_cost in (0.0, 0.001, 0.0025, 0.005):
        scenario = {
            arm: value - (0.0 if arm == train.bau_action else extra_cost)
            for arm, value in training_static.items()
        }
        winner = max(scenario, key=lambda arm: scenario[arm])
        cost_sensitivity[str(extra_cost)] = {
            "selected_arm": winner + 1,
            "scenario_value_per_visitor": scenario[winner],
        }

    result: dict[str, Any] = {
        "status": "DEVELOPMENT_ONLY_NO_FREEZE",
        "seed": SEED,
        "folds": FOLDS,
        "objective": "known-propensity DR value of package-provided retailer profit per visitor",
        "claim_boundary": "not contribution profit; no validation or sealed outcome accessed",
        "counts": {
            "audited_development_units_complete_profit": len(data.action),
            "inner_train_units": len(train.action),
            "inner_heldout_units": len(test.action),
            "inner_overlap": 0,
        },
        "features": list(data.feature_names),
        "known_propensity": 0.125,
        "enterprise_allowed_arms": list(ENTERPRISE_ALLOWED_ARMS),
        "development_selected_best_static_arm": best_static_arm + 1,
        "development_training_static_values": {
            str(arm + 1): value for arm, value in training_static.items()
        },
        "heldout_development_results": records,
        "calibration": calibration,
        "skipped_invalid_candidate": skipped,
        "provisional_best_personalized": provisional_best["name"],
        "materiality_per_visitor": materiality,
        "material_observable_personalization": personalization_material,
        "falsification": {
            "treatment_shuffle": shuffle_record,
            "outcome_shuffle": outcome_placebo_record,
            "forbidden_feature_count": 0,
            "prohibited_action_selections": int(
                sum(row["unsupported_or_prohibited_selections"] for row in records)
            ),
            "all_allowed_arm_train_rows": {
                str(arm + 1): int(np.sum(train.action == arm)) for arm in allowed_indexes
            },
            "support": {
                "known_inverse_propensity_weight": 8.0,
                "all_enterprise_arms_observed": True,
                "minimum_allowed_arm_train_rows": int(
                    min(np.sum(train.action == arm) for arm in allowed_indexes)
                ),
            },
            "outlier_sensitivity": {
                "winsorization_quantiles": [0.005, 0.995],
                "lower": float(lower),
                "upper": float(upper),
                "selected_arm": winsorized_best + 1,
                "arm_values": {
                    str(arm + 1): value for arm, value in winsorized_values.items()
                },
            },
            "additional_equal_per_exposure_cost_scenarios": cost_sensitivity,
        },
        "runtime_seconds": time.perf_counter() - started,
        "official_selection_frozen": False,
        "validation_revealed": False,
        "sealed_test_revealed": False,
    }
    destination = ROOT / "results/buy_baits_development_tournament.json"
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-lock", action="store_true")
    arguments = parser.parse_args()
    if arguments.verify_lock:
        print(json.dumps({"buy_baits_development_lock_valid": verify_lock()}))
        raise SystemExit(0)
    report = run()
    print(
        json.dumps(
            {
                "status": report["status"],
                "best_static_arm": report["development_selected_best_static_arm"],
                "provisional_best": report["provisional_best_personalized"],
                "material_personalization": report["material_observable_personalization"],
                "runtime_seconds": report["runtime_seconds"],
            },
            indent=2,
        )
    )
