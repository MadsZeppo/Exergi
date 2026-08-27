from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss

from decision_engine.datasets.mt_lift import MTLiftAdapter


def _fit_t_learners(
    x: np.ndarray, treatment: np.ndarray, outcome: np.ndarray, seed: int
) -> dict[int, HistGradientBoostingClassifier]:
    models: dict[int, HistGradientBoostingClassifier] = {}
    for arm in sorted(np.unique(treatment)):
        mask = treatment == arm
        models[int(arm)] = HistGradientBoostingClassifier(
            max_iter=80, max_leaf_nodes=15, min_samples_leaf=50, random_state=seed
        ).fit(x[mask], outcome[mask])
    return models


def run_mt_lift_benchmark(
    root: str | Path = "data/raw/mt_lift",
    output_dir: str | Path = "artifacts/benchmarks/mt_lift",
    *,
    outcome: str = "conversion",
    max_train_rows: int = 500_000,
    max_test_rows: int = 500_000,
    seed: int = 42,
) -> dict[str, Any]:
    """Fit on publisher train, freeze all-arm predictions, then reveal test outcomes."""
    adapter = MTLiftAdapter(root)
    if not adapter.available():
        raise FileNotFoundError("publisher-provided MT-LIFT train.csv and test.csv are required")
    train = adapter.load_split("train").head(max_train_rows).collect()
    test = adapter.load_split("test").head(max_test_rows).collect()
    features = list(adapter.feature_columns)
    x_train = train.select(features).to_numpy()
    x_test = test.select(features).to_numpy()
    t_train = train["treatment"].to_numpy().astype(int)
    y_train = train[outcome].to_numpy().astype(int)
    models = _fit_t_learners(x_train, t_train, y_train, seed)
    arms = sorted(models)
    frozen = np.column_stack([models[arm].predict_proba(x_test)[:, 1] for arm in arms])
    recommended = np.asarray(arms)[np.argmax(frozen, axis=1)]
    frozen_frame = pl.DataFrame(
        {
            **{f"predicted_y_arm_{arm}": frozen[:, index] for index, arm in enumerate(arms)},
            "recommended_treatment": recommended,
        }
    )
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    frozen_frame.write_parquet(target / "frozen_predictions.parquet")

    observed_treatment = test["treatment"].to_numpy().astype(int)
    observed_outcome = test[outcome].to_numpy().astype(int)
    arm_to_index = {arm: index for index, arm in enumerate(arms)}
    factual_prediction = np.array(
        [frozen[row, arm_to_index[arm]] for row, arm in enumerate(observed_treatment)]
    )
    arm_rates = {arm: float(np.mean(observed_outcome[observed_treatment == arm])) for arm in arms}
    best_static = max(arm_rates, key=arm_rates.get)  # type: ignore[arg-type]
    propensity = 1.0 / len(arms)
    policy_value = float(
        np.mean(observed_outcome * (recommended == observed_treatment) / propensity)
    )
    result = {
        "dataset": "MT-LIFT",
        "design": adapter.design.__dict__,
        "outcome": outcome,
        "train_rows": train.height,
        "test_rows": test.height,
        "frozen_before_outcome_evaluation": True,
        "factual_log_loss": float(log_loss(observed_outcome, factual_prediction)),
        "randomized_arm_rates": arm_rates,
        "best_static_treatment": int(best_static),
        "best_static_value": arm_rates[best_static],
        "policy_value_ipw": policy_value,
        "policy_regret_vs_best_static": float(arm_rates[best_static] - policy_value),
        "interpretation": "randomized customer-action evidence; no World State evidence",
    }
    (target / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
