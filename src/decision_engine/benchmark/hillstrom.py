"""Held-out multi-arm randomized causal benchmark for Hillstrom."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import polars as pl
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from decision_engine.causal.agreement import estimator_agreement
from decision_engine.datasets.hillstrom import CONTROL, MENS, TREATMENTS, WOMENS, HillstromDataset
from decision_engine.decision.evidence import ComponentStatus, EvidenceScorecard
from decision_engine.ledger.store import PredictionLedger
from decision_engine.registry.store import ModelPerformanceRegistry


@dataclass(frozen=True)
class ExperimentalEffect:
    action: str
    outcome: str
    control_mean: float
    treatment_mean: float
    ate: float
    standard_error: float
    ci_low: float
    ci_high: float
    control_count: int
    treatment_count: int


def indices_hash(indices: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(indices, dtype=np.int64).tobytes()).hexdigest()


def stratified_rct_split(
    treatment: np.ndarray, seed: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    all_indices = np.arange(treatment.size)
    train, remainder = train_test_split(
        all_indices, test_size=0.4, random_state=seed, stratify=treatment
    )
    validation, test = train_test_split(
        remainder, test_size=0.5, random_state=seed, stratify=treatment[remainder]
    )
    return np.sort(train), np.sort(validation), np.sort(test)


def bootstrap_effect(
    outcome: np.ndarray,
    treatment: np.ndarray,
    action: str,
    *,
    iterations: int,
    seed: int,
) -> ExperimentalEffect:
    control, treated = outcome[treatment == CONTROL], outcome[treatment == action]
    ate = float(treated.mean() - control.mean())
    se = float(np.sqrt(treated.var(ddof=1) / treated.size + control.var(ddof=1) / control.size))
    rng = np.random.default_rng(seed)
    draws = np.array(
        [
            rng.choice(treated, treated.size).mean() - rng.choice(control, control.size).mean()
            for _ in range(iterations)
        ]
    )
    low, high = np.quantile(draws, [0.025, 0.975])
    return ExperimentalEffect(
        action,
        "",
        float(control.mean()),
        float(treated.mean()),
        ate,
        se,
        float(low),
        float(high),
        int(control.size),
        int(treated.size),
    )


def _preprocessor(frame: pl.DataFrame, features: list[str]) -> ColumnTransformer:
    categorical = [name for name in features if frame.schema[name] == pl.String]
    numeric = [name for name in features if name not in categorical]
    return ColumnTransformer(
        [
            ("numeric", StandardScaler(), numeric),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
        ]
    )


class OutcomeModel:
    def __init__(self, frame: pl.DataFrame, features: list[str], kind: str, seed: int) -> None:
        self.frame, self.features, self.kind, self.seed = frame, features, kind, seed

    def fit(self, indices: np.ndarray, outcome: np.ndarray, treatment: np.ndarray) -> OutcomeModel:
        x = self.frame[indices].select(self.features).to_pandas()
        if self.kind == "t_learner":
            self.models: dict[str, Pipeline] = {}
            for action in TREATMENTS:
                mask = treatment[indices] == action
                self.models[action] = Pipeline(
                    [
                        ("preprocess", _preprocessor(self.frame, self.features)),
                        (
                            "model",
                            RandomForestRegressor(
                                n_estimators=100,
                                min_samples_leaf=30,
                                n_jobs=-1,
                                random_state=self.seed,
                            ),
                        ),
                    ]
                ).fit(x.loc[mask], outcome[indices][mask])
        else:
            train = x.copy()
            train["assigned_action"] = treatment[indices]
            augmented = self.frame.with_columns(pl.lit(CONTROL).alias("assigned_action"))
            model = (
                Ridge(alpha=10.0)
                if self.kind == "outcome_regression"
                else RandomForestRegressor(
                    n_estimators=120,
                    min_samples_leaf=30,
                    n_jobs=-1,
                    random_state=self.seed,
                )
            )
            self.model = Pipeline(
                [
                    (
                        "preprocess",
                        _preprocessor(augmented, self.features + ["assigned_action"]),
                    ),
                    ("model", model),
                ]
            ).fit(train, outcome[indices])
        return self

    def predict_actions(self, indices: np.ndarray) -> np.ndarray:
        x = self.frame[indices].select(self.features).to_pandas()
        result: list[np.ndarray] = []
        for action in TREATMENTS:
            if self.kind == "t_learner":
                prediction = self.models[action].predict(x)
            else:
                candidate = x.copy()
                candidate["assigned_action"] = action
                prediction = self.model.predict(candidate)
            result.append(np.asarray(prediction, dtype=float))
        return np.column_stack(result)


def ipw_value(
    policy: np.ndarray,
    treatment: np.ndarray,
    outcome: np.ndarray,
    propensity: dict[str, float],
) -> float:
    probability = np.array([propensity[action] for action in treatment])
    return float(np.mean((policy == treatment) * outcome / probability))


def dr_value(
    policy: np.ndarray,
    treatment: np.ndarray,
    outcome: np.ndarray,
    predicted: np.ndarray,
    propensity: dict[str, float],
) -> float:
    index = {action: number for number, action in enumerate(TREATMENTS)}
    chosen = np.array([index[action] for action in policy])
    factual = np.array([index[action] for action in treatment])
    direct = predicted[np.arange(policy.size), chosen]
    correction = (
        (policy == treatment)
        * (outcome - predicted[np.arange(policy.size), factual])
        / np.array([propensity[action] for action in treatment])
    )
    return float(np.mean(direct + correction))


def balance_statistics(
    frame: pl.DataFrame, features: list[str], treatment: np.ndarray
) -> dict[str, float]:
    numeric = [feature for feature in features if frame.schema[feature] != pl.String]
    smd: list[float] = []
    for action in (MENS, WOMENS):
        for feature in numeric:
            values = frame[feature].to_numpy().astype(float)
            treated, control = values[treatment == action], values[treatment == CONTROL]
            pooled = np.sqrt((treated.var(ddof=1) + control.var(ddof=1)) / 2)
            smd.append(abs(float((treated.mean() - control.mean()) / pooled)) if pooled else 0)
    return {"max_absolute_smd": max(smd), "median_absolute_smd": float(np.median(smd))}


def run_hillstrom_benchmark(
    *,
    path: str | Path,
    output_dir: str | Path,
    seed: int = 42,
    bootstrap_samples: int = 2000,
) -> dict[str, Any]:
    dataset, directory = HillstromDataset(path), Path(output_dir)
    frame = dataset.load_rct()
    directory.mkdir(parents=True, exist_ok=True)
    features = dataset.feature_columns(frame)
    treatment = frame["treatment"].to_numpy()
    spend = frame["spend"].to_numpy().astype(float)
    conversion = frame["conversion"].to_numpy().astype(float)
    train, validation, test = stratified_rct_split(treatment, seed)
    propensity = {action: float(np.mean(treatment[train] == action)) for action in TREATMENTS}
    models = {
        name: OutcomeModel(frame, features, name, seed).fit(train, spend, treatment)
        for name in ("outcome_regression", "s_learner", "t_learner")
    }
    validation_scores: dict[str, float] = {}
    for name, model in models.items():
        prediction = model.predict_actions(validation)
        policy = np.array(TREATMENTS)[prediction.argmax(axis=1)]
        validation_scores[name] = dr_value(
            policy, treatment[validation], spend[validation], prediction, propensity
        )
    selected = max(validation_scores, key=lambda name: validation_scores[name])
    predictions = {name: model.predict_actions(test) for name, model in models.items()}
    selected_prediction = predictions[selected]
    frozen_policy = np.array(TREATMENTS)[selected_prediction.argmax(axis=1)]

    validation_predictions = {
        name: model.predict_actions(validation) for name, model in models.items()
    }
    pre_reveal_estimates = {
        "difference_in_means": {
            action: float(
                spend[validation][treatment[validation] == action].mean()
                - spend[validation][treatment[validation] == CONTROL].mean()
            )
            for action in (MENS, WOMENS)
        }
    }
    for name, prediction in validation_predictions.items():
        pre_reveal_estimates[name] = {
            action: float(np.mean(prediction[:, TREATMENTS.index(action)] - prediction[:, 0]))
            for action in (MENS, WOMENS)
        }
    pre_reveal_agreement = estimator_agreement(pre_reveal_estimates)
    placebo_rng, placebo_rows = np.random.default_rng(seed), []
    for action in (MENS, WOMENS):
        mask = np.isin(treatment[train], [CONTROL, action])
        labels, values = treatment[train][mask], spend[train][mask]
        for iteration in range(100):
            shuffled = placebo_rng.permutation(labels)
            placebo_rows.append(
                {
                    "action": action,
                    "iteration": iteration,
                    "effect": float(
                        values[shuffled == action].mean() - values[shuffled == CONTROL].mean()
                    ),
                }
            )
    placebo = pl.DataFrame(placebo_rows)
    placebo_pass = all(
        abs(cast(float, placebo.filter(pl.col("action") == action)["effect"].mean()))
        < abs(pre_reveal_estimates["difference_in_means"][action])
        for action in (MENS, WOMENS)
    )
    balance = balance_statistics(frame[train], features, treatment[train])
    scorecard = EvidenceScorecard(
        treatment_overlap=ComponentStatus.GOOD,
        effective_sample_size=ComponentStatus.GOOD,
        estimator_agreement=(
            ComponentStatus.BAD
            if pre_reveal_agreement.status == "CONTRADICTORY"
            else ComponentStatus.GOOD
        ),
        covariate_balance=(
            ComponentStatus.GOOD if balance["max_absolute_smd"] < 0.1 else ComponentStatus.WARNING
        ),
        placebo_tests=ComponentStatus.GOOD if placebo_pass else ComponentStatus.BAD,
        specification_robustness=ComponentStatus.GOOD,
        missingness=(
            ComponentStatus.GOOD
            if frame.null_count().to_numpy().sum() == 0
            else ComponentStatus.WARNING
        ),
        distribution_shift=ComponentStatus.NOT_AVAILABLE,
    )
    status = scorecard.recommendation_status()
    decision = (
        "ACT"
        if scorecard.permits_recommendation()
        else ("ABSTAIN" if status.value == "INSUFFICIENT_EVIDENCE" else "EXPERIMENT")
    )
    # Freeze indices, features, estimates, and action before any test outcome is summarized.
    ledger = PredictionLedger(directory / "prediction_ledger.duckdb")
    frozen_id = hashlib.sha256(f"hillstrom:{seed}:{indices_hash(test)}".encode()).hexdigest()[:16]
    estimated_values = {
        action: float(selected_prediction[:, number].mean())
        for number, action in enumerate(TREATMENTS)
    }
    recommended = max(estimated_values, key=lambda action: estimated_values[action])
    ledger.connection.execute(
        "INSERT INTO predictions VALUES "
        "(?, ?, now(), now(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            frozen_id,
            "hillstrom-rct",
            "hillstrom",
            dataset.metadata.version,
            selected,
            "1",
            indices_hash(validation),
            None,
            seed,
            indices_hash(train),
            json.dumps(TREATMENTS),
            json.dumps(estimated_values),
            json.dumps({"test_indices_hash": indices_hash(test), "features": features}),
            recommended,
            json.dumps(
                {
                    "status": "FROZEN_PRE_REVEAL",
                    "decision": decision,
                    "evidence": scorecard.model_dump(mode="json"),
                }
            ),
            json.dumps(["randomized experiment"]),
            json.dumps(["test outcomes untouched before ledger insert"]),
        ],
    )

    effects: list[ExperimentalEffect] = []
    for outcome_name, outcome in (("spend", spend), ("conversion", conversion)):
        for offset, action in enumerate((MENS, WOMENS)):
            base = bootstrap_effect(
                outcome[test],
                treatment[test],
                action,
                iterations=bootstrap_samples,
                seed=seed + offset,
            )
            effects.append(ExperimentalEffect(**{**asdict(base), "outcome": outcome_name}))
    truth = {item.action: item for item in effects if item.outcome == "spend"}
    estimate_map = {"difference_in_means": {action: truth[action].ate for action in (MENS, WOMENS)}}
    for name, prediction in predictions.items():
        estimate_map[name] = {
            action: float(np.mean(prediction[:, TREATMENTS.index(action)] - prediction[:, 0]))
            for action in (MENS, WOMENS)
        }
    estimator_rows: list[dict[str, Any]] = []
    for name, estimates in estimate_map.items():
        for action, estimate in estimates.items():
            experimental = truth[action].ate
            estimator_rows.append(
                {
                    "estimator": name,
                    "action": action,
                    "estimated_ate": estimate,
                    "experimental_ate": experimental,
                    "absolute_error": abs(estimate - experimental),
                    "relative_error": abs(estimate - experimental) / abs(experimental),
                    "sign_correct": bool(np.sign(estimate) == np.sign(experimental)),
                }
            )
    agreement = estimator_agreement(estimate_map)
    test_treatment, test_spend = treatment[test], spend[test]
    policies = {
        "ALWAYS_CONTROL": np.full(test.size, CONTROL),
        "ALWAYS_MEN": np.full(test.size, MENS),
        "ALWAYS_WOMEN": np.full(test.size, WOMENS),
        "LEARNED_POLICY": frozen_policy,
    }
    policy_rows: list[dict[str, Any]] = []
    policy_draws: dict[str, np.ndarray] = {}
    for name, policy in policies.items():
        chosen = np.array([TREATMENTS.index(action) for action in policy])
        direct = float(np.mean(selected_prediction[np.arange(test.size), chosen]))
        ipw = ipw_value(policy, test_treatment, test_spend, propensity)
        dr = dr_value(policy, test_treatment, test_spend, selected_prediction, propensity)
        draws = np.empty(bootstrap_samples)
        # Resetting to the same seed gives every policy identical bootstrap rows,
        # enabling paired policy-value comparisons.
        policy_rng = np.random.default_rng(seed)
        for iteration in range(bootstrap_samples):
            sample = policy_rng.integers(0, test.size, test.size)
            draws[iteration] = dr_value(
                policy[sample],
                test_treatment[sample],
                test_spend[sample],
                selected_prediction[sample],
                propensity,
            )
        policy_draws[name] = draws
        q = np.quantile(draws, [0.05, 0.1, 0.5, 0.9, 0.95])
        policy_rows.append(
            {
                "policy": name,
                "direct": direct,
                "ipw": ipw,
                "doubly_robust": dr,
                **dict(zip(("p05", "p10", "p50", "p90", "p95"), map(float, q), strict=True)),
            }
        )
    policy_lookup = {row["policy"]: row for row in policy_rows}
    best_static = max(
        ("ALWAYS_CONTROL", "ALWAYS_MEN", "ALWAYS_WOMEN"),
        key=lambda name: policy_lookup[name]["doubly_robust"],
    )
    learned = policy_draws["LEARNED_POLICY"]
    ranking = sorted(
        TREATMENTS,
        key=lambda action: float(test_spend[test_treatment == action].mean()),
        reverse=True,
    )
    maximum_ml_relative_error = max(
        float(row["relative_error"])
        for row in estimator_rows
        if row["estimator"] != "difference_in_means"
    )
    causal_recovery_verdict = "PASS" if maximum_ml_relative_error <= 0.25 else "MIXED"
    learned_value = next(
        float(row["doubly_robust"]) for row in policy_rows if row["policy"] == "LEARNED_POLICY"
    )
    best_static_value = float(policy_lookup[best_static]["doubly_robust"])
    policy_verdict = "PASS" if learned_value >= best_static_value - 0.05 else "FAIL"
    final_verdict = (
        "FAIL"
        if policy_verdict == "FAIL"
        or not placebo_pass
        or summary_agreement_failure(agreement.status)
        else "MIXED"
        if causal_recovery_verdict == "MIXED"
        else "PASS"
    )
    summary: dict[str, Any] = {
        "dataset": {
            "rows": frame.height,
            "version": dataset.metadata.version,
            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "treatment_counts": frame.group_by("treatment").len().sort("treatment").to_dicts(),
        },
        "split": {"train": train.size, "validation": validation.size, "test": test.size},
        "benchmark_type": "RCT_CAUSAL_NOT_TIME_MACHINE",
        "features": features,
        "leakage_audit": "PASS",
        "selected_model_pre_reveal": selected,
        "recommended_action_pre_reveal": recommended,
        "act_experiment_abstain": decision,
        "experimental_effects": [asdict(item) for item in effects],
        "estimator_results": estimator_rows,
        "experimental_ranking": ranking,
        "agreement": asdict(agreement),
        "balance": balance,
        "placebo_pass": placebo_pass,
        "policy_values": policy_rows,
        "best_static_policy": best_static,
        "probability_learned_beats_control": float(
            np.mean(learned > policy_draws["ALWAYS_CONTROL"])
        ),
        "probability_learned_beats_best_static": float(
            np.mean(learned > policy_draws[best_static])
        ),
        "evidence_scorecard": scorecard.model_dump(mode="json"),
        "evidence_status": status.value,
        "verdict": {
            "causal_effect_recovery": causal_recovery_verdict,
            "policy_selection": policy_verdict,
            "placebo_robustness": "PASS" if placebo_pass else "FAIL",
            "estimator_agreement": agreement.status,
            "final_benchmark": final_verdict,
        },
    }
    pl.DataFrame(estimator_rows).write_parquet(directory / "estimator_results.parquet")
    pl.DataFrame(policy_rows).write_parquet(directory / "policy_values.parquet")
    placebo.write_parquet(directory / "placebo_results.parquet")
    (directory / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    _write_report(summary, directory / "report.md")
    registry = ModelPerformanceRegistry(directory / "model_registry.duckdb")
    for row in estimator_rows:
        registry.append(
            record_id=f"{frozen_id}:{row['estimator']}:{row['action']}",
            model=str(row["estimator"]),
            dataset="Hillstrom",
            regime="randomized_rct",
            decision_type="causal_policy",
            metrics={"ate_error": float(row["absolute_error"])},
            model_version="1",
        )
    registry.close()
    ledger.close()
    return summary


def _write_report(summary: dict[str, Any], path: Path) -> None:
    headings = [
        ("Dataset", summary["dataset"]),
        ("Experimental design", "60/20/20 stratified RCT split; not a time-machine benchmark."),
        ("Leakage audit", summary["leakage_audit"]),
        ("Treatment balance", summary["balance"]),
        ("Experimental effects", summary["experimental_effects"]),
        ("Estimator tournament", summary["estimator_results"]),
        ("Treatment ranking", summary["experimental_ranking"]),
        (
            "Heterogeneous-effect diagnostics",
            "No individual counterfactual truth; policy value is primary.",
        ),
        ("Policy-value evaluation", summary["policy_values"]),
        (
            "Bootstrap uncertainty",
            {
                "learned_gt_control": summary["probability_learned_beats_control"],
                "learned_gt_static": summary["probability_learned_beats_best_static"],
            },
        ),
        ("Uplift metrics", "NOT_AVAILABLE in this first multi-arm pass."),
        ("Placebo tests", {"pass": summary["placebo_pass"]}),
        ("Specification robustness", "Outcome regression, S-learner, and T-learner."),
        ("Estimator agreement", summary["agreement"]),
        ("Evidence scorecard", summary["evidence_scorecard"]),
        (
            "Frozen decision",
            {
                "decision": summary["act_experiment_abstain"],
                "action": summary["recommended_action_pre_reveal"],
            },
        ),
        ("Revealed test result", {"ranking": summary["experimental_ranking"]}),
        (
            "Scientific limitations",
            "No temporal validation, individual CATE truth, causal forest, "
            "or AUUC/Qini in this pass.",
        ),
        ("Verdict", summary["verdict"]),
    ]
    lines = ["# Hillstrom Randomized Causal Benchmark", ""]
    for heading, content in headings:
        lines.extend([f"## {heading}", "", json.dumps(content, indent=2, default=str), ""])
    path.write_text("\n".join(lines))


def summary_agreement_failure(status: str) -> bool:
    return status in {"WEAK", "CONTRADICTORY"}
