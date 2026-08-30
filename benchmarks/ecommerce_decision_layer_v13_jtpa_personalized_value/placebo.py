from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .materialize import development_frame
from .qualification import ROOT
from .tournament import (
    FOLDS,
    dr_score,
    encoder,
    feature_frame,
    folds_for,
    lgbm,
)

PLACEBO_RESULTS = ROOT / "V13_PLACEBO_RESULTS.json"
REPLICATES = 20


def t_learner_dr_value(
    frame: pd.DataFrame,
    y: np.ndarray,
    treatment: np.ndarray,
    fold_seed: int,
    model_seed: int,
) -> float:
    working = frame.copy()
    working["treatment"] = treatment
    raw = feature_frame(working)
    fold_id = folds_for(working, fold_seed)
    m0, m1, policy = np.empty(len(y)), np.empty(len(y)), np.empty(len(y), dtype=np.int8)
    for fold in range(FOLDS):
        test = fold_id == fold
        train = ~test
        transform = encoder().fit(raw.loc[train])
        x_train = transform.transform(raw.loc[train])
        x_test = transform.transform(raw.loc[test])
        for arm, target in ((0, m0), (1, m1)):
            rows = treatment[train] == arm
            model = lgbm(model_seed + fold * 100 + arm).fit(x_train[rows], y[train][rows])
            target[test] = model.predict(x_test)
        policy[test] = (m1[test] - m0[test] > 0).astype(np.int8)
    bau = np.zeros(len(y), dtype=np.int8)
    return float(
        np.mean(
            dr_score(policy, y, treatment, m0, m1)
            - dr_score(bau, y, treatment, m0, m1)
        )
    )


def permute_treatment_within_site(
    treatment: np.ndarray,
    site: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    output = treatment.copy()
    for value in np.unique(site):
        rows = np.flatnonzero(site == value)
        output[rows] = rng.permutation(output[rows])
    return output


def run_placebos() -> dict[str, object]:
    frame, access = development_frame()
    if access["validation_outcomes_opened"]:
        raise RuntimeError("validation accessed during V13 placebo suite")
    y = frame["earnings_30m"].to_numpy(dtype=float)
    treatment = frame["treatment"].to_numpy(dtype=np.int8)
    site = frame["site"].astype(str).to_numpy()
    observed = t_learner_dr_value(frame, y, treatment, 1301, 1301)
    rng = np.random.default_rng(1399)
    treatment_null = np.empty(REPLICATES, dtype=float)
    outcome_null = np.empty(REPLICATES, dtype=float)
    for replicate in range(REPLICATES):
        shuffled_treatment = permute_treatment_within_site(treatment, site, rng)
        treatment_null[replicate] = t_learner_dr_value(
            frame,
            y,
            shuffled_treatment,
            1400 + replicate,
            1400 + replicate,
        )
        outcome_null[replicate] = t_learner_dr_value(
            frame,
            rng.permutation(y),
            treatment,
            1500 + replicate,
            1500 + replicate,
        )
    treatment_p = float((1 + np.sum(treatment_null >= observed)) / (REPLICATES + 1))
    outcome_p = float((1 + np.sum(outcome_null >= observed)) / (REPLICATES + 1))
    result: dict[str, object] = {
        "model": "lgbm_t_learner",
        "observed_dr_value_vs_bau": observed,
        "outcome_shuffle": {
            "null_max": float(outcome_null.max()),
            "null_mean": float(outcome_null.mean()),
            "one_sided_p_value": outcome_p,
            "replicates": REPLICATES,
            "values": outcome_null.tolist(),
        },
        "passed_both_placebos": treatment_p <= 0.05 and outcome_p <= 0.05,
        "seed": 1399,
        "treatment_shuffle_within_site": {
            "null_max": float(treatment_null.max()),
            "null_mean": float(treatment_null.mean()),
            "one_sided_p_value": treatment_p,
            "replicates": REPLICATES,
            "values": treatment_null.tolist(),
        },
        "validation_outcomes_opened": False,
    }
    PLACEBO_RESULTS.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    run_placebos()
