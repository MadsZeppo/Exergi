from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import lightgbm as lgb
import numpy as np
import polars as pl

from decision_engine.datasets.criteo_uplift import CriteoUpliftAdapter
from decision_engine.ledger import PredictionLedger
from decision_engine.registry import ModelPerformanceRegistry


class UpliftPredictor(Protocol):
    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...


@dataclass(frozen=True)
class CriteoBenchmarkConfig:
    source_path: Path = Path("data/raw/criteo/criteo-research-uplift-v2.1.csv.gz")
    parquet_path: Path = Path("data/processed/criteo/criteo-uplift-v2.1.parquet")
    output_dir: Path = Path("artifacts/benchmarks/criteo/definitive-seed-42-v2")
    seed: int = 42
    outcome: str = "conversion"
    n_estimators: int = 120
    sample_fractions: tuple[float, ...] = (0.01, 0.05, 0.10, 0.25, 0.50, 1.00)
    policy_fractions: tuple[float, ...] = (0.05, 0.10, 0.20, 0.30, 0.50, 1.00)


def _classifier(seed: int, n_estimators: int) -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(
        objective="binary",
        n_estimators=n_estimators,
        learning_rate=0.06,
        num_leaves=31,
        min_child_samples=1000,
        subsample=0.8,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=-1,
        verbosity=-1,
    )


def _regressor(seed: int, n_estimators: int) -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(
        objective="regression",
        n_estimators=n_estimators,
        learning_rate=0.06,
        num_leaves=31,
        min_child_samples=1000,
        subsample=0.8,
        colsample_bytree=0.9,
        reg_lambda=2.0,
        random_state=seed,
        n_jobs=-1,
        verbosity=-1,
    )


def _positive_probability(model: lgb.LGBMClassifier, x: np.ndarray) -> np.ndarray:
    return np.asarray(model.predict_proba(x), dtype=float)[:, 1]


def _regression_prediction(model: lgb.LGBMRegressor, x: np.ndarray) -> np.ndarray:
    return np.asarray(model.predict(x), dtype=float)


class StaticATEModel:
    def __init__(self, ate: float, control_rate: float) -> None:
        self.ate = ate
        self.control_rate = control_rate

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p0 = np.full(len(x), self.control_rate)
        uplift = np.full(len(x), self.ate)
        return p0, np.clip(p0 + uplift, 0, 1), uplift


class OutcomePropensityModel:
    def __init__(self, model: lgb.LGBMClassifier) -> None:
        self.model = model

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        response = _positive_probability(self.model, x)
        return response, response, response


class SLearnerModel:
    def __init__(self, model: lgb.LGBMClassifier) -> None:
        self.model = model

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p0 = _positive_probability(self.model, np.column_stack([x, np.zeros(len(x))]))
        p1 = _positive_probability(self.model, np.column_stack([x, np.ones(len(x))]))
        return p0, p1, p1 - p0


class TLearnerModel:
    def __init__(self, control: lgb.LGBMClassifier, treated: lgb.LGBMClassifier) -> None:
        self.control = control
        self.treated = treated

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p0 = _positive_probability(self.control, x)
        p1 = _positive_probability(self.treated, x)
        return p0, p1, p1 - p0


class XLearnerModel:
    def __init__(
        self,
        outcome: TLearnerModel,
        control_effect: lgb.LGBMRegressor,
        treated_effect: lgb.LGBMRegressor,
        propensity: float,
    ) -> None:
        self.outcome = outcome
        self.control_effect = control_effect
        self.treated_effect = treated_effect
        self.propensity = propensity

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p0, p1, _ = self.outcome.predict(x)
        uplift = self.propensity * _regression_prediction(self.control_effect, x) + (
            1 - self.propensity
        ) * _regression_prediction(self.treated_effect, x)
        center = (p0 + p1) / 2
        return (
            np.clip(center - uplift / 2, 0, 1),
            np.clip(center + uplift / 2, 0, 1),
            uplift,
        )


class DRLearnerModel:
    def __init__(
        self,
        effect: lgb.LGBMRegressor,
        outcome: TLearnerModel,
    ) -> None:
        self.effect = effect
        self.outcome = outcome

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p0, p1, _ = self.outcome.predict(x)
        uplift = _regression_prediction(self.effect, x)
        center = (p0 + p1) / 2
        return (
            np.clip(center - uplift / 2, 0, 1),
            np.clip(center + uplift / 2, 0, 1),
            uplift,
        )


def _fit_models(
    x: np.ndarray,
    treatment: np.ndarray,
    outcome: np.ndarray,
    row_ids: np.ndarray,
    config: CriteoBenchmarkConfig,
) -> dict[str, UpliftPredictor]:
    propensity = float(np.mean(treatment))
    control_rate = float(np.mean(outcome[treatment == 0]))
    treated_rate = float(np.mean(outcome[treatment == 1]))
    models: dict[str, UpliftPredictor] = {
        "static_treat_all": StaticATEModel(treated_rate - control_rate, control_rate)
    }
    outcome_model = _classifier(config.seed, config.n_estimators).fit(x, outcome)
    models["outcome_propensity"] = OutcomePropensityModel(outcome_model)
    s_model = _classifier(config.seed + 1, config.n_estimators).fit(
        np.column_stack([x, treatment]), outcome
    )
    models["s_learner"] = SLearnerModel(s_model)
    control = _classifier(config.seed + 2, config.n_estimators).fit(
        x[treatment == 0], outcome[treatment == 0]
    )
    treated = _classifier(config.seed + 3, config.n_estimators).fit(
        x[treatment == 1], outcome[treatment == 1]
    )
    t_model = TLearnerModel(control, treated)
    models["t_learner"] = t_model
    p0_train, p1_train, _ = t_model.predict(x)
    d0 = p1_train[treatment == 0] - outcome[treatment == 0]
    d1 = outcome[treatment == 1] - p0_train[treatment == 1]
    control_effect = _regressor(config.seed + 4, config.n_estimators).fit(x[treatment == 0], d0)
    treated_effect = _regressor(config.seed + 5, config.n_estimators).fit(x[treatment == 1], d1)
    models["x_learner"] = XLearnerModel(t_model, control_effect, treated_effect, propensity)

    pseudo = np.empty(len(x), dtype=float)
    for fold in (0, 1):
        validation = row_ids % 2 == fold
        training = ~validation
        fold_control = _classifier(config.seed + 10 + fold, config.n_estimators).fit(
            x[training & (treatment == 0)], outcome[training & (treatment == 0)]
        )
        fold_treated = _classifier(config.seed + 12 + fold, config.n_estimators).fit(
            x[training & (treatment == 1)], outcome[training & (treatment == 1)]
        )
        m0 = _positive_probability(fold_control, x[validation])
        m1 = _positive_probability(fold_treated, x[validation])
        t_valid = treatment[validation]
        y_valid = outcome[validation]
        pseudo[validation] = (
            m1
            - m0
            + t_valid * (y_valid - m1) / propensity
            - (1 - t_valid) * (y_valid - m0) / (1 - propensity)
        )
    effect = _regressor(config.seed + 20, config.n_estimators).fit(x, pseudo)
    models["dr_learner"] = DRLearnerModel(effect, t_model)
    models["commercial_twin_dr"] = models["dr_learner"]
    return models


def uplift_ranking_metrics(
    outcome: np.ndarray, treatment: np.ndarray, score: np.ndarray, propensity: float
) -> dict[str, float]:
    order = _score_order(score, descending=True)
    y = outcome[order]
    t = treatment[order]
    n = len(y)
    treated_count = np.cumsum(t)
    control_count = np.cumsum(1 - t)
    treated_y = np.cumsum(y * t)
    control_y = np.cumsum(y * (1 - t))
    uplift = treated_y / np.maximum(treated_count, 1) - control_y / np.maximum(control_count, 1)
    fraction = np.arange(1, n + 1) / n
    ate = float(np.mean(y[t == 1]) - np.mean(y[t == 0]))
    auuc = float(np.trapezoid(uplift - ate, fraction))
    influence = y * t / propensity - y * (1 - t) / (1 - propensity)
    cumulative = np.cumsum(influence) / n
    qini = float(np.trapezoid(cumulative - fraction * cumulative[-1], fraction))
    return {"auuc": auuc, "qini": qini, "observed_ate": ate}


def uplift_calibration(
    outcome: np.ndarray,
    treatment: np.ndarray,
    score: np.ndarray,
    bins: int = 10,
) -> list[dict[str, float]]:
    order = _score_order(score, descending=False)
    rows: list[dict[str, float]] = []
    for index, positions in enumerate(np.array_split(order, bins), start=1):
        t = treatment[positions]
        y = outcome[positions]
        treated = y[t == 1]
        control = y[t == 0]
        if len(treated) == 0 or len(control) == 0:
            raise ValueError("calibration bin lacks a randomized treatment arm")
        observed = float(np.mean(treated) - np.mean(control))
        se = float(
            np.sqrt(
                np.var(treated, ddof=1) / max(len(treated), 1)
                + np.var(control, ddof=1) / max(len(control), 1)
            )
        )
        rows.append(
            {
                "bin": float(index),
                "rows": float(len(positions)),
                "predicted_uplift": float(np.mean(score[positions])),
                "observed_uplift": observed,
                "standard_error": se,
                "lower_90": observed - 1.645 * se,
                "upper_90": observed + 1.645 * se,
                "score_min": float(np.min(score[positions])),
                "score_max": float(np.max(score[positions])),
            }
        )
    return rows


def policy_table(
    outcome: np.ndarray,
    treatment: np.ndarray,
    score: np.ndarray,
    fractions: tuple[float, ...],
    propensity: float,
) -> list[dict[str, float | str]]:
    n = len(outcome)
    order = _score_order(score, descending=True)
    none_influence = outcome * (1 - treatment) / (1 - propensity)
    all_influence = outcome * treatment / propensity
    none_value = float(np.mean(none_influence))
    all_value = float(np.mean(all_influence))
    rows: list[dict[str, float | str]] = []
    for fraction in fractions:
        targeted = np.zeros(n, dtype=bool)
        targeted[order[: int(round(n * fraction))]] = True
        influence = np.where(targeted, all_influence, none_influence)
        value = float(np.mean(influence))
        standard_error = float(np.std(influence, ddof=1) / np.sqrt(n))
        random_value = fraction * all_value + (1 - fraction) * none_value
        rows.append(
            {
                "policy": f"TOP_{int(fraction * 100)}%" if fraction < 1 else "ALL",
                "treatment_fraction": fraction,
                "policy_value": value,
                "standard_error": standard_error,
                "lower_90": value - 1.645 * standard_error,
                "upper_90": value + 1.645 * standard_error,
                "incremental_rate_vs_none": value - none_value,
                "incremental_conversions_vs_none": (value - none_value) * n,
                "random_policy_value": random_value,
                "value_over_random": value - random_value,
            }
        )
    rows.append(
        {
            "policy": "NONE",
            "treatment_fraction": 0.0,
            "policy_value": none_value,
            "standard_error": float(np.std(none_influence, ddof=1) / np.sqrt(n)),
            "lower_90": none_value,
            "upper_90": none_value,
            "incremental_rate_vs_none": 0.0,
            "incremental_conversions_vs_none": 0.0,
            "random_policy_value": none_value,
            "value_over_random": 0.0,
        }
    )
    best = max(float(row["policy_value"]) for row in rows)
    for row in rows:
        row["regret_vs_best_available"] = best - float(row["policy_value"])
    return rows


def _score_order(score: np.ndarray, *, descending: bool) -> np.ndarray:
    """Order scores with a deterministic treatment/outcome-blind tie breaker."""
    positions = np.arange(len(score), dtype=np.uint64)
    secondary = (positions * np.uint64(11_400_714_819_323_198_485)) ^ np.uint64(
        7_046_029_254_386_353_131
    )
    primary = -score if descending else score
    return np.lexsort((secondary, primary))


def masked_policy_value(
    outcome: np.ndarray,
    treatment: np.ndarray,
    targeted: np.ndarray,
    propensity: float,
) -> dict[str, float]:
    treated_influence = outcome * treatment / propensity
    control_influence = outcome * (1 - treatment) / (1 - propensity)
    influence = np.where(targeted, treated_influence, control_influence)
    value = float(np.mean(influence))
    standard_error = float(np.std(influence, ddof=1) / np.sqrt(len(outcome)))
    return {
        "acted_fraction": float(np.mean(targeted)),
        "policy_value": value,
        "standard_error": standard_error,
        "lower_90": value - 1.645 * standard_error,
        "upper_90": value + 1.645 * standard_error,
    }


def uplift_bin_assignments(score: np.ndarray, bins: int = 10) -> np.ndarray:
    assignment = np.empty(len(score), dtype=int)
    for index, positions in enumerate(np.array_split(_score_order(score, descending=False), bins)):
        assignment[positions] = index + 1
    return assignment


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _freeze_predictions(
    path: Path,
    row_ids: np.ndarray,
    p0: np.ndarray,
    p1: np.ndarray,
    uplift: np.ndarray,
) -> None:
    pl.DataFrame(
        {"row_id": row_ids, "p_control": p0, "p_treatment": p1, "uplift": uplift}
    ).write_parquet(path, compression="zstd")


def _load_split(
    parquet: Path, split: str, features: tuple[str, ...], outcome: str | None
) -> pl.DataFrame:
    scan = CriteoUpliftAdapter.split(pl.scan_parquet(parquet), split)
    columns = ["row_id", *features]
    if outcome is not None:
        columns.extend(["treatment", outcome])
    return scan.select(columns).collect()


def run_criteo_benchmark(config: CriteoBenchmarkConfig | None = None) -> Path:
    config = config or CriteoBenchmarkConfig()
    started = time.perf_counter()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    adapter = CriteoUpliftAdapter(config.source_path)
    profile = adapter.validate()
    parquet = adapter.prepare_parquet(config.parquet_path)
    train = _load_split(parquet, "train", adapter.feature_columns, config.outcome)
    development = _load_split(parquet, "development", adapter.feature_columns, config.outcome)
    test_features = _load_split(parquet, "test", adapter.feature_columns, None)
    x_train = train.select(adapter.feature_columns).to_numpy()
    t_train = train["treatment"].to_numpy().astype(int)
    y_train = train[config.outcome].to_numpy().astype(int)
    models = _fit_models(x_train, t_train, y_train, train["row_id"].to_numpy(), config)
    del x_train
    x_development = development.select(adapter.feature_columns).to_numpy()
    x_test = test_features.select(adapter.feature_columns).to_numpy()
    ledger = PredictionLedger(config.output_dir / "prediction_ledger.duckdb")
    frozen: dict[str, dict[str, Path]] = {}
    for name, model in models.items():
        frozen[name] = {}
        for split, x_values, ids in (
            ("development", x_development, development["row_id"].to_numpy()),
            ("test", x_test, test_features["row_id"].to_numpy()),
        ):
            p0, p1, uplift = model.predict(x_values)
            path = config.output_dir / f"frozen_{name}_{split}.parquet"
            _freeze_predictions(path, ids, p0, p1, uplift)
            ledger.append_frozen_batch(
                batch_id=f"criteo-v2.1:{name}:{split}:seed-{config.seed}",
                dataset_name="Criteo Uplift Modeling Dataset",
                dataset_version="unbiased-v2.1",
                split=split,
                model_name=name,
                row_count=len(ids),
                predictions_path=str(path),
                predictions_sha256=_sha256(path),
                config=asdict(config),
                outcome_columns_hidden=("conversion", "visit"),
            )
            frozen[name][split] = path
    del x_test, test_features

    # Test outcomes are loaded only after every model's test predictions are frozen.
    test = _load_split(parquet, "test", (), config.outcome)
    y_test = test[config.outcome].to_numpy().astype(int)
    t_test = test["treatment"].to_numpy().astype(int)
    y_dev = development[config.outcome].to_numpy().astype(int)
    t_dev = development["treatment"].to_numpy().astype(int)
    propensity = float(np.mean(t_train))
    results: list[dict[str, Any]] = []
    policies: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []
    for name in models:
        test_prediction = pl.read_parquet(frozen[name]["test"])
        dev_prediction = pl.read_parquet(frozen[name]["development"])
        score = test_prediction["uplift"].to_numpy()
        dev_score = dev_prediction["uplift"].to_numpy()
        ranking = uplift_ranking_metrics(y_test, t_test, score, propensity)
        calibration = uplift_calibration(y_test, t_test, score)
        ate_error = float(abs(np.mean(score) - ranking["observed_ate"]))
        calibration_mae = float(
            np.mean([abs(row["predicted_uplift"] - row["observed_uplift"]) for row in calibration])
        )
        model_policies = policy_table(y_test, t_test, score, config.policy_fractions, propensity)
        results.append(
            {
                "model": name,
                **ranking,
                "ate_error": ate_error,
                "uplift_calibration_mae": calibration_mae,
                "best_policy_value": max(float(row["policy_value"]) for row in model_policies),
            }
        )
        policies.extend({"model": name, **row} for row in model_policies)
        calibration_rows.extend({"model": name, **row} for row in calibration)
        ledger.append_frozen_batch_evaluation(
            f"criteo-v2.1:{name}:test:seed-{config.seed}", results[-1]
        )

        if name == "commercial_twin_dr":
            dev_calibration = uplift_calibration(y_dev, t_dev, dev_score)
            act_ranges = [
                (row["score_min"], row["score_max"])
                for row in dev_calibration
                if row["lower_90"] > 0 and row["predicted_uplift"] > 0
            ]
            gated = np.zeros(len(score), dtype=bool)
            for lower, upper in act_ranges:
                gated |= (score >= lower) & (score <= upper)
            ungated = score > 0
            for label, targeted in (("ungated_positive", ungated), ("gated_act", gated)):
                custom_score = np.where(targeted, 1.0, -1.0)
                row = policy_table(
                    y_test,
                    t_test,
                    custom_score,
                    (float(np.mean(targeted)),),
                    propensity,
                )[0]
                policies.append(
                    {
                        "model": name,
                        "policy": label,
                        "acted_fraction": float(np.mean(targeted)),
                        "development_act_bins": len(act_ranges),
                        **row,
                    }
                )

    sample_curve: list[dict[str, Any]] = []
    for fraction in config.sample_fractions:
        row_ids = train["row_id"].to_numpy()
        mask = ((row_ids * 2_654_435_761 + config.seed) % 1_000_000) < int(fraction * 1_000_000)
        sample_x = train.filter(pl.Series(mask)).select(adapter.feature_columns).to_numpy()
        sample_t = t_train[mask]
        sample_y = y_train[mask]
        sample_control = _classifier(config.seed + 100, max(50, config.n_estimators // 2)).fit(
            sample_x[sample_t == 0], sample_y[sample_t == 0]
        )
        sample_treated = _classifier(config.seed + 101, max(50, config.n_estimators // 2)).fit(
            sample_x[sample_t == 1], sample_y[sample_t == 1]
        )
        sample_model = TLearnerModel(sample_control, sample_treated)
        _, _, score = sample_model.predict(x_development)
        ranking = uplift_ranking_metrics(y_dev, t_dev, score, propensity)
        calibration = uplift_calibration(y_dev, t_dev, score)
        curve_policy = policy_table(y_dev, t_dev, score, config.policy_fractions, propensity)
        sample_curve.append(
            {
                "fraction": fraction,
                "rows": int(np.sum(mask)),
                **ranking,
                "calibration_mae": float(
                    np.mean(
                        [
                            abs(row["predicted_uplift"] - row["observed_uplift"])
                            for row in calibration
                        ]
                    )
                ),
                "best_policy_value": max(float(row["policy_value"]) for row in curve_policy),
                "best_policy_regret": min(
                    float(row["regret_vs_best_available"]) for row in curve_policy
                ),
            }
        )

    result_frame = pl.DataFrame(results).sort("qini", descending=True)
    result_frame.write_parquet(config.output_dir / "model_results.parquet")
    pl.DataFrame(policies).write_parquet(config.output_dir / "policy_results.parquet")
    pl.DataFrame(calibration_rows).write_parquet(config.output_dir / "uplift_calibration.parquet")
    pl.DataFrame(sample_curve).write_parquet(config.output_dir / "sample_size_curve.parquet")
    profile_path = config.output_dir / "data_profile.json"
    profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    summary = {
        "label": "RESEARCH BENCHMARK — REAL RANDOMIZED EVIDENCE",
        "validated_layer": "ACTION_TO_CUSTOMER_RESPONSE",
        "not_validated": ["WORLD_STATE", "PRICING", "PROFIT", "INDIVIDUAL_COUNTERFACTUALS"],
        "config": {key: str(value) for key, value in asdict(config).items()},
        "data": profile,
        "splits": {
            "train": train.height,
            "development": development.height,
            "test": test.height,
        },
        "models": result_frame.to_dicts(),
        "sample_size_curve": sample_curve,
        "runtime_seconds": time.perf_counter() - started,
        "freeze_invariant": "all test scores frozen and ledgered before test outcomes loaded",
        "individual_truth_warning": (
            "individual counterfactuals are unobserved; evaluation is cohort/policy-level"
        ),
        "optional_challengers": {"econml": "NOT_INSTALLED", "dowhy": "NOT_INSTALLED"},
    }
    (config.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    registry = ModelPerformanceRegistry(config.output_dir / "model_registry.duckdb")
    for row in results:
        registry.append_behavior_model_result(
            record_id=f"criteo-v2.1:{row['model']}:seed-{config.seed}",
            decision_type="binary_ad_targeting",
            data_regime="REAL_RANDOMIZED",
            model=str(row["model"]),
            factual_error={},
            causal_error={
                "ate_error": float(row["ate_error"]),
                "auuc": float(row["auuc"]),
                "qini": float(row["qini"]),
            },
            calibration={"uplift_mae": float(row["uplift_calibration_mae"])},
            economic_regret=None,
            metadata={"outcome": config.outcome, "pricing_or_profit": False},
        )
    registry.close()
    ledger.close()
    return config.output_dir
