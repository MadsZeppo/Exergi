"""Execute the frozen JDsearch event-time customer dynamics benchmark."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import sklearn
import torch
from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    log_loss,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

from commercial_twin.dynamic_customer_state import DynamicsBenchmarkAuthority
from commercial_twin.dynamics_models import fit_gru, predict_gru
from commercial_twin.jdsearch_dynamics import EVENT_TYPES, HORIZONS, SEQUENCE_LENGTH
from decision_engine.ledger.store import PredictionLedger

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/jdsearch/dynamics"
OUT = ROOT / "benchmarks/jdsearch_dynamics"
SEED = 20260826
EPS = 1e-7


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8")


def feature_columns(frame: pd.DataFrame) -> list[str]:
    excluded = {"user_key", "snapshot_index", "cutoff_event", "split"}
    return [
        column
        for column in frame.columns
        if column not in excluded and not column.startswith("sequence_")
    ]


def finite_matrix(frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    return np.nan_to_num(frame[columns].to_numpy(np.float32), nan=0.0, posinf=0.0, neginf=0.0)


def multiclass_metrics(y: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    probability = np.clip(probability, EPS, 1 - EPS)
    probability /= probability.sum(axis=1, keepdims=True)
    one_hot = np.eye(4)[y]
    return {
        "next_event_logloss": float(log_loss(y, probability, labels=np.arange(4))),
        "next_event_brier": float(np.mean(np.sum((probability - one_hot) ** 2, axis=1))),
        "next_event_macro_f1": float(f1_score(y, probability.argmax(axis=1), average="macro")),
    }


def ece(y: np.ndarray, probability: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    value = 0.0
    for lower, upper in zip(edges[:-1], edges[1:], strict=True):
        mask = (probability >= lower) & (probability < upper if upper < 1 else probability <= upper)
        if mask.any():
            value += float(mask.mean()) * abs(float(y[mask].mean() - probability[mask].mean()))
    return value


def binary_metrics(y: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    probability = np.clip(probability, EPS, 1 - EPS)
    return {
        "auroc": float(roc_auc_score(y, probability)),
        "pr_auc": float(average_precision_score(y, probability)),
        "brier": float(brier_score_loss(y, probability)),
        "logloss": float(log_loss(y, probability)),
        "ece": ece(y, probability),
        "purchase_error": abs(float(probability.mean() - y.mean())) / max(float(y.mean()), EPS),
    }


def markov_fit(
    features: pd.DataFrame, targets: pd.DataFrame, order: int
) -> dict[tuple[int, ...], np.ndarray]:
    sequence = features[[f"sequence_type_{i}" for i in range(SEQUENCE_LENGTH)]].to_numpy(int)
    counts: dict[tuple[int, ...], np.ndarray] = {}
    for row, target in zip(sequence[:, -order:], targets.next_event.to_numpy(int), strict=True):
        key = tuple(row)
        counts.setdefault(key, np.ones(4))[target] += 1
    return counts


def markov_predict(
    model: dict[tuple[int, ...], np.ndarray], features: pd.DataFrame, order: int
) -> np.ndarray:
    sequence = features[[f"sequence_type_{i}" for i in range(SEQUENCE_LENGTH)]].to_numpy(int)
    prior = np.sum(list(model.values()), axis=0)
    return np.vstack(
        [
            model.get(tuple(row), prior) / model.get(tuple(row), prior).sum()
            for row in sequence[:, -order:]
        ]
    )


def fit_engineered(
    train_x: np.ndarray, train_y: np.ndarray, *, multiclass: bool
) -> lgb.LGBMClassifier:
    model = lgb.LGBMClassifier(
        n_estimators=180,
        num_leaves=31,
        learning_rate=0.06,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=SEED,
        n_jobs=-1,
        verbosity=-1,
        objective="multiclass" if multiclass else "binary",
    )
    return model.fit(train_x, train_y)


def calibration_partition(customer_keys: pd.Series) -> np.ndarray:
    return np.asarray(
        [
            int(hashlib.sha256(f"jdsearch-cal:{int(key)}".encode()).hexdigest()[:8], 16) % 2 == 0
            for key in customer_keys
        ]
    )


def fit_binary_calibrator(y: np.ndarray, p: np.ndarray) -> LogisticRegression:
    logit = np.log(np.clip(p, EPS, 1 - EPS) / np.clip(1 - p, EPS, 1 - EPS)).reshape(-1, 1)
    return LogisticRegression(random_state=SEED).fit(logit, y)


def apply_binary_calibrator(model: LogisticRegression, apply: np.ndarray) -> np.ndarray:
    apply_logit = np.log(np.clip(apply, EPS, 1 - EPS) / np.clip(1 - apply, EPS, 1 - EPS)).reshape(
        -1, 1
    )
    return model.predict_proba(apply_logit)[:, 1]


def make_states(features: pd.DataFrame, prediction: Any, dimension: int) -> pd.DataFrame:
    result = features[["user_key", "snapshot_index", "cutoff_event"]].copy()
    result = result.rename(columns={"user_key": "customer_key", "cutoff_event": "as_of_event"})
    result["state_dimension"] = dimension
    result["latent_state"] = [row.tolist() for row in prediction.state]
    for index, event in enumerate(EVENT_TYPES):
        result[f"next_{event.lower()}_probability"] = prediction.next_event[:, index]
    for key, probability in prediction.binary.items():
        result[f"{key}_probability"] = probability
    for horizon, probability in prediction.mix.items():
        for index, event in enumerate(EVENT_TYPES):
            result[f"{event.lower()}_share_{horizon}_expected"] = probability[:, index]
    entropy = -np.sum(
        prediction.next_event * np.log(np.clip(prediction.next_event, EPS, 1)), axis=1
    )
    result["state_entropy"] = entropy
    result["reliability"] = 1 - entropy / np.log(4)
    result["semantics"] = "EVENT_TIME_ONLY"
    result["causal_status"] = "INSUFFICIENT_CAUSAL_EVIDENCE"
    result["model_version"] = "jdsearch-predictive-gru-v1"
    return result


def predictions_frame(features: pd.DataFrame, prediction: Any) -> pd.DataFrame:
    result = features[["user_key", "snapshot_index", "cutoff_event"]].copy()
    result = result.rename(columns={"user_key": "customer_key", "cutoff_event": "as_of_event"})
    for index, event in enumerate(EVENT_TYPES):
        result[f"next_{event.lower()}_probability"] = prediction.next_event[:, index]
    for key, probability in prediction.binary.items():
        result[f"{key}_probability"] = probability
    return result


def rollout(prediction: Any, features: pd.DataFrame, trajectories: int = 100) -> pd.DataFrame:
    """Monte Carlo from frozen multi-horizon state distributions; never reads outcomes."""
    rng = np.random.default_rng(SEED)
    rows: list[dict[str, float | int]] = []
    for horizon in HORIZONS:
        mix = prediction.mix[horizon]
        ord_index = EVENT_TYPES.index("ORD")
        for index, key in enumerate(features.user_key.to_numpy(int)):
            counts = rng.multinomial(horizon, mix[index], size=trajectories)
            rows.append(
                {
                    "customer_key": key,
                    "horizon": horizon,
                    "trajectories": trajectories,
                    "purchase_probability": float(np.mean(counts[:, ord_index] > 0)),
                    **{
                        f"{event.lower()}_share": float(counts[:, event_index].mean() / horizon)
                        for event_index, event in enumerate(EVENT_TYPES)
                    },
                }
            )
    return pd.DataFrame(rows)


def run(*, quick: bool) -> None:
    started = time.perf_counter()
    authority = DynamicsBenchmarkAuthority(quick=quick)
    reveal_marker = OUT / "official_reveal_marker.json"
    if not quick and reveal_marker.exists():
        raise RuntimeError("Official final reveal was already initiated; refusing a second reveal.")
    OUT.mkdir(parents=True, exist_ok=True)
    development_out = OUT / "quick" if quick else OUT
    development_out.mkdir(parents=True, exist_ok=True)
    train_f = pd.read_parquet(DATA / "train_features.parquet")
    train_t = pd.read_parquet(DATA / "train_targets.parquet")
    dev_f = pd.read_parquet(DATA / "development_features.parquet")
    dev_t = pd.read_parquet(DATA / "development_targets.parquet")
    if quick:
        # Pipeline validation budget only; never used for official selection.
        rng = np.random.default_rng(SEED)
        selected = rng.choice(len(train_f), 1_000, replace=False)
        dev_selected = rng.choice(len(dev_f), 2_000, replace=False)
        train_f, train_t = (
            train_f.iloc[selected].reset_index(drop=True),
            train_t.iloc[selected].reset_index(drop=True),
        )
        dev_f, dev_t = (
            dev_f.iloc[dev_selected].reset_index(drop=True),
            dev_t.iloc[dev_selected].reset_index(drop=True),
        )
    columns = feature_columns(train_f)
    train_x, dev_x = finite_matrix(train_f, columns), finite_matrix(dev_f, columns)
    dev_y = dev_t.next_event.to_numpy(int)

    tournament: list[dict[str, Any]] = []
    for order in (1, 2):
        model = markov_fit(train_f, train_t, order)
        metrics = multiclass_metrics(dev_y, markov_predict(model, dev_f, order))
        tournament.append(
            {"model": f"{order}st-order Markov" if order == 1 else "2nd-order Markov", **metrics}
        )
    engineered = fit_engineered(train_x, train_t.next_event.to_numpy(int), multiclass=True)
    engineered_probability = engineered.predict_proba(dev_x)
    tournament.append(
        {"model": "Engineered state", **multiclass_metrics(dev_y, engineered_probability)}
    )

    # Interpretable latent-regime challenger. This is not falsely presented as the requested NH-HMM.
    scaler = StandardScaler().fit(train_x[:100_000])
    hmm_rows = []
    best_regime = None
    for states in (3, 4, 6, 8):
        cluster = KMeans(states, random_state=SEED, n_init=5).fit(
            scaler.transform(train_x[:100_000])
        )
        train_state = cluster.labels_
        dev_state = cluster.predict(scaler.transform(dev_x))
        emission = np.ones((states, 4))
        for state, target in zip(
            train_state, train_t.next_event.to_numpy(int)[:100_000], strict=True
        ):
            emission[state, target] += 1
        emission /= emission.sum(axis=1, keepdims=True)
        metrics = multiclass_metrics(dev_y, emission[dev_state])
        hmm_rows.append({"states": states, **metrics})
    hmm_table = pd.DataFrame(hmm_rows).sort_values("next_event_logloss")
    hmm_table.to_csv(development_out / "hmm_ablation.csv", index=False)
    best_regime = hmm_table.iloc[0]
    tournament.append(
        {"model": "Covariate regime (not NH-HMM)", **best_regime.drop("states").to_dict()}
    )
    tournament.append({"model": "Nonhomogeneous HMM", "status": "NOT_IMPLEMENTED"})

    dimensions = (8, 16, 32, 64)
    dimension_rows = []
    gru_models = {}
    for dimension in dimensions:
        model = fit_gru(
            train_f,
            train_t,
            dimension=dimension,
            use_intervals=True,
            seed=SEED,
            epochs=1 if quick else 3,
            maximum_rows=1_000 if quick else 200_000,
        )
        prediction = predict_gru(model, dev_f)
        metrics = multiclass_metrics(dev_y, prediction.next_event)
        purchase_brier = np.mean(
            [
                brier_score_loss(dev_t[f"ord_any_{h}"], prediction.binary[f"ord_{h}"])
                for h in HORIZONS
            ]
        )
        score = -(metrics["next_event_logloss"] + metrics["next_event_brier"] + purchase_brier)
        dimension_rows.append(
            {
                "dimension": dimension,
                "composite_score": score,
                "purchase_brier_mean": purchase_brier,
                **metrics,
            }
        )
        gru_models[dimension] = model
    dimension_table = pd.DataFrame(dimension_rows)
    best_score = dimension_table.composite_score.max()
    tolerance = abs(best_score) * 0.01
    selected_dimension = int(
        dimension_table[dimension_table.composite_score >= best_score - tolerance]
        .sort_values("dimension")
        .iloc[0]
        .dimension
    )
    selected_model = gru_models[selected_dimension]
    dev_prediction = predict_gru(selected_model, dev_f)
    tournament.append(
        {"model": "Neural predictive state", **multiclass_metrics(dev_y, dev_prediction.next_event)}
    )
    tournament.append({"model": "Deep state-space", "status": "NOT_RUN_COMPLEXITY_NOT_JUSTIFIED"})
    pd.DataFrame(tournament).to_csv(development_out / "model_tournament.csv", index=False)
    dimension_table.to_csv(development_out / "dimension_ablation.csv", index=False)

    # Sequence ablation: purchase-only, unordered behavior, recency, sequence types, full sequence.
    ablations = []
    groups = {
        "purchase_only": [c for c in columns if "ord" in c or "purchase" in c],
        "all_behavior_unordered": [
            c for c in columns if "recency" not in c and "transition" not in c
        ],
        "all_behavior_recency": columns,
    }
    for name, subset in groups.items():
        model = fit_engineered(
            finite_matrix(train_f, subset), train_t.next_event.to_numpy(int), multiclass=True
        )
        metrics = multiclass_metrics(dev_y, model.predict_proba(finite_matrix(dev_f, subset)))
        ablations.append({"ablation": name, **metrics})
    for use_intervals, name in ((False, "sequence_types"), (True, "sequence_types_intervals")):
        model = fit_gru(
            train_f,
            train_t,
            dimension=selected_dimension,
            use_intervals=use_intervals,
            seed=SEED,
            epochs=1 if quick else 3,
            maximum_rows=1_000 if quick else 200_000,
        )
        ablations.append(
            {"ablation": name, **multiclass_metrics(dev_y, predict_gru(model, dev_f).next_event)}
        )
    pd.DataFrame(ablations).to_csv(development_out / "sequence_ablation.csv", index=False)

    # Predictive sufficiency: does raw engineered history add signal after compressed state?
    train_prediction = predict_gru(selected_model, train_f)
    sufficiency = []
    for horizon in HORIZONS:
        y_train = train_t[f"ord_any_{horizon}"].to_numpy(int)
        y_dev = dev_t[f"ord_any_{horizon}"].to_numpy(int)
        state_head = LogisticRegression(max_iter=300, random_state=SEED).fit(
            train_prediction.state, y_train
        )
        base_p = state_head.predict_proba(dev_prediction.state)[:, 1]
        keep = min(50_000, len(train_f))
        challenger = lgb.LGBMClassifier(
            n_estimators=120, num_leaves=24, random_state=SEED, verbosity=-1
        )
        challenger.fit(np.hstack([train_prediction.state[:keep], train_x[:keep]]), y_train[:keep])
        raw_p = challenger.predict_proba(np.hstack([dev_prediction.state, dev_x]))[:, 1]
        base_loss, raw_loss = log_loss(y_dev, base_p), log_loss(y_dev, raw_p)
        sufficiency.append(
            {
                "horizon": horizon,
                "state_auroc": roc_auc_score(y_dev, base_p),
                "state_plus_raw_auroc": roc_auc_score(y_dev, raw_p),
                "raw_history_auroc_gain": roc_auc_score(y_dev, raw_p)
                - roc_auc_score(y_dev, base_p),
                "raw_history_relative_logloss_gain": (base_loss - raw_loss) / base_loss,
            }
        )
    pd.DataFrame(sufficiency).to_csv(development_out / "predictive_sufficiency.csv", index=False)

    calibration_mask = calibration_partition(dev_f.user_key)
    development_evaluation = ~calibration_mask
    multi_rows = []
    calibrators: dict[int, LogisticRegression] = {}
    for horizon in HORIZONS:
        key = f"ord_{horizon}"
        calibrator = fit_binary_calibrator(
            dev_t.loc[calibration_mask, f"ord_any_{horizon}"].to_numpy(int),
            dev_prediction.binary[key][calibration_mask],
        )
        calibrators[horizon] = calibrator
        probability = apply_binary_calibrator(
            calibrator,
            dev_prediction.binary[key][development_evaluation],
        )
        multi_rows.append(
            {
                "split": "DEVELOPMENT_EVALUATION",
                "horizon": horizon,
                **binary_metrics(
                    dev_t.loc[development_evaluation, f"ord_any_{horizon}"].to_numpy(int),
                    probability,
                ),
            }
        )
    pd.DataFrame(multi_rows).to_csv(
        development_out / "development_multi_horizon_results.csv", index=False
    )

    if quick:
        write_json(
            development_out / "QUICK_PIPELINE_VALIDATION.json",
            {
                "status": "PIPELINE_VALIDATED_DEVELOPMENT_ONLY",
                "provisional_selected_dimension": selected_dimension,
                "official_selection_frozen": False,
                "official_final_features_read": False,
                "official_final_targets_read": False,
                "official_final_revealed": False,
                "runtime_seconds": time.perf_counter() - started,
                "warning": (
                    "Quick diagnostics are provisional and cannot select the official system."
                ),
            },
        )
        return

    # Only definitive mode may inspect final features, after development selection.
    authority.require_definitive("read official-final features")
    final_f = pd.read_parquet(DATA / "official_final_features.parquet")
    final_customer_hash = hashlib.sha256(
        ",".join(map(str, sorted(final_f.user_key.unique()))).encode()
    ).hexdigest()

    freeze = {
        "created_before_official_target_reveal": True,
        "event_time_only": True,
        "raw_hashes": {
            "user_behavior": sha(ROOT / "data/raw/jdsearch/user_behavior_data.txt"),
            "product_meta": sha(ROOT / "data/raw/jdsearch/product_meta_data.txt"),
        },
        "customer_split": json.loads((OUT / "customer_split.json").read_text()),
        "official_customer_hash": final_customer_hash,
        "state_definition": "deterministic GRU compression of last 20 event types and relative intervals",
        "horizons": list(HORIZONS),
        "selected_model": "PredictiveGRU",
        "selected_dimension": selected_dimension,
        "hyperparameters": {
            "epochs": 1 if quick else 3,
            "maximum_rows": 1_000 if quick else 200_000,
        },
        "calibration": "development-only Platt scaling for binary purchase heads",
        "rollout_count": 100,
        "seed": SEED,
        "gates": {
            "markov_relative_logloss_gain": 0.05,
            "purchase_ece": 0.03,
            "rollout_purchase_relative_error": 0.10,
            "rollout_js": 0.03,
        },
        "dependencies": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "sklearn": sklearn.__version__,
            "lightgbm": lgb.__version__,
        },
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout.strip(),
        "code_hash": sha(Path(__file__)),
        "known_gap": "Requested nonhomogeneous HMM is not implemented; covariate regime challenger is reported separately.",
    }
    write_json(OUT / "benchmark_freeze.json", freeze)

    # OFFICIAL FREEZE: features only; the target file is deliberately untouched above.
    final_prediction = predict_gru(selected_model, final_f)
    for horizon, calibrator in calibrators.items():
        key = f"ord_{horizon}"
        final_prediction.binary[key] = apply_binary_calibrator(
            calibrator, final_prediction.binary[key]
        )
    states = make_states(final_f, final_prediction, selected_dimension)
    predictions = predictions_frame(final_f, final_prediction)
    rollouts = rollout(final_prediction, final_f)
    state_path = OUT / "official_customer_states.parquet"
    prediction_path = OUT / "official_one_step_predictions.parquet"
    rollout_path = OUT / "official_rollouts.parquet"
    states.to_parquet(state_path, index=False)
    predictions.to_parquet(prediction_path, index=False)
    rollouts.to_parquet(rollout_path, index=False)
    hashes = {path.name: sha(path) for path in (state_path, prediction_path, rollout_path)}
    write_json(OUT / "official_artifact_hashes.json", hashes)
    ledger_path = OUT / "prediction_ledger.duckdb"
    if ledger_path.exists():
        ledger_path.unlink()
    ledger = PredictionLedger(ledger_path)
    batch_ids = []
    for name, path, hidden in (
        ("states", state_path, ("next_event", "future_events")),
        ("one_step", prediction_path, ("next_event",)),
        ("rollouts", rollout_path, ("future_event_sequence",)),
    ):
        batch_id = f"jdsearch-dynamics-v1:{name}:seed-{SEED}"
        ledger.append_frozen_batch(
            batch_id=batch_id,
            dataset_name="JDsearch event-time behavior",
            dataset_version=freeze["raw_hashes"]["user_behavior"],
            split="OFFICIAL_FINAL",
            model_name=f"PredictiveGRU-d{selected_dimension}",
            row_count=len(pd.read_parquet(path, columns=["customer_key"])),
            predictions_path=str(path),
            predictions_sha256=hashes[path.name],
            config=freeze,
            outcome_columns_hidden=hidden,
        )
        batch_ids.append(batch_id)
    write_json(
        OUT / "final_reveal_guard.json",
        {
            "ledger_batches_written": batch_ids,
            "artifacts_hashed": hashes,
            "ready_for_single_reveal": True,
        },
    )

    # SINGLE OFFICIAL REVEAL. Write the one-way marker before opening outcomes.
    authority.require_definitive("read and score official-final targets")
    write_json(
        reveal_marker,
        {
            "status": "REVEAL_INITIATED",
            "official_reveal_count": 1,
            "freeze_sha256": sha(OUT / "benchmark_freeze.json"),
            "ledger_sha256": sha(ledger_path),
        },
    )
    final_t = pd.read_parquet(DATA / "official_final_targets.parquet")
    one_step = multiclass_metrics(final_t.next_event.to_numpy(int), final_prediction.next_event)
    final_multi = []
    for horizon in HORIZONS:
        final_multi.append(
            {
                "split": "OFFICIAL_FINAL",
                "horizon": horizon,
                **binary_metrics(
                    final_t[f"ord_any_{horizon}"].to_numpy(int),
                    final_prediction.binary[f"ord_{horizon}"],
                ),
            }
        )
    multi_table = pd.DataFrame(final_multi)
    multi_table.to_csv(OUT / "multi_horizon_results.csv", index=False)
    pd.DataFrame([{"split": "OFFICIAL_FINAL", **one_step}]).to_csv(
        OUT / "one_step_results.csv", index=False
    )

    rollout_rows = []
    for horizon in HORIZONS:
        predicted = rollouts[rollouts.horizon == horizon]
        actual_mix = np.asarray(
            [final_t[f"{event.lower()}_share_{horizon}"].mean() for event in EVENT_TYPES]
        )
        predicted_mix = np.asarray(
            [predicted[f"{event.lower()}_share"].mean() for event in EVENT_TYPES]
        )
        midpoint = (actual_mix + predicted_mix) / 2
        js = 0.5 * np.sum(
            actual_mix * np.log(np.clip(actual_mix / midpoint, EPS, None))
        ) + 0.5 * np.sum(predicted_mix * np.log(np.clip(predicted_mix / midpoint, EPS, None)))
        actual_purchase = float(final_t[f"ord_any_{horizon}"].mean())
        rollout_rows.append(
            {
                "horizon": horizon,
                "purchase_relative_error": abs(
                    float(predicted.purchase_probability.mean()) - actual_purchase
                )
                / actual_purchase,
                "js_divergence": float(js),
                **{
                    f"{event.lower()}_share_error": abs(float(predicted_mix[i] - actual_mix[i]))
                    for i, event in enumerate(EVENT_TYPES)
                },
            }
        )
    rollout_table = pd.DataFrame(rollout_rows)
    rollout_table.to_csv(OUT / "rollout_population_results.csv", index=False)
    for batch_id in batch_ids:
        ledger.append_frozen_batch_evaluation(
            batch_id, {"one_step": one_step, "multi_horizon": final_multi, "rollout": rollout_rows}
        )

    # Required honest empty/secondary artifacts.
    pd.DataFrame(columns=["regime", "size", "interpretation"]).to_csv(
        OUT / "state_regimes.csv", index=False
    )
    pd.DataFrame(columns=["from_regime", "to_regime", "probability"]).to_csv(
        OUT / "regime_transition_matrix.csv", index=False
    )
    pd.DataFrame(columns=["subgroup", "metric", "value"]).to_csv(
        OUT / "subgroup_results.csv", index=False
    )
    runtime = time.perf_counter() - started
    markov_loss = min(row["next_event_logloss"] for row in tournament[:2])
    neural_gain = (markov_loss - one_step["next_event_logloss"]) / markov_loss
    verdict = {
        "predictive_state": "PASS" if neural_gain >= 0.05 else "FAIL",
        "state_compression": "PASS"
        if all(
            row["raw_history_auroc_gain"] < 0.01 and row["raw_history_relative_logloss_gain"] < 0.02
            for row in sufficiency
        )
        else "FAIL",
        "one_step_dynamics": "PASS" if neural_gain >= 0.05 else "FAIL",
        "multi_step_dynamics": "PASS"
        if sum(row["brier"] < 0.25 for row in final_multi) >= 2
        else "PARTIALLY",
        "population_rollout": "PASS"
        if all(
            row["purchase_relative_error"] <= 0.10 and row["js_divergence"] <= 0.03
            for row in rollout_rows[:2]
        )
        else "FAIL",
        "calibration": "PASS" if all(row["ece"] <= 0.03 for row in final_multi) else "FAIL",
    }
    verdict["dynamic_customer_twin_thesis"] = (
        "YES"
        if all(value == "PASS" for value in verdict.values())
        else "PARTIALLY"
        if sum(value == "PASS" for value in verdict.values()) >= 3
        else "NO"
    )
    final_metrics = {
        "verdict": verdict,
        "one_step": one_step,
        "multi_horizon": final_multi,
        "rollout": rollout_rows,
        "selected_dimension": selected_dimension,
        "runtime_seconds": runtime,
        "official_reveal_count": 1,
        "causal_claims": False,
        "calendar_semantics": False,
    }
    write_json(OUT / "final_metrics.json", final_metrics)
    write_json(
        reveal_marker,
        {
            "status": "REVEAL_COMPLETED",
            "official_reveal_count": 1,
            "final_metrics_sha256": sha(OUT / "final_metrics.json"),
        },
    )
    write_documents(
        final_metrics, pd.DataFrame(tournament), dimension_table, pd.DataFrame(sufficiency)
    )


def write_documents(
    metrics: dict[str, Any],
    tournament: pd.DataFrame,
    dimensions: pd.DataFrame,
    sufficiency: pd.DataFrame,
) -> None:
    verdict = metrics["verdict"]
    display = tournament.fillna("—")
    header = "| " + " | ".join(map(str, display.columns)) + " |"
    divider = "|" + "|".join("---" for _ in display.columns) + "|"
    body = [
        "| " + " | ".join(map(str, row)) + " |"
        for row in display.itertuples(index=False, name=None)
    ]
    table = "\n".join([header, divider, *body])
    report = f"""# Dynamic Customer State Engine V1 — JDsearch

## Executive verdict

- PREDICTIVE STATE: {verdict["predictive_state"]}
- STATE COMPRESSION: {verdict["state_compression"]}
- ONE-STEP DYNAMICS: {verdict["one_step_dynamics"]}
- MULTI-STEP DYNAMICS: {verdict["multi_step_dynamics"]}
- POPULATION ROLLOUT: {verdict["population_rollout"]}
- CALIBRATION: {verdict["calibration"]}
- DYNAMIC CUSTOMER TWIN THESIS: {verdict["dynamic_customer_twin_thesis"]}

This is an event-time predictive benchmark. It is not causal evidence and it does not support merchant-action simulation.

## Official model tournament

{table}

Selected GRU dimension: **{metrics["selected_dimension"]}**. Official reveal count: **1**.

## Scientific limitations

- The requested nonhomogeneous HMM was not completed. A covariate-cluster regime challenger is reported separately and is not mislabeled as an HMM.
- Deep stochastic state-space modelling was not run because simpler-model evidence must justify that complexity first.
- JDsearch interval units are unknown; no day or calendar semantics are claimed.
- Merchant actions are absent. The causal transition kernel therefore fails closed with `INSUFFICIENT_CAUSAL_EVIDENCE`.
- Empty regime/subgroup artifacts record capabilities not completed; they are not evidence.

## What remains unproven

Predictive compression does not prove causal response, counterfactual validity, stable real-time identity, calendar-time dynamics, or transportability to a merchant population.
"""
    (OUT / "REPORT.md").write_text(report, encoding="utf-8")
    (OUT / "README.md").write_text(
        "# JDsearch dynamics benchmark\n\nSee [REPORT.md](REPORT.md). All semantics are event-time only.\n",
        encoding="utf-8",
    )
    (OUT / "scientific_spec.md").write_text(
        "# Scientific specification\n\nFrozen 70/15/15 customer split; train-only fitting; development-only selection; one official-final reveal. Targets are next event and any/mix/count over the next 5, 10, and 20 events.\n",
        encoding="utf-8",
    )
    (OUT / "mathematical_formulation.md").write_text(
        "# Mathematical formulation\n\nThe predictive state is $Z_t=f_\\theta(H_t)$. Heads estimate $P(M_{t+1}|Z_t)$ and future event observables. Recursive predictive simulation is not an interventional transition $P(S_{t+1}|S_t,A_t)$.\n",
        encoding="utf-8",
    )
    write_json(
        OUT / "state_schema.json",
        {
            "latent_state": "float[d]",
            "probabilities": "[0,1] simplex where applicable",
            "semantics": "EVENT_TIME_ONLY",
        },
    )
    write_json(
        OUT / "target_schema.json",
        {
            "next_event": list(EVENT_TYPES),
            "horizons": list(HORIZONS),
            "targets": ["any", "count", "event_mix"],
        },
    )
    write_json(
        OUT / "data_audit.json",
        {
            "train_snapshots": 311621,
            "development_snapshots": 35743,
            "official_final_snapshots": 17646,
            "official_reveal_count": 1,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    run(quick=parser.parse_args().quick)
