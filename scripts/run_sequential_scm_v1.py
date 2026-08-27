"""Known-truth longitudinal SCM correctness benchmark; never real-world evidence."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks/customer_twin_research_v1/sequential_causal_synthetic"
SEED = 20260826
STEPS = 6


def sigmoid(value: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-value))


def simulate(scenario: str, samples: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    state = rng.normal(size=samples)
    prior_action = np.zeros(samples)
    rows = []
    for step in range(STEPS):
        coefficient = {
            "randomized": 0.0,
            "static_confounding": 0.8,
            "time_varying_confounding": 1.1,
            "treatment_affected_confounding": 1.1,
            "weak_overlap": 3.5,
            "heterogeneous_effect": 0.8,
            "delayed_effect": 1.0,
        }[scenario]
        propensity = sigmoid(coefficient * state + 0.4 * prior_action)
        if scenario == "randomized":
            propensity[:] = 0.5
        action = rng.binomial(1, propensity)
        effect = 0.5 + (0.35 * state if scenario == "heterogeneous_effect" else 0)
        delayed = 0.3 * prior_action if scenario == "delayed_effect" else 0
        outcome = 0.6 * state + effect * action + delayed + rng.normal(scale=0.4, size=samples)
        next_state = 0.65 * state + 0.30 * action + rng.normal(scale=0.5, size=samples)
        rows.append(
            pd.DataFrame(
                {
                    "unit": np.arange(samples),
                    "step": step,
                    "state": state,
                    "prior_action": prior_action,
                    "action": action,
                    "propensity": propensity,
                    "outcome": outcome,
                    "next_state": next_state,
                }
            )
        )
        state, prior_action = next_state, action
    return pd.concat(rows, ignore_index=True)


def policy_truth(scenario: str, action_value: int, samples: int = 200_000) -> float:
    rng = np.random.default_rng(SEED + action_value)
    state = rng.normal(size=samples)
    prior = np.zeros(samples)
    total = np.zeros(samples)
    for _ in range(STEPS):
        action = np.full(samples, action_value)
        effect = 0.5 + (0.35 * state if scenario == "heterogeneous_effect" else 0)
        delayed = 0.3 * prior if scenario == "delayed_effect" else 0
        total += 0.6 * state + effect * action + delayed
        state = 0.65 * state + 0.30 * action + rng.normal(scale=0.5, size=samples)
        prior = action
    return float(total.mean())


def estimate(frame: pd.DataFrame, scenario: str) -> dict[str, float | str]:
    transition = LinearRegression().fit(frame[["state", "action"]], frame.next_state)
    outcome = LinearRegression().fit(frame[["state", "action", "prior_action"]], frame.outcome)
    rng = np.random.default_rng(SEED + 99)
    residual = frame.next_state - transition.predict(frame[["state", "action"]])
    estimates = []
    for action_value in (0, 1):
        state = rng.normal(size=50_000)
        prior = np.zeros(len(state))
        total = np.zeros(len(state))
        for _ in range(STEPS):
            action = np.full(len(state), action_value)
            total += outcome.predict(np.column_stack([state, action, prior]))
            mean = transition.predict(np.column_stack([state, action]))
            state = mean + rng.choice(residual.to_numpy(), size=len(state), replace=True)
            prior = action
        estimates.append(float(total.mean()))
    truth = policy_truth(scenario, 1) - policy_truth(scenario, 0)
    gcomp = estimates[1] - estimates[0]
    propensity = (
        LogisticRegression()
        .fit(frame[["state", "prior_action"]], frame.action)
        .predict_proba(frame[["state", "prior_action"]])[:, 1]
    )
    probability = np.where(frame.action == 1, propensity, 1 - propensity)
    weights = np.clip(0.5 / np.clip(probability, 0.01, 1), 0, 20)
    msm = (
        LinearRegression()
        .fit(frame[["action", "step"]], frame.outcome, sample_weight=weights)
        .coef_[0]
        * STEPS
    )
    return {
        "scenario": scenario,
        "true_policy_effect": truth,
        "g_computation_effect": gcomp,
        "g_computation_error": abs(gcomp - truth),
        "msm_effect": float(msm),
        "msm_error": abs(float(msm) - truth),
        "sequential_dr_error": "NOT_IMPLEMENTED",
        "policy_value_error": abs(gcomp - truth),
    }


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scenarios = (
        "randomized",
        "static_confounding",
        "time_varying_confounding",
        "treatment_affected_confounding",
        "weak_overlap",
        "heterogeneous_effect",
        "delayed_effect",
    )
    rows = [
        estimate(simulate(scenario, 30_000, SEED + index), scenario)
        for index, scenario in enumerate(scenarios)
    ]
    pd.DataFrame(rows).to_csv(OUT / "estimator_results.csv", index=False)
    pd.DataFrame(rows)[
        ["scenario", "true_policy_effect", "g_computation_effect", "policy_value_error"]
    ].to_csv(OUT / "policy_results.csv", index=False)
    pd.DataFrame(rows)[
        ["scenario", "g_computation_error", "msm_error", "sequential_dr_error"]
    ].to_csv(OUT / "trajectory_results.csv", index=False)
    spec = {
        "status": "SIMULATED_ONLY",
        "equations": {
            "state": "Z[t+1]=0.65 Z[t]+0.30 A[t]+epsilon",
            "outcome": "Y[t]=0.60 Z[t]+tau(Z[t]) A[t]+delayed+eta",
        },
        "scenarios": scenarios,
        "sequential_dr": "NOT_IMPLEMENTED",
    }
    (OUT / "scm_spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    truth = {row["scenario"]: row["true_policy_effect"] for row in rows}
    (OUT / "ground_truth_effects.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    g_computation_passed = all(float(row["g_computation_error"]) < 0.15 for row in rows)
    # The requested synthetic layer includes sequential DR; missing it is a layer FAIL.
    passed = False
    (OUT / "REPORT.md").write_text(
        "# Sequential causal SCM\n\nSynthetic implementation verdict: **"
        + ("PASS" if passed else "FAIL")
        + "**. This validates only known-SCM g-computation plumbing. "
        "Sequential DR is not implemented. Real-world status: "
        "**REAL MERCHANT RANDOMIZED LONGITUDINAL DATA REQUIRED**.\n",
        encoding="utf-8",
    )
    (OUT / "final_metrics.json").write_text(
        json.dumps(
            {
                "synthetic_implementation": "PASS" if passed else "FAIL",
                "g_computation_component": "PASS" if g_computation_passed else "FAIL",
                "real_world": "UNPROVEN",
                "results": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
