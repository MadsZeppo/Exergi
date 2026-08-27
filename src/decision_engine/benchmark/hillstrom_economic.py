from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import polars as pl
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from decision_engine.benchmark.criteo_uplift import (
    _score_order,
    uplift_bin_assignments,
    uplift_calibration,
    uplift_ranking_metrics,
)
from decision_engine.benchmark.hillstrom import stratified_rct_split
from decision_engine.datasets.hillstrom import CONTROL, MENS, HillstromDataset
from decision_engine.decision.model_selection import (
    DevelopmentCandidate,
    DevelopmentSelectionConfig,
    GateBenchmark,
    promote_customer_facing_gate,
    select_development_model,
)
from decision_engine.ledger import PredictionLedger
from decision_engine.registry import ModelPerformanceRegistry


@dataclass(frozen=True)
class HillstromEconomicConfig:
    path: Path = Path("data/raw/hillstrom/hillstrom.csv")
    output_dir: Path = Path("artifacts/benchmarks/hillstrom/economic-capacity-seed-42")
    seed: int = 42
    contact_cost: float = 0.50
    capacity: float = 0.20
    policy_fractions: tuple[float, ...] = (0.05, 0.10, 0.20)
    calibration_tolerance: float = 0.25
    n_estimators: int = 160


class EconomicUpliftModel(Protocol):
    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...


class _StaticModel:
    def __init__(self, p0: float, uplift: float) -> None:
        self.p0, self.uplift = p0, uplift

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p0 = np.full(len(x), self.p0)
        uplift = np.full(len(x), self.uplift)
        return p0, p0 + uplift, uplift


class _OutcomeRanking:
    def __init__(self, model: RandomForestRegressor) -> None:
        self.model = model

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        value = np.asarray(self.model.predict(x), dtype=float)
        return value, value, value


class _SLearner:
    def __init__(self, model: RandomForestRegressor) -> None:
        self.model = model

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p0 = np.asarray(self.model.predict(np.column_stack([x, np.zeros(len(x))])), dtype=float)
        p1 = np.asarray(self.model.predict(np.column_stack([x, np.ones(len(x))])), dtype=float)
        return p0, p1, p1 - p0


class _TLearner:
    def __init__(self, control: RandomForestRegressor, treated: RandomForestRegressor) -> None:
        self.control, self.treated = control, treated

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p0 = np.asarray(self.control.predict(x), dtype=float)
        p1 = np.asarray(self.treated.predict(x), dtype=float)
        return p0, p1, p1 - p0


class _EffectLearner:
    def __init__(
        self,
        outcome: _TLearner,
        effect: RandomForestRegressor,
    ) -> None:
        self.outcome, self.effect = outcome, effect

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p0, p1, _ = self.outcome.predict(x)
        uplift = np.asarray(self.effect.predict(x), dtype=float)
        center = (p0 + p1) / 2
        return center - uplift / 2, center + uplift / 2, uplift


def _forest(seed: int, estimators: int) -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=estimators,
        min_samples_leaf=40,
        max_features=0.8,
        n_jobs=-1,
        random_state=seed,
    )


def _prepare_features(frame: pl.DataFrame, train: np.ndarray, features: list[str]) -> np.ndarray:
    categorical = [name for name in features if frame.schema[name] == pl.String]
    numeric = [name for name in features if name not in categorical]
    transformer = ColumnTransformer(
        [
            ("numeric", StandardScaler(), numeric),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                categorical,
            ),
        ]
    )
    pandas = frame.select(features).to_pandas()
    transformer.fit(pandas.iloc[train])
    return np.asarray(transformer.transform(pandas), dtype=float)


def _fit_models(
    x: np.ndarray,
    treatment: np.ndarray,
    spend: np.ndarray,
    train: np.ndarray,
    config: HillstromEconomicConfig,
) -> dict[str, EconomicUpliftModel]:
    t = (treatment == MENS).astype(int)
    p0 = float(np.mean(spend[train][t[train] == 0]))
    p1 = float(np.mean(spend[train][t[train] == 1]))
    models: dict[str, EconomicUpliftModel] = {"static_treat_all": _StaticModel(p0, p1 - p0)}
    outcome = _forest(config.seed, config.n_estimators).fit(x[train], spend[train])
    models["outcome_propensity"] = _OutcomeRanking(outcome)
    s_model = _forest(config.seed + 1, config.n_estimators).fit(
        np.column_stack([x[train], t[train]]), spend[train]
    )
    models["s_learner"] = _SLearner(s_model)
    control = _forest(config.seed + 2, config.n_estimators).fit(
        x[train][t[train] == 0], spend[train][t[train] == 0]
    )
    treated = _forest(config.seed + 3, config.n_estimators).fit(
        x[train][t[train] == 1], spend[train][t[train] == 1]
    )
    t_model = _TLearner(control, treated)
    models["t_learner"] = t_model
    p0_train, p1_train, _ = t_model.predict(x[train])
    d0 = p1_train[t[train] == 0] - spend[train][t[train] == 0]
    d1 = spend[train][t[train] == 1] - p0_train[t[train] == 1]
    effect_target = np.empty(len(train), dtype=float)
    effect_target[t[train] == 0] = d0
    effect_target[t[train] == 1] = d1
    x_effect = _forest(config.seed + 4, config.n_estimators).fit(x[train], effect_target)
    models["x_learner"] = _EffectLearner(t_model, x_effect)

    propensity = 0.5
    pseudo = np.empty(len(train), dtype=float)
    for fold in (0, 1):
        validation_local = np.arange(len(train)) % 2 == fold
        training_local = ~validation_local
        fold_indices = train[training_local]
        fold_control = _forest(config.seed + 10 + fold, config.n_estimators).fit(
            x[fold_indices][t[fold_indices] == 0],
            spend[fold_indices][t[fold_indices] == 0],
        )
        fold_treated = _forest(config.seed + 12 + fold, config.n_estimators).fit(
            x[fold_indices][t[fold_indices] == 1],
            spend[fold_indices][t[fold_indices] == 1],
        )
        validation_indices = train[validation_local]
        m0 = np.asarray(fold_control.predict(x[validation_indices]), dtype=float)
        m1 = np.asarray(fold_treated.predict(x[validation_indices]), dtype=float)
        tv = t[validation_indices]
        yv = spend[validation_indices]
        pseudo[validation_local] = (
            m1 - m0 + tv * (yv - m1) / propensity - (1 - tv) * (yv - m0) / (1 - propensity)
        )
    dr_effect = _forest(config.seed + 20, config.n_estimators).fit(x[train], pseudo)
    models["dr_learner"] = _EffectLearner(t_model, dr_effect)
    return models


def economic_policy_value(
    spend: np.ndarray,
    treatment: np.ndarray,
    targeted: np.ndarray,
    *,
    contact_cost: float,
    propensity: float = 0.5,
) -> dict[str, float]:
    observed_treatment = (treatment == MENS).astype(int)
    treated = spend * observed_treatment / propensity
    control = spend * (1 - observed_treatment) / (1 - propensity)
    gross = float(np.mean(np.where(targeted, treated, control)))
    cost = contact_cost * float(np.mean(targeted))
    influence = np.where(targeted, treated, control) - contact_cost * targeted
    return {
        "gross_outcome_value": gross,
        "treatment_cost": cost,
        "net_policy_value": gross - cost,
        "standard_error": float(np.std(influence, ddof=1) / np.sqrt(len(spend))),
        "treatment_rate": float(np.mean(targeted)),
    }


def _top(score: np.ndarray, fraction: float) -> np.ndarray:
    targeted = np.zeros(len(score), dtype=bool)
    order = _score_order(score, descending=True)
    targeted[order[: int(round(len(score) * fraction))]] = True
    return targeted


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _freeze(path: Path, ids: np.ndarray, prediction: tuple[np.ndarray, ...]) -> None:
    p0, p1, uplift = prediction
    pl.DataFrame({"row_id": ids, "control": p0, "treatment": p1, "uplift": uplift}).write_parquet(
        path
    )


def run_hillstrom_economic_benchmark(
    config: HillstromEconomicConfig | None = None,
) -> Path:
    config = config or HillstromEconomicConfig()
    started = time.perf_counter()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    for database_name in ("prediction_ledger.duckdb", "model_registry.duckdb"):
        database_path = config.output_dir / database_name
        if database_path.exists():
            database_path.unlink()
    full = HillstromDataset(config.path).load_rct()
    frame = full.filter(pl.col("treatment").is_in([CONTROL, MENS]))
    treatment = frame["treatment"].to_numpy()
    spend = frame["spend"].to_numpy().astype(float)
    train, development, test = stratified_rct_split(treatment, config.seed)
    features = HillstromDataset.feature_columns(frame)
    x = _prepare_features(frame, train, features)
    models = _fit_models(x, treatment, spend, train, config)
    ledger = PredictionLedger(config.output_dir / "prediction_ledger.duckdb")
    predictions: dict[str, dict[str, Path]] = {}
    for name, model in models.items():
        predictions[name] = {}
        for split, indices in (("development", development), ("test", test)):
            path = config.output_dir / f"frozen_{name}_{split}.parquet"
            _freeze(path, frame[indices]["row_id"].to_numpy(), model.predict(x[indices]))
            ledger.append_frozen_batch(
                batch_id=f"hillstrom-economic:{name}:{split}:seed-{config.seed}",
                dataset_name="Hillstrom",
                dataset_version="mine-that-data-2008",
                split=split,
                model_name=name,
                row_count=len(indices),
                predictions_path=str(path),
                predictions_sha256=_sha256(path),
                config=asdict(config),
                outcome_columns_hidden=("spend", "conversion", "visit"),
            )
            predictions[name][split] = path

    t_dev, y_dev = treatment[development], spend[development]
    candidates: list[DevelopmentCandidate] = []
    development_policy_rows: list[dict[str, Any]] = []
    scores_dev: dict[str, np.ndarray] = {}
    for name in models:
        score = pl.read_parquet(predictions[name]["development"])["uplift"].to_numpy()
        scores_dev[name] = score
        calibration = uplift_calibration(y_dev, (t_dev == MENS).astype(int), score)
        calibration_error = float(
            np.mean([abs(row["predicted_uplift"] - row["observed_uplift"]) for row in calibration])
        )
        model_rows: list[dict[str, float]] = []
        for fraction in config.policy_fractions:
            value = economic_policy_value(
                y_dev,
                t_dev,
                _top(score, fraction),
                contact_cost=config.contact_cost,
            )
            row = {"fraction": fraction, **value}
            model_rows.append(row)
            development_policy_rows.append({"model": name, **row})
        best = max(model_rows, key=lambda row: float(row["net_policy_value"]))
        best_value = float(best["net_policy_value"])
        best_fraction = float(best["fraction"])
        candidates.append(
            DevelopmentCandidate(
                model_name=name,
                policy_value=best_value,
                calibration_error=calibration_error,
                policy_name=f"TOP_{int(best_fraction * 100)}%",
            )
        )
    selection = select_development_model(
        tuple(candidates),
        DevelopmentSelectionConfig(
            decision_type="email_spend_capacity",
            calibration_tolerance=config.calibration_tolerance,
        ),
    )
    selected_fraction = (
        float(selection.selected_policy.removeprefix("TOP_").removesuffix("%")) / 100
    )
    selected_score_dev = scores_dev[selection.selected_model]
    dev_calibration = uplift_calibration(y_dev, (t_dev == MENS).astype(int), selected_score_dev)
    act_bins = {int(row["bin"]) for row in dev_calibration if row["lower_90"] > config.contact_cost}
    dev_bins = uplift_bin_assignments(selected_score_dev)
    dev_gated = np.isin(dev_bins, list(act_bins)) & _top(selected_score_dev, config.capacity)

    # The selected model and gate are frozen before final outcomes are evaluated below.
    t_test, y_test = treatment[test], spend[test]
    final_rows: list[dict[str, Any]] = []
    test_scores: dict[str, np.ndarray] = {}
    for name in models:
        score = pl.read_parquet(predictions[name]["test"])["uplift"].to_numpy()
        test_scores[name] = score
        for fraction in config.policy_fractions:
            value = economic_policy_value(
                y_test,
                t_test,
                _top(score, fraction),
                contact_cost=config.contact_cost,
            )
            final_rows.append({"model": name, "fraction": fraction, **value})
    selected_score_test = test_scores[selection.selected_model]
    test_bins = uplift_bin_assignments(selected_score_test)
    test_gated = np.isin(test_bins, list(act_bins)) & _top(selected_score_test, config.capacity)
    simple_dev = scores_dev["outcome_propensity"]
    simple_test = test_scores["outcome_propensity"]

    def gate_values(
        y: np.ndarray,
        t: np.ndarray,
        selected_score: np.ndarray,
        simple_score: np.ndarray,
        gated: np.ndarray,
    ) -> GateBenchmark:
        return GateBenchmark(
            gated_policy_value=economic_policy_value(y, t, gated, contact_cost=config.contact_cost)[
                "net_policy_value"
            ],
            ungated_policy_value=economic_policy_value(
                y,
                t,
                _top(selected_score, selected_fraction),
                contact_cost=config.contact_cost,
            )["net_policy_value"],
            simple_targeting_value=economic_policy_value(
                y,
                t,
                _top(simple_score, config.capacity),
                contact_cost=config.contact_cost,
            )["net_policy_value"],
            treat_all_value=economic_policy_value(
                y, t, np.ones(len(y), dtype=bool), contact_cost=config.contact_cost
            )["net_policy_value"],
            treat_none_value=economic_policy_value(
                y, t, np.zeros(len(y), dtype=bool), contact_cost=config.contact_cost
            )["net_policy_value"],
        )

    gate = promote_customer_facing_gate(
        "email_spend_capacity",
        gate_values(y_dev, t_dev, selected_score_dev, simple_dev, dev_gated),
        gate_values(y_test, t_test, selected_score_test, simple_test, test_gated),
    )
    selected_final = next(
        row
        for row in final_rows
        if row["model"] == selection.selected_model
        and np.isclose(row["fraction"], selected_fraction)
    )
    none = economic_policy_value(
        y_test, t_test, np.zeros(len(y_test), dtype=bool), contact_cost=config.contact_cost
    )
    all_policy = economic_policy_value(
        y_test, t_test, np.ones(len(y_test), dtype=bool), contact_cost=config.contact_cost
    )
    random_capacity_value = (
        config.capacity * all_policy["net_policy_value"]
        + (1 - config.capacity) * none["net_policy_value"]
    )
    simple_capacity = economic_policy_value(
        y_test,
        t_test,
        _top(simple_test, config.capacity),
        contact_cost=config.contact_cost,
    )
    feasible = [row for row in final_rows if float(row["fraction"]) <= config.capacity] + [
        {"model": "treat_none", "fraction": 0.0, **none}
    ]
    best_feasible = max(feasible, key=lambda row: row["net_policy_value"])
    selected_final["regret_vs_best_feasible"] = (
        best_feasible["net_policy_value"] - selected_final["net_policy_value"]
    )
    selected_final["random_capacity_value"] = random_capacity_value
    selected_final["value_over_random_capacity"] = (
        selected_final["net_policy_value"] - random_capacity_value
    )
    selected_calibration = uplift_calibration(
        y_test, (t_test == MENS).astype(int), selected_score_test
    )
    calibration_error = float(
        np.mean(
            [abs(row["predicted_uplift"] - row["observed_uplift"]) for row in selected_calibration]
        )
    )
    ranking = uplift_ranking_metrics(y_test, (t_test == MENS).astype(int), selected_score_test, 0.5)
    payload = {
        "label": "REAL RANDOMIZED COMMERCE BENCHMARK — ECONOMIC SCENARIO",
        "dataset_rows": frame.height,
        "split": {"train": len(train), "development": len(development), "test": len(test)},
        "economic_constraint": {
            "contact_cost": config.contact_cost,
            "capacity": config.capacity,
            "cost_source": "explicit benchmark scenario assumption, not a Hillstrom field",
            "outcome_value": "observed customer spend",
        },
        "selection": selection.model_dump(mode="json"),
        "selected_final": selected_final,
        "treat_all": all_policy,
        "treat_none": none,
        "simple_targeting": simple_capacity,
        "best_feasible": best_feasible,
        "selected_calibration_error": calibration_error,
        "selected_ranking": ranking,
        "customer_facing_gate": gate.model_dump(mode="json"),
        "selective_targeting_creates_economic_value": (
            selected_final["net_policy_value"]
            > max(
                random_capacity_value,
                none["net_policy_value"],
                simple_capacity["net_policy_value"],
            )
        ),
        "runtime_seconds": time.perf_counter() - started,
        "scientific_warning": (
            "cost is scenario-defined; individual counterfactual spend is unobserved"
        ),
    }
    (config.output_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    pl.DataFrame(development_policy_rows).write_parquet(
        config.output_dir / "development_policy_results.parquet"
    )
    pl.DataFrame(final_rows).write_parquet(config.output_dir / "final_policy_results.parquet")
    pl.DataFrame(selected_calibration).write_parquet(
        config.output_dir / "selected_model_calibration.parquet"
    )
    registry = ModelPerformanceRegistry(config.output_dir / "model_registry.duckdb")
    registry.set_decision_model_default(
        decision_type="email_spend_capacity",
        model=selection.selected_model,
        selection_artifact=str(config.output_dir / "summary.json"),
        customer_facing_do_this_enabled=gate.customer_facing_do_this_enabled,
    )
    registry.close()
    for name in models:
        ledger.append_frozen_batch_evaluation(
            f"hillstrom-economic:{name}:test:seed-{config.seed}",
            {"selected": name == selection.selected_model},
        )
    ledger.close()
    return config.output_dir
