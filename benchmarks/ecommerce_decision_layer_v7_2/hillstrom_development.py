"""Preregistered Hillstrom three-arm DEVELOPMENT-only economic tournament."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from decision_engine.datasets.hillstrom import CONTROL, MENS, WOMENS
from decision_engine.economic_policy_v72 import (
    CrossFittedOutcomeModel,
    EconomicPolicyDataset,
    causal_challengers,
    evaluate_policy,
    model_candidates,
)

ROOT = Path(__file__).resolve().parent
DEVELOPMENT = Path("data/processed/hillstrom/v7_2/development.parquet")
PREREGISTRATION = ROOT / "HILLSTROM_DEVELOPMENT_PREREGISTRATION.md"
OUTPUT = ROOT / "results/hillstrom_development_tournament.json"
REPORT = ROOT / "HILLSTROM_DEVELOPMENT_REPORT.md"
SEED = 72_2021
FOLDS = 5
COST_GRID = (0.0, 0.01, 0.05, 0.10, 0.25, 0.50, 1.00, 2.00)
PRIMARY_COST = 0.05
ACTION_LABELS = (CONTROL, MENS, WOMENS)
RAW_ACTION = {"No E-Mail": 0, "Mens E-Mail": 1, "Womens E-Mail": 2}
NUMERIC = ("recency", "history", "mens", "womens", "newbie")
CATEGORICAL = ("history_segment", "zip_code", "channel")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _make_data(
    features: np.ndarray,
    action: np.ndarray,
    spend: np.ndarray,
    unit_id: np.ndarray,
    cost: float,
) -> EconomicPolicyDataset:
    n, arms = len(action), 3
    costs = np.zeros((n, arms))
    costs[:, 1:] = cost
    return EconomicPolicyDataset(
        features=np.asarray(features, dtype=float),
        action=np.asarray(action, dtype=np.int64),
        monetary_outcome=np.asarray(spend, dtype=float),
        propensity=np.full((n, arms), 1 / 3),
        action_cost=costs,
        allowed_actions=np.ones((n, arms), dtype=bool),
        unit_id=np.asarray(unit_id, dtype=str),
        bau_action=0,
        mature=np.ones(n, dtype=bool),
    )


def _paired_interval(first: np.ndarray, second: np.ndarray) -> dict[str, float]:
    difference = np.asarray(first - second, dtype=float)
    point = float(np.mean(difference))
    se = float(np.std(difference, ddof=1) / np.sqrt(len(difference)))
    critical = float(norm.ppf(0.975))
    return {
        "point": point,
        "standard_error": se,
        "lower_95": point - critical * se,
        "upper_95": point + critical * se,
    }


def _segment_key(frame: pd.DataFrame) -> np.ndarray:
    recency_value = frame["recency"].to_numpy()
    history_value = frame["history"].to_numpy()
    recency = np.where(recency_value <= 3, "R1", np.where(recency_value <= 6, "R2", "R3"))
    history = np.where(
        history_value < 200, "F1", np.where(history_value < 500, "F2", "F3")
    )
    mens = frame["mens"].to_numpy().astype(int)
    womens = frame["womens"].to_numpy().astype(int)
    affinity = np.where(
        (mens == 1) & (womens == 0),
        "M",
        np.where((mens == 0) & (womens == 1), "W", "B"),
    )
    return np.char.add(np.char.add(np.char.add(recency, "_"), history), np.char.add("_", affinity))


def _segment_predictions(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    train_action: np.ndarray,
    train_spend: np.ndarray,
) -> np.ndarray:
    train_key, test_key = _segment_key(train_frame), _segment_key(test_frame)
    global_means = np.asarray(
        [np.mean(train_spend[train_action == arm]) for arm in range(3)], dtype=float
    )
    prediction = np.tile(global_means, (len(test_frame), 1))
    for key in np.unique(train_key):
        train_segment = train_key == key
        test_segment = test_key == key
        if not np.any(test_segment):
            continue
        for arm in range(3):
            rows = train_segment & (train_action == arm)
            if int(rows.sum()) >= 40:
                prediction[test_segment, arm] = np.mean(train_spend[rows])
    return prediction


def _fold_stability(increment: np.ndarray, unit_id: np.ndarray) -> dict[str, Any]:
    fold = np.asarray(
        [
            int(hashlib.sha256(f"stability\0{value}".encode()).hexdigest()[:8], 16) % 5
            for value in unit_id
        ]
    )
    values = [float(np.mean(increment[fold == index])) for index in range(5)]
    return {
        "fold_increment": values,
        "positive_fold_fraction": float(np.mean(np.asarray(values) > 0)),
        "minimum_fold_increment": min(values),
        "maximum_fold_increment": max(values),
    }


def run() -> dict[str, Any]:
    started = time.perf_counter()
    frame = pd.read_parquet(DEVELOPMENT)
    required = set((*NUMERIC, *CATEGORICAL, "segment", "spend", "unit_hash"))
    if not required.issubset(frame.columns) or {"row_id", "id"} & set(frame.columns):
        raise RuntimeError("invalid or identifying Hillstrom development materialization")
    action = frame["segment"].map(RAW_ACTION).to_numpy(dtype=np.int64)
    spend = frame["spend"].to_numpy(dtype=float)
    unit_id = frame["unit_hash"].to_numpy(dtype=str)
    held_out = _inner_holdout(unit_id)
    train_frame = frame.loc[~held_out].reset_index(drop=True)
    test_frame = frame.loc[held_out].reset_index(drop=True)
    train_action, test_action = action[~held_out], action[held_out]
    train_spend, test_spend = spend[~held_out], spend[held_out]
    train_id, test_id = unit_id[~held_out], unit_id[held_out]
    if set(train_id) & set(test_id):
        raise RuntimeError("inner Hillstrom development leakage")

    transformer = ColumnTransformer(
        [
            ("numeric", StandardScaler(), list(NUMERIC)),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                list(CATEGORICAL),
            ),
        ]
    )
    x_train = np.asarray(transformer.fit_transform(train_frame), dtype=float)
    x_test = np.asarray(transformer.transform(test_frame), dtype=float)
    train_zero = _make_data(x_train, train_action, train_spend, train_id, 0.0)
    test_zero = _make_data(x_test, test_action, test_spend, test_id, 0.0)

    evaluator = CrossFittedOutcomeModel(model_candidates(SEED)[0], folds=FOLDS, seed=SEED)
    evaluator_train = evaluator.fit_predict_oof(
        x_train, train_action, train_spend, train_zero.arms
    )
    evaluator_test = evaluator.predict_actions(x_test)

    predictions: dict[str, np.ndarray] = {
        "simple_rfm_affinity_segment": _segment_predictions(
            train_frame, test_frame, train_action, train_spend
        )
    }
    calibration: dict[str, dict[str, float]] = {}
    for base in model_candidates(SEED):
        model = CrossFittedOutcomeModel(base, folds=FOLDS, seed=SEED)
        model.fit_predict_oof(x_train, train_action, train_spend, train_zero.arms)
        predictions[model.name] = model.predict_actions(x_test)
    for causal_model in causal_challengers(SEED, bau_action=0):
        causal_model.fit(x_train, train_action, train_spend, train_zero.arms)
        predictions[causal_model.name] = causal_model.predict_actions(x_test)
    for name, prediction in predictions.items():
        if prediction.shape != (len(test_action), 3) or not np.all(np.isfinite(prediction)):
            raise RuntimeError(f"invalid predictions from {name}")
        observed = prediction[np.arange(len(test_action)), test_action]
        residual = test_spend - observed
        calibration[name] = {
            "observed_action_mean_error": float(np.mean(residual)),
            "observed_action_mae": float(np.mean(np.abs(residual))),
            "observed_action_rmse": float(np.sqrt(np.mean(residual**2))),
        }

    by_cost: dict[str, Any] = {}
    primary_policies: dict[str, np.ndarray] = {}
    primary_influences: dict[str, np.ndarray] = {}
    for cost in COST_GRID:
        train = _make_data(x_train, train_action, train_spend, train_id, cost)
        test = _make_data(x_test, test_action, test_spend, test_id, cost)
        train_nuisance = evaluator_train - train.action_cost
        test_nuisance = evaluator_test - test.action_cost
        static_train_values: dict[int, float] = {}
        for arm in range(3):
            static_train_values[arm] = evaluate_policy(
                train,
                np.full(len(train_action), arm, dtype=np.int64),
                train_nuisance,
            ).value_per_unit
        best_static_arm = max(
            static_train_values, key=lambda arm: static_train_values[arm]
        )
        bau_policy = np.zeros(len(test_action), dtype=np.int64)
        static_policy = np.full(len(test_action), best_static_arm, dtype=np.int64)
        bau = evaluate_policy(test, bau_policy, test_nuisance)
        static = evaluate_policy(test, static_policy, test_nuisance)
        rows: list[dict[str, Any]] = []
        baseline_policies = {
            "BAU": bau_policy,
            "treat_all_mens": np.ones(len(test_action), dtype=np.int64),
            "treat_all_womens": np.full(len(test_action), 2, dtype=np.int64),
            "best_static": static_policy,
        }
        evaluated_policies = dict(baseline_policies)
        evaluated_policies.update(
            {
                name: np.argmax(
                    prediction - test.action_cost, axis=1
                ).astype(np.int64)
                for name, prediction in predictions.items()
            }
        )
        for name, policy in evaluated_policies.items():
            evaluation = evaluate_policy(test, policy, test_nuisance)
            versus_bau = _paired_interval(evaluation.influence, bau.influence)
            versus_static = _paired_interval(evaluation.influence, static.influence)
            row = {
                "name": name,
                "value_per_customer": evaluation.value_per_unit,
                "lower_95": evaluation.lower_95,
                "upper_95": evaluation.upper_95,
                "versus_bau": versus_bau,
                "versus_best_static": versus_static,
                "email_rate": float(np.mean(policy != 0)),
                "action_counts": {
                    ACTION_LABELS[int(arm)]: int(count)
                    for arm, count in zip(*np.unique(policy, return_counts=True), strict=True)
                },
                "stability_vs_static": _fold_stability(
                    evaluation.influence - static.influence, test_id
                ),
            }
            rows.append(row)
            if cost == PRIMARY_COST:
                primary_policies[name] = policy
                primary_influences[name] = evaluation.influence
        by_cost[str(cost)] = {
            "development_selected_best_static": ACTION_LABELS[best_static_arm],
            "training_static_values": {
                ACTION_LABELS[arm]: value for arm, value in static_train_values.items()
            },
            "heldout_results": rows,
        }

    zero_rows = {
        row["name"]: row for row in by_cost["0.0"]["heldout_results"]
    }
    break_even = {}
    bau_gross = zero_rows["BAU"]["value_per_customer"]
    for name, policy in primary_policies.items():
        gross = evaluate_policy(test_zero, policy, evaluator_test)
        email_rate = float(np.mean(policy != 0))
        break_even[name] = (
            float((gross.value_per_unit - bau_gross) / email_rate)
            if email_rate > 0
            else None
        )

    primary_rows = by_cost[str(PRIMARY_COST)]["heldout_results"]
    personalized_names = set(predictions)
    personalized_rows = [row for row in primary_rows if row["name"] in personalized_names]
    provisional_best = max(personalized_rows, key=lambda row: row["value_per_customer"])
    material = bool(
        provisional_best["versus_best_static"]["point"] >= 0.01
        and provisional_best["versus_best_static"]["lower_95"] > 0
    )

    result: dict[str, Any] = {
        "status": "DEVELOPMENT_ONLY_NO_OFFICIAL_SELECTION",
        "preregistration_sha256": _sha256(PREREGISTRATION),
        "seed": SEED,
        "folds": FOLDS,
        "counts": {
            "development": len(frame),
            "inner_train": len(train_frame),
            "inner_heldout": len(test_frame),
            "overlap": 0,
        },
        "assignment": {
            "arms": list(ACTION_LABELS),
            "known_propensity": 1 / 3,
            "development_counts": {
                ACTION_LABELS[arm]: int(np.sum(action == arm)) for arm in range(3)
            },
        },
        "feature_names": [str(name) for name in transformer.get_feature_names_out()],
        "outcome": "two-week randomized spend/revenue; not profit",
        "cost_grid": list(COST_GRID),
        "primary_cost": PRIMARY_COST,
        "by_cost": by_cost,
        "calibration": calibration,
        "break_even_email_cost": break_even,
        "provisional_best_personalized_at_primary_cost": provisional_best["name"],
        "material_observable_heterogeneity": material,
        "sealed_integrity_incident": {
            "status": "ONE_ROW_DIAGNOSTIC_EXPOSURE",
            "row": "row-0",
            "assigned_split": "SEALED_TEST",
            "used_for_modeling_or_scoring": False,
            "future_sealed_claim": "COMPROMISED_DO_NOT_CLAIM_UNTOUCHED",
        },
        "validation_scored": False,
        "sealed_test_scored": False,
        "official_model_frozen": False,
        "runtime_seconds": time.perf_counter() - started,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    REPORT.write_text(_markdown_report(result))
    return result


def _markdown_report(result: dict[str, Any]) -> str:
    primary = result["by_cost"][str(PRIMARY_COST)]
    rows = sorted(
        primary["heldout_results"], key=lambda row: row["value_per_customer"], reverse=True
    )
    lines = [
        "# Hillstrom V7.2 Development Checkpoint",
        "",
        "Status: **DEVELOPMENT ONLY — NO VALIDATION OR OFFICIAL FREEZE**.",
        "",
        f"Primary declared email cost: `${PRIMARY_COST:.2f}` per recipient. Outcome is two-week",
        "spend/revenue, not profit.",
        "",
        "| Policy | Net value/customer | vs BAU | vs best static | 95% CI vs static |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['name']} | {row['value_per_customer']:.6f} | "
            f"{row['versus_bau']['point']:.6f} | {row['versus_best_static']['point']:.6f} | "
            f"[{row['versus_best_static']['lower_95']:.6f}, "
            f"{row['versus_best_static']['upper_95']:.6f}] |"
        )
    lines.extend(
        [
            "",
            f"Development-selected best static: **{primary['development_selected_best_static']}**.",
            "Provisional personalized leader: "
            f"**{result['provisional_best_personalized_at_primary_cost']}**.",
            "Material observable heterogeneity: "
            f"**{result['material_observable_heterogeneity']}**.",
            "",
            "The static Mens policy's point-estimate increment over BAU is positive but its "
            "95% interval crosses zero on the inner held-out split. The provisional Tweedie "
            "leader does not beat static, and one large negative stability fold dominates.",
            "",
            "The static Mens point-estimate break-even contact cost and the full fixed cost grid "
            "are in the JSON result. The train-development static choice changes to No Email "
            "at the $1.00 and $2.00 grid points.",
            "",
            "## Integrity incident",
            "",
            "During header inspection, row-0 was accidentally printed with outcomes. The existing ",
            "manifest assigns it to SEALED_TEST. It was never used for fitting or scoring, "
            "but the ",
            "future sealed set cannot honestly be called fully untouched. All subsequent ",
            "materialization parsed DEVELOPMENT rows only.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    summary = run()
    print(
        json.dumps(
            {
                "status": summary["status"],
                "provisional_best": summary[
                    "provisional_best_personalized_at_primary_cost"
                ],
                "material_heterogeneity": summary["material_observable_heterogeneity"],
                "runtime_seconds": summary["runtime_seconds"],
            },
            indent=2,
        )
    )
