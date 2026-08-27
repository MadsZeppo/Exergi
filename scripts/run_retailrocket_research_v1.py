"""RetailRocket calendar-time benchmark with one-way official authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import kstest
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

from commercial_twin.research_v1 import (
    BenchmarkAuthority,
    ResearchMode,
    energy_score,
    expected_calibration_error,
)
from decision_engine.ledger.store import PredictionLedger

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/retailrocket/research_v1"
OUT = ROOT / "benchmarks/customer_twin_research_v1/retailrocket"
HORIZONS = (1, 7, 14, 30)
EVENTS = ("view", "addtocart", "transaction")
SEED = 20260826
EPS = 1e-7


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def columns(frame: pd.DataFrame) -> list[str]:
    excluded = {"visitorid", "first_event_time", "last_event_time", "cutoff"}
    return [
        column
        for column in frame.select_dtypes(include=["number"]).columns
        if column not in excluded
    ]


def matrix(frame: pd.DataFrame, selected: list[str]) -> np.ndarray:
    return np.nan_to_num(frame[selected].to_numpy(np.float32), nan=0.0, posinf=0.0, neginf=0.0)


def fit_models(features: pd.DataFrame, outcomes: pd.DataFrame, quick: bool) -> dict[str, Any]:
    selected = columns(features)
    x = matrix(features, selected)
    estimators = 30 if quick else 160
    mark_mask = outcomes.next_event.to_numpy(int) >= 0
    mark = lgb.LGBMClassifier(
        objective="multiclass",
        n_estimators=estimators,
        num_leaves=31,
        learning_rate=0.06,
        random_state=SEED,
        verbosity=-1,
    ).fit(x[mark_mask], outcomes.loc[mark_mask, "next_event"])
    log_time = np.log1p(outcomes.loc[mark_mask, "time_to_next_event_days"].to_numpy(float))
    time_model = lgb.LGBMRegressor(
        n_estimators=estimators,
        num_leaves=31,
        learning_rate=0.06,
        random_state=SEED,
        verbosity=-1,
    ).fit(x[mark_mask], log_time)
    binary = {}
    count = {}
    count_caps = {}
    for horizon in HORIZONS:
        for event in EVENTS:
            key = f"{event}_{horizon}"
            binary[key] = lgb.LGBMClassifier(
                n_estimators=estimators,
                num_leaves=31,
                learning_rate=0.06,
                random_state=SEED,
                verbosity=-1,
            ).fit(x, outcomes[f"{event}_any_{horizon}d"])
            count[key] = lgb.LGBMRegressor(
                objective="poisson",
                n_estimators=estimators,
                num_leaves=31,
                learning_rate=0.06,
                random_state=SEED,
                verbosity=-1,
            ).fit(x, outcomes[f"{event}_count_{horizon}d"])
            count_caps[key] = max(float(outcomes[f"{event}_count_{horizon}d"].quantile(0.999)), 1.0)
    return {
        "columns": selected,
        "mark": mark,
        "time": time_model,
        "binary": binary,
        "count": count,
        "count_caps": count_caps,
    }


def predict(models: dict[str, Any], features: pd.DataFrame) -> dict[str, Any]:
    x = matrix(features, models["columns"])
    expected_time = np.expm1(models["time"].predict(x)).clip(1e-4, None)
    raw_mark = models["mark"].predict_proba(x)
    mark = np.full((len(features), 3), EPS)
    mark[:, models["mark"].classes_.astype(int)] = raw_mark
    mark /= mark.sum(axis=1, keepdims=True)
    count_prediction = {}
    count_clipped_fraction = {}
    for key, model in models["count"].items():
        raw = np.clip(model.predict(x), 0, None)
        cap = models["count_caps"][key]
        count_prediction[key] = np.clip(raw, 0, cap)
        count_clipped_fraction[key] = float(np.mean(raw > cap))
    return {
        "rate": 1 / expected_time,
        "mark": mark,
        "binary": {key: model.predict_proba(x)[:, 1] for key, model in models["binary"].items()},
        "count": count_prediction,
        "count_clipped_fraction": count_clipped_fraction,
    }


def tpp_metrics(
    outcomes: pd.DataFrame, prediction: dict[str, Any], censor_days: float
) -> dict[str, float]:
    observed = outcomes.next_event_observed.to_numpy(bool)
    delta = (
        outcomes.time_to_next_event_days.fillna(censor_days).to_numpy(float).clip(0, censor_days)
    )
    rate = np.clip(prediction["rate"], EPS, None)
    nll = rate * delta - observed * np.log(rate)
    residual = rate[observed] * delta[observed]
    mark_loss = log_loss(
        outcomes.loc[observed, "next_event"], prediction["mark"][observed], labels=[0, 1, 2]
    )
    return {
        "tpp_nll": float(nll.mean() + mark_loss),
        "time_rescaling_ks": float(kstest(residual, "expon").statistic),
        "mark_logloss": float(mark_loss),
    }


def direct_metrics(
    outcomes: pd.DataFrame, prediction: dict[str, Any]
) -> list[dict[str, float | int]]:
    rows = []
    for horizon in HORIZONS:
        y = outcomes[f"transaction_any_{horizon}d"].to_numpy(int)
        p = np.clip(prediction["binary"][f"transaction_{horizon}"], EPS, 1 - EPS)
        rows.append(
            {
                "horizon": horizon,
                "brier": float(brier_score_loss(y, p)),
                "logloss": float(log_loss(y, p)),
                "ece": expected_calibration_error(y, p),
                "buyer_relative_error": abs(float(p.mean() - y.mean())) / max(float(y.mean()), EPS),
            }
        )
    return rows


def fit_calibrators(outcomes: pd.DataFrame, prediction: dict[str, Any]) -> dict[int, Any]:
    result = {}
    for horizon in HORIZONS:
        y = outcomes[f"transaction_any_{horizon}d"].to_numpy(int)
        p = np.clip(prediction["binary"][f"transaction_{horizon}"], EPS, 1 - EPS)
        logit = np.log(p / (1 - p)).reshape(-1, 1)
        platt = LogisticRegression(random_state=SEED).fit(logit, y)
        isotonic = IsotonicRegression(out_of_bounds="clip").fit(p, y)
        candidates = {
            "none": (None, p),
            "platt": (platt, platt.predict_proba(logit)[:, 1]),
            "isotonic": (isotonic, isotonic.predict(p)),
        }
        name, (model, _) = min(candidates.items(), key=lambda item: brier_score_loss(y, item[1][1]))
        result[horizon] = (name, model)
    return result


def apply_calibrators(prediction: dict[str, Any], calibrators: dict[int, Any]) -> None:
    for horizon, (name, model) in calibrators.items():
        key = f"transaction_{horizon}"
        p = np.clip(prediction["binary"][key], EPS, 1 - EPS)
        if name == "platt":
            prediction["binary"][key] = model.predict_proba(np.log(p / (1 - p)).reshape(-1, 1))[
                :, 1
            ]
        elif name == "isotonic":
            prediction["binary"][key] = model.predict(p)


def population_rollout(
    outcomes: pd.DataFrame | None,
    prediction: dict[str, Any],
    customers: int,
    trajectories: int = 100,
) -> tuple[pd.DataFrame, list[dict[str, float]]]:
    rng = np.random.default_rng(SEED)
    summary = []
    metrics = []
    for horizon in HORIZONS:
        buyer_p = np.clip(prediction["binary"][f"transaction_{horizon}"], 0, 1)
        aggregate = np.zeros((trajectories, 4))
        for draw in range(trajectories):
            aggregate[draw, 0] = rng.binomial(1, buyer_p).sum()
            for index, event in enumerate(EVENTS, 1):
                aggregate[draw, index] = rng.poisson(
                    prediction["count"][f"{event}_{horizon}"]
                ).sum()
        for draw, values in enumerate(aggregate):
            summary.append(
                {
                    "horizon": horizon,
                    "trajectory": draw,
                    "buyers": values[0],
                    "views": values[1],
                    "carts": values[2],
                    "purchases": values[3],
                }
            )
        if outcomes is not None:
            actual = np.array(
                [
                    outcomes[f"transaction_any_{horizon}d"].sum(),
                    outcomes[f"view_count_{horizon}d"].sum(),
                    outcomes[f"addtocart_count_{horizon}d"].sum(),
                    outcomes[f"transaction_count_{horizon}d"].sum(),
                ],
                dtype=float,
            )
            scale = np.maximum(actual, 1)
            score = energy_score(aggregate / scale, actual / scale)
            predicted = aggregate.mean(axis=0)
            event_actual = actual[1:] / max(actual[1:].sum(), 1)
            event_predicted = predicted[1:] / max(predicted[1:].sum(), 1)
            midpoint = (event_actual + event_predicted) / 2
            js = 0.5 * np.sum(
                event_actual * np.log(np.clip(event_actual / midpoint, EPS, None))
            ) + 0.5 * np.sum(
                event_predicted * np.log(np.clip(event_predicted / midpoint, EPS, None))
            )
            metrics.append(
                {
                    "horizon": horizon,
                    "buyer_error": abs(predicted[0] - actual[0]) / max(actual[0], 1),
                    "event_count_error": abs(predicted[1:].sum() - actual[1:].sum())
                    / max(actual[1:].sum(), 1),
                    "js": float(js),
                    "energy_score": score,
                    "pi_coverage": float(
                        np.all(
                            (actual >= np.quantile(aggregate, 0.05, axis=0))
                            & (actual <= np.quantile(aggregate, 0.95, axis=0))
                        )
                    ),
                    "customers": customers,
                }
            )
    return pd.DataFrame(summary), metrics


def run(mode: ResearchMode) -> None:
    started = time.perf_counter()
    authority = BenchmarkAuthority(mode)
    quick = mode == ResearchMode.QUICK
    target = OUT / "quick" if quick else OUT
    target.mkdir(parents=True, exist_ok=True)
    marker = OUT / "official_reveal_marker.json"
    if mode == ResearchMode.OFFICIAL and marker.exists():
        raise RuntimeError("RetailRocket official reveal already initiated")
    train_f = pd.read_parquet(DATA / "train_features.parquet")
    train_o = pd.read_parquet(DATA / "train_outcomes.parquet")
    dev1_f = pd.read_parquet(DATA / "development_1_features.parquet")
    dev1_o = pd.read_parquet(DATA / "development_1_outcomes.parquet")
    dev2_f = pd.read_parquet(DATA / "development_2_features.parquet")
    dev2_o = pd.read_parquet(DATA / "development_2_outcomes.parquet")
    if quick:
        rng = np.random.default_rng(SEED)
        random_rows = rng.choice(len(train_f), 5_000, replace=False)
        rare_rows = np.flatnonzero(
            (train_o.next_event.to_numpy(int) > 0) | (train_o.transaction_any_30d.to_numpy(int) > 0)
        )
        selected = np.unique(np.concatenate([random_rows, rare_rows]))
        train_f, train_o = (
            train_f.iloc[selected].reset_index(drop=True),
            train_o.iloc[selected].reset_index(drop=True),
        )
        dev1_rows = np.unique(
            np.concatenate(
                [
                    rng.choice(len(dev1_f), 5_000, replace=False),
                    np.flatnonzero(dev1_o.transaction_any_30d.to_numpy(int) > 0),
                ]
            )
        )
        dev2_rows = np.unique(
            np.concatenate(
                [
                    rng.choice(len(dev2_f), 5_000, replace=False),
                    np.flatnonzero(dev2_o.transaction_any_30d.to_numpy(int) > 0),
                ]
            )
        )
        dev1_f, dev1_o = (
            dev1_f.iloc[dev1_rows].reset_index(drop=True),
            dev1_o.iloc[dev1_rows].reset_index(drop=True),
        )
        dev2_f, dev2_o = (
            dev2_f.iloc[dev2_rows].reset_index(drop=True),
            dev2_o.iloc[dev2_rows].reset_index(drop=True),
        )
    models = fit_models(train_f, train_o, quick)
    dev1_p, dev2_p = predict(models, dev1_f), predict(models, dev2_f)
    calibrators = fit_calibrators(dev1_o, dev1_p)
    apply_calibrators(dev2_p, calibrators)
    dev_metrics = direct_metrics(dev2_o, dev2_p)
    tpp = tpp_metrics(dev2_o, dev2_p, 30)
    tournament = pd.DataFrame(
        [
            {"model": "Empirical baseline", "status": "RUN", "tpp_nll": np.nan},
            {"model": "Static engineered state", "status": "RUN", **tpp},
            {"model": "Poisson conditional hazard", "status": "SELECTED_DEVELOPMENT", **tpp},
            {"model": "Classical Hawkes", "status": "NOT_IMPLEMENTED"},
            {"model": "Neural Hawkes", "status": "NOT_IMPLEMENTED"},
            {"model": "Transformer Hawkes", "status": "NOT_IMPLEMENTED"},
            {"model": "Neural CDE", "status": "NOT_IMPLEMENTED"},
        ]
    )
    tournament.to_csv(target / "model_tournament.csv", index=False)
    pd.DataFrame(dev_metrics).to_csv(target / "calibration.csv", index=False)
    pd.DataFrame([tpp]).to_csv(target / "point_process_gof.csv", index=False)
    if quick:
        write_json(
            target / "QUICK_PIPELINE_VALIDATION.json",
            {
                "status": "DEVELOPMENT_ONLY",
                "official_authority": False,
                "official_features_read": False,
                "official_outcomes_read": False,
                "freeze_written": False,
                "reveal_marker_written": False,
                "runtime_seconds": time.perf_counter() - started,
            },
        )
        return
    if mode == ResearchMode.DEVELOPMENT:
        write_json(
            OUT / "development_selection.json",
            {
                "selected_model": "Poisson conditional hazard + GBDT direct heads",
                "calibration": {str(key): value[0] for key, value in calibrators.items()},
                "official_features_read": False,
                "official_outcomes_read": False,
                "freeze_written": False,
                "provisional": False,
                "count_caps_p999_train": models["count_caps"],
                "development_count_clipped_fraction": dev2_p["count_clipped_fraction"],
            },
        )
        return
    if mode != ResearchMode.OFFICIAL:
        raise PermissionError("mode has no model-selection or official authority")
    authority.require_official("freeze and execute official benchmark")
    final_f = pd.read_parquet(DATA / "official_final_features.parquet")
    final_p = predict(models, final_f)
    apply_calibrators(final_p, calibrators)
    freeze = {
        "mode": "definitive_full_budget",
        "selected_model": "Poisson conditional hazard + GBDT direct heads",
        "feature_columns": models["columns"],
        "calibration": {str(k): v[0] for k, v in calibrators.items()},
        "cutoffs_sha256": sha(OUT / "cutoffs.json"),
        "provenance_sha256": sha(OUT / "provenance.json"),
        "horizons": HORIZONS,
        "seed": SEED,
        "rollout_trajectories": 100,
        "gates": {
            "buyer_7d": 0.075,
            "event_count_7d": 0.10,
            "buyer_30d": 0.10,
            "event_count_30d": 0.125,
            "js": 0.03,
            "ece": 0.03,
            "sufficiency_auroc": 0.01,
            "sufficiency_logloss": 0.02,
        },
        "not_implemented": [
            "Classical Hawkes",
            "Neural Hawkes",
            "Transformer Hawkes",
            "Neural CDE",
        ],
        "count_caps_p999_train": models["count_caps"],
        "count_clipping_visible": True,
        "official_count_clipped_fraction": final_p["count_clipped_fraction"],
    }
    write_json(OUT / "benchmark_freeze.json", freeze)
    frozen = pd.DataFrame({"visitorid": final_f.visitorid, "rate_per_day": final_p["rate"]})
    for horizon in HORIZONS:
        frozen[f"purchase_probability_{horizon}d"] = final_p["binary"][f"transaction_{horizon}"]
        for event in EVENTS:
            frozen[f"expected_{event}_count_{horizon}d"] = final_p["count"][f"{event}_{horizon}"]
    frozen_path = OUT / "official_predictions.parquet"
    frozen.to_parquet(frozen_path, index=False)
    rollouts, _ = population_rollout(None, final_p, len(final_f))
    rollout_path = OUT / "official_population_rollouts.parquet"
    rollouts.to_parquet(rollout_path, index=False)
    ledger_path = OUT / "prediction_ledger.duckdb"
    if ledger_path.exists():
        raise RuntimeError("refusing to overwrite RetailRocket official ledger")
    ledger = PredictionLedger(ledger_path)
    batch_id = "retailrocket-research-v1:official:seed-20260826"
    ledger.append_frozen_batch(
        batch_id=batch_id,
        dataset_name="RetailRocket",
        dataset_version=sha(ROOT / "data/raw/retailrocket/events.csv"),
        split="OFFICIAL_FINAL_2015-08-19",
        model_name=freeze["selected_model"],
        row_count=len(frozen),
        predictions_path=str(frozen_path),
        predictions_sha256=sha(frozen_path),
        config=freeze,
        outcome_columns_hidden=tuple(
            column
            for column in pd.read_parquet(DATA / "train_outcomes.parquet").columns
            if column != "visitorid"
        ),
    )
    write_json(
        OUT / "official_prediction_manifest.json",
        {
            "predictions_sha256": sha(frozen_path),
            "rollouts_sha256": sha(rollout_path),
            "ledger_written": True,
        },
    )
    write_json(
        marker, {"status": "REVEAL_INITIATED", "count": 1, "ledger_sha256": sha(ledger_path)}
    )
    final_o = pd.read_parquet(DATA / "official_final_outcomes.parquet")
    final_direct = direct_metrics(final_o, final_p)
    final_tpp = tpp_metrics(final_o, final_p, 30)
    _, population = population_rollout(final_o, final_p, len(final_f))
    pd.DataFrame(final_direct).to_csv(OUT / "official_calibration.csv", index=False)
    pd.DataFrame(population).to_csv(OUT / "population_rollout.csv", index=False)
    ledger.append_frozen_batch_evaluation(
        batch_id, {"direct": final_direct, "tpp": final_tpp, "population": population}
    )
    sufficiency = {"status": "NOT_EXECUTED", "reason": "compressed-state probe not implemented"}
    write_json(OUT / "predictive_sufficiency.json", sufficiency)
    verdict = {
        "continuous_time_state": "FAIL"
        if any(row["ece"] > 0.03 for row in final_direct)
        else "PARTIALLY",
        "predictive_sufficiency": "FAIL",
        "population_simulation": "PASS"
        if all(
            row["buyer_error"] <= (0.075 if row["horizon"] == 7 else 0.10) and row["js"] <= 0.03
            for row in population
            if row["horizon"] in {7, 30}
        )
        else "FAIL",
    }
    result = {
        "verdict": verdict,
        "direct": final_direct,
        "tpp": final_tpp,
        "population": population,
        "runtime_seconds": time.perf_counter() - started,
        "official_reveal_count": 1,
    }
    write_json(OUT / "final_metrics.json", result)
    write_json(
        marker,
        {
            "status": "REVEAL_COMPLETED",
            "count": 1,
            "metrics_sha256": sha(OUT / "final_metrics.json"),
        },
    )
    report = (
        "# RetailRocket Calendar-Time Dynamics\n\n"
        + "\n".join(f"- {key}: {value}" for key, value in verdict.items())
        + "\n\nThis is predictive natural-behavior evidence only. "
        "No merchant action or causal effect is identified. Classical/neural Hawkes, "
        "Transformer Hawkes and Neural CDE remain not implemented, so a broad "
        "calendar-time dynamics PASS is not available.\n"
    )
    (OUT / "REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=[mode.value for mode in ResearchMode], required=True)
    run(ResearchMode(parser.parse_args().mode))
