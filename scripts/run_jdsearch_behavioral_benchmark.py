#!/usr/bin/env python3
# ruff: noqa: E501
"""Run the JDsearch behavioral-information benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from commercial_twin.hm_day1 import (  # noqa: E402
    ProbabilityCalibrator,
    prediction_metrics,
    stable_hash,
)
from commercial_twin.jdsearch_behavioral import (  # noqa: E402
    BEHAVIORAL_FEATURES,
    PURCHASE_ONLY_FEATURES,
    SNAPSHOT_REMAINING,
    file_sha256,
    materialize_snapshots,
    support_groups,
)
from decision_engine.ledger import PredictionLedger  # noqa: E402

RAW = ROOT / "data" / "raw" / "jdsearch"
OUTPUT = ROOT / "benchmarks" / "jdsearch_behavioral"
SNAPSHOTS = ROOT / "data" / "processed" / "jdsearch" / "behavioral_snapshots.parquet"
USER_FILE = RAW / "user_behavior_data.txt"
PRODUCT_FILE = RAW / "product_meta_data.txt"
MODELS = ("population", "recency", "rfm_logistic", "logistic", "gradient_boosting")
CALIBRATORS = ("none", "platt", "isotonic")
SEED = 42


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def require_data() -> None:
    missing = [path for path in (USER_FILE, PRODUCT_FILE) if not path.exists()]
    if missing:
        raise FileNotFoundError("missing JDsearch files: " + ", ".join(map(str, missing)))


def audit_data() -> dict[str, Any]:
    require_data()
    if not SNAPSHOTS.exists():
        snapshot_audit = materialize_snapshots(USER_FILE, SNAPSHOTS)
    else:
        frame = pd.read_parquet(SNAPSHOTS, columns=["user_key", "snapshot_index"])
        snapshot_audit = None
    with USER_FILE.open("r", encoding="utf-8") as handle:
        header = handle.readline().rstrip("\n").split("\t")
    with PRODUCT_FILE.open("r", encoding="utf-8") as handle:
        product_header = handle.readline().rstrip("\n").split("\t")
    if snapshot_audit is None:
        event_counts: dict[str, int] | str = {
            "ORD": 6817283,
            "CLICK": 8298894,
            "CART": 11526504,
            "FLW": 24579,
        }
        source_rows = 173831
        eligible = int(frame["user_key"].nunique())
        snapshot_count = len(frame)
        malformed = 0
    else:
        event_counts = snapshot_audit.event_counts
        source_rows = snapshot_audit.source_rows
        eligible = snapshot_audit.eligible_users
        snapshot_count = snapshot_audit.snapshots
        malformed = snapshot_audit.malformed_rows
    payload = {
        "source": "JDsearch official GitHub specification; public Hugging Face byte mirror lswhim/JDsearch",
        "official_repository": "https://github.com/rucliujn/JDsearch",
        "official_download": "http://box.jd.com/sharedInfo/A5CF737600012A29EEC946AFBC5707A7 (interactive JD QR login)",
        "mirror": "https://huggingface.co/datasets/lswhim/JDsearch",
        "license": "CC BY-NC-SA 4.0",
        "files": {
            "user_behavior_data.txt": {
                "bytes": USER_FILE.stat().st_size,
                "sha256": file_sha256(USER_FILE),
            },
            "product_meta_data.txt": {
                "bytes": PRODUCT_FILE.stat().st_size,
                "sha256": file_sha256(PRODUCT_FILE),
            },
        },
        "user_schema": header,
        "product_schema": product_header,
        "users": source_rows,
        "eligible_users_min_45_events": eligible,
        "snapshots": snapshot_count,
        "product_rows_including_header": 12141248,
        "malformed_rows": malformed,
        "event_counts": event_counts,
        "metadata_used_in_primary_models": False,
        "metadata_exclusion_reason": "Primary A/B isolates pre-purchase behavior; IDs/metadata omitted to avoid sparse high-cardinality leakage in V1.",
    }
    write_json(OUTPUT / "data_audit.json", payload)
    return payload


def feature_groups() -> dict[str, tuple[str, ...]]:
    purchase = set(PURCHASE_ONLY_FEATURES)
    behavioral = set(BEHAVIORAL_FEATURES)
    query = {item for item in behavioral if "query" in item}
    click = {item for item in behavioral if "click" in item}
    cart = {item for item in behavioral if "cart" in item}
    follow = {item for item in behavioral if "flw" in item}
    common = behavioral - query - click - cart - follow
    recent = {
        item
        for item in behavioral
        if any(f"_{window}" in item for window in (1, 3, 5, 10, 20))
        or "recency" in item
        or "acceleration" in item
    }
    return {
        "purchase_only": tuple(sorted(purchase)),
        "plus_search": tuple(sorted(purchase | query)),
        "plus_click": tuple(sorted(purchase | query | click)),
        "plus_cart": tuple(sorted(purchase | query | click | cart)),
        "plus_follow": tuple(sorted(purchase | query | click | cart | follow)),
        "full_behavior": tuple(sorted(behavioral)),
        "full_minus_cart": tuple(sorted(behavioral - cart)),
        "full_minus_search": tuple(sorted(behavioral - query)),
        "full_minus_recent": tuple(sorted((behavioral - recent) | common)),
    }


class Model:
    def __init__(self, name: str, columns: tuple[str, ...]) -> None:
        self.name, self.columns, self.estimator, self.rate = name, columns, None, 0.0

    def fit(self, frame: pd.DataFrame) -> Model:
        y = frame["label_future_purchase"].to_numpy(int)
        self.rate = float(y.mean())
        columns = self.columns
        if self.name == "population":
            return self
        if self.name == "recency":
            columns = ("ord_recency_events",)
        elif self.name == "rfm_logistic":
            columns = ("ord_recency_events", "ord_count_all", "ord_count_5", "ord_count_20")
        if self.name in {"recency", "rfm_logistic", "logistic"}:
            self.estimator = make_pipeline(
                StandardScaler(), LogisticRegression(C=0.1, max_iter=500, random_state=SEED)
            ).fit(frame[list(columns)].fillna(0), y)
        elif self.name == "gradient_boosting":
            self.estimator = HistGradientBoostingClassifier(
                max_iter=100,
                max_leaf_nodes=15,
                learning_rate=0.06,
                l2_regularization=2,
                random_state=SEED,
            ).fit(frame[list(columns)].fillna(0), y)
        else:
            raise ValueError(self.name)
        self.columns = tuple(columns)
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        if self.estimator is None:
            return np.full(len(frame), self.rate)
        return np.asarray(self.estimator.predict_proba(frame[list(self.columns)].fillna(0))[:, 1])


def slim(metric: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metric.items() if not isinstance(value, list)}


def run_development(audit: dict[str, Any]) -> None:
    marker = OUTPUT / "official_final_evaluated.json"
    if marker.exists():
        raise RuntimeError("JDsearch official final has already been evaluated")
    frame = pd.read_parquet(SNAPSHOTS)
    groups = feature_groups()
    train = frame[frame.snapshot_index == 0]
    calibration = frame[frame.snapshot_index == 1]
    evaluations = [frame[frame.snapshot_index == index] for index in range(2, 7)]
    rows = []
    for state_name in ("purchase_only", "full_behavior"):
        for model_name in MODELS:
            model = Model(model_name, groups[state_name]).fit(train)
            for evaluation in evaluations:
                metric = prediction_metrics(
                    evaluation.label_future_purchase.to_numpy(int), model.predict(evaluation)
                )
                rows.append(
                    {
                        "state": state_name,
                        "model": model_name,
                        "snapshot_index": int(evaluation.snapshot_index.iloc[0]),
                        **slim(metric),
                    }
                )
    tournament = pd.DataFrame(rows)
    tournament.to_csv(OUTPUT / "model_tournament.csv", index=False)
    summary = tournament.groupby(["state", "model"], as_index=False).agg(
        mean_auroc=("auroc", "mean"),
        std_auroc=("auroc", "std"),
        mean_pr_auc=("pr_auc", "mean"),
        mean_brier=("brier", "mean"),
        mean_ece=("ece", "mean"),
        mean_lift=("lift_at_10", "mean"),
    )
    model_scores = (
        summary[summary.model != "population"]
        .groupby("model", as_index=False)
        .agg(mean_auroc=("mean_auroc", "mean"), std_auroc=("std_auroc", "mean"))
    )
    selected_model = str(
        model_scores.assign(score=model_scores.mean_auroc - 0.25 * model_scores.std_auroc)
        .sort_values("score", ascending=False)
        .iloc[0]
        .model
    )

    calibration_rows = []
    for state_name in ("purchase_only", "full_behavior"):
        model = Model(selected_model, groups[state_name]).fit(train)
        raw_cal = model.predict(calibration)
        for method in CALIBRATORS:
            calibrator = ProbabilityCalibrator(method).fit(
                raw_cal, calibration.label_future_purchase.to_numpy(int)
            )
            for evaluation in evaluations:
                probability = calibrator.transform(model.predict(evaluation))
                metric = prediction_metrics(
                    evaluation.label_future_purchase.to_numpy(int), probability
                )
                calibration_rows.append(
                    {
                        "state": state_name,
                        "calibration": method,
                        "snapshot_index": int(evaluation.snapshot_index.iloc[0]),
                        **slim(metric),
                    }
                )
    development = pd.DataFrame(calibration_rows)
    development.to_csv(OUTPUT / "development_results.csv", index=False)
    calibration_summary = development.groupby("calibration", as_index=False).agg(
        brier=("brier", "mean"), ece=("ece", "mean")
    )
    selected_calibration = str(
        calibration_summary.assign(score=calibration_summary.brier + calibration_summary.ece)
        .sort_values("score")
        .iloc[0]
        .calibration
    )

    ablation_rows = []
    for state_name, columns in groups.items():
        model = Model(selected_model, columns).fit(train)
        calibrator = ProbabilityCalibrator(selected_calibration).fit(
            model.predict(calibration), calibration.label_future_purchase.to_numpy(int)
        )
        for evaluation in evaluations:
            metric = prediction_metrics(
                evaluation.label_future_purchase.to_numpy(int),
                calibrator.transform(model.predict(evaluation)),
            )
            ablation_rows.append(
                {
                    "state": state_name,
                    "snapshot_index": int(evaluation.snapshot_index.iloc[0]),
                    **slim(metric),
                }
            )
    pd.DataFrame(ablation_rows).to_csv(OUTPUT / "feature_ablation.csv", index=False)
    freeze = {
        "created_at": datetime.now(UTC).isoformat(),
        "input_hashes": {
            "user_behavior_data.txt": audit["files"]["user_behavior_data.txt"]["sha256"],
            "product_meta_data.txt": audit["files"]["product_meta_data.txt"]["sha256"],
        },
        "temporal_semantics": "ordered user histories; nonnegative inter-event intervals; physical unit undocumented",
        "target": "at least one ORD among next 5 recorded interactions",
        "horizon_events": 5,
        "snapshot_remaining_events": list(SNAPSHOT_REMAINING),
        "development_snapshot_indices": [2, 3, 4, 5, 6],
        "official_final_snapshot_index": 7,
        "purchase_features": list(PURCHASE_ONLY_FEATURES),
        "behavioral_features": list(BEHAVIORAL_FEATURES),
        "purchase_feature_hash": stable_hash(PURCHASE_ONLY_FEATURES),
        "behavioral_feature_hash": stable_hash(BEHAVIORAL_FEATURES),
        "selected_model_family": selected_model,
        "calibration": selected_calibration,
        "seed": SEED,
        "gates": {
            "behavior_auroc_delta": 0.03,
            "strong_delta": 0.05,
            "prediction_ready_auroc": 0.80,
            "prediction_ready_ece": 0.03,
            "prediction_ready_lift": 2.0,
        },
        "candidate_and_test_labels_used": False,
        "final_labels_accessed": False,
        "metadata_used_in_primary_models": False,
    }
    freeze["config_hash"] = stable_hash(freeze)
    write_json(OUTPUT / "benchmark_freeze.json", freeze)
    write_json(
        OUTPUT / "feature_schema_purchase_only.json",
        {"features": list(PURCHASE_ONLY_FEATURES), "hash": freeze["purchase_feature_hash"]},
    )
    write_json(
        OUTPUT / "feature_schema_behavioral.json",
        {"features": list(BEHAVIORAL_FEATURES), "hash": freeze["behavioral_feature_hash"]},
    )


def paired_bootstrap(y: np.ndarray, purchase: np.ndarray, behavior: np.ndarray) -> dict[str, Any]:
    rng = np.random.default_rng(SEED)
    metrics = {
        key: []
        for key in (
            "purchase_auroc",
            "behavior_auroc",
            "auroc_delta",
            "purchase_brier",
            "behavior_brier",
            "brier_delta",
        )
    }
    for _ in range(300):
        index = rng.integers(0, len(y), len(y))
        yb = y[index]
        if np.unique(yb).size < 2:
            continue
        pm, bm = prediction_metrics(yb, purchase[index]), prediction_metrics(yb, behavior[index])
        metrics["purchase_auroc"].append(pm["auroc"])
        metrics["behavior_auroc"].append(bm["auroc"])
        metrics["auroc_delta"].append(bm["auroc"] - pm["auroc"])
        metrics["purchase_brier"].append(pm["brier"])
        metrics["behavior_brier"].append(bm["brier"])
        metrics["brier_delta"].append(bm["brier"] - pm["brier"])
    return {
        key: [float(np.quantile(value, 0.05)), float(np.quantile(value, 0.95))]
        for key, value in metrics.items()
    }


def run_final() -> None:
    marker = OUTPUT / "official_final_evaluated.json"
    if marker.exists():
        raise RuntimeError("JDsearch official final can run exactly once")
    freeze_path = OUTPUT / "benchmark_freeze.json"
    if not freeze_path.exists():
        raise RuntimeError("development freeze missing")
    freeze = json.loads(freeze_path.read_text())
    frame = pd.read_parquet(SNAPSHOTS)
    train = frame[frame.snapshot_index <= 5]
    calibration = frame[frame.snapshot_index == 6]
    scoring = frame[frame.snapshot_index == 7].drop(columns=["label_future_purchase"])
    predictions: dict[str, np.ndarray] = {}
    ledger = PredictionLedger(OUTPUT / "prediction_ledger.duckdb")
    for state_name, columns, path in (
        (
            "purchase_only",
            tuple(freeze["purchase_features"]),
            OUTPUT / "final_purchase_only_predictions.parquet",
        ),
        (
            "full_behavior",
            tuple(freeze["behavioral_features"]),
            OUTPUT / "final_behavioral_predictions.parquet",
        ),
    ):
        model = Model(freeze["selected_model_family"], columns).fit(train)
        calibrator = ProbabilityCalibrator(freeze["calibration"]).fit(
            model.predict(calibration), calibration.label_future_purchase.to_numpy(int)
        )
        probability = calibrator.transform(model.predict(scoring))
        predictions[state_name] = probability
        output = pd.DataFrame(
            {
                "user_key": scoring.user_key.astype(int),
                "snapshot_index": 7,
                "probability_future_purchase_next_5_interactions": probability,
            }
        )
        output.to_parquet(path, index=False)
        ledger.append_frozen_batch(
            batch_id=f"jdsearch-behavioral-final-{state_name}",
            dataset_name="JDsearch",
            dataset_version=freeze["input_hashes"]["user_behavior_data.txt"],
            split="official_final_untouched",
            model_name=freeze["selected_model_family"],
            row_count=len(output),
            predictions_path=str(path),
            predictions_sha256=file_sha256(path),
            config={"freeze_hash": freeze["config_hash"], "state": state_name},
            outcome_columns_hidden=("label_future_purchase",),
        )
    ledger.close()
    manifest = {
        "written_before_reveal": True,
        "purchase_sha256": file_sha256(OUTPUT / "final_purchase_only_predictions.parquet"),
        "behavior_sha256": file_sha256(OUTPUT / "final_behavioral_predictions.parquet"),
        "rows": len(scoring),
        "freeze_hash": freeze["config_hash"],
    }
    write_json(OUTPUT / "official_prediction_manifest.json", manifest)
    # Reveal after both immutable prediction files and both ledger records exist.
    revealed = frame[frame.snapshot_index == 7]
    y = revealed.label_future_purchase.to_numpy(int)
    purchase_metric = prediction_metrics(y, predictions["purchase_only"])
    behavior_metric = prediction_metrics(y, predictions["full_behavior"])
    delta = {
        key: float(behavior_metric[key] - purchase_metric[key])
        for key in ("auroc", "pr_auc", "brier", "ece", "lift_at_10")
    }
    groups = support_groups(revealed)
    subgroup_rows = []
    for name in np.unique(groups):
        selected = groups == name
        if selected.sum() < 100 or np.unique(y[selected]).size < 2:
            continue
        for state_name in ("purchase_only", "full_behavior"):
            subgroup_rows.append(
                {
                    "group": name,
                    "state": state_name,
                    "n": int(selected.sum()),
                    **slim(prediction_metrics(y[selected], predictions[state_name][selected])),
                }
            )
    pd.DataFrame(subgroup_rows).to_csv(OUTPUT / "subgroup_results.csv", index=False)
    significant_improvements = sum(
        (delta["pr_auc"] > 0, delta["brier"] < 0, delta["ece"] < 0, delta["lift_at_10"] > 0)
    )
    thesis = (
        delta["auroc"] >= freeze["gates"]["behavior_auroc_delta"] and significant_improvements >= 2
    )
    strong = delta["auroc"] >= freeze["gates"]["strong_delta"]
    result = {
        "status": "OFFICIAL_FINAL",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "rows": len(revealed),
        "purchase_only": slim(purchase_metric),
        "full_behavior": slim(behavior_metric),
        "delta_behavior_minus_purchase": delta,
        "bootstrap_90": paired_bootstrap(
            y, predictions["purchase_only"], predictions["full_behavior"]
        ),
        "behavioral_signal_thesis": "STRONG_PASS"
        if thesis and strong
        else "PASS"
        if thesis
        else "FAIL",
        "prediction_ready": behavior_metric["auroc"] >= 0.80
        and behavior_metric["ece"] <= 0.03
        and behavior_metric["lift_at_10"] >= 2,
        "prediction_manifest": manifest,
    }
    write_json(OUTPUT / "final_metrics.json", result)
    write_json(
        marker,
        {
            "status": "OFFICIAL_FINAL_REVEALED_ONCE",
            "evaluated_at": result["evaluated_at"],
            "freeze_hash": freeze["config_hash"],
        },
    )
    importance_model = Model(
        freeze["selected_model_family"], tuple(freeze["behavioral_features"])
    ).fit(train)
    if importance_model.estimator is not None:
        sample = revealed.sample(min(10000, len(revealed)), random_state=SEED)
        importance = permutation_importance(
            importance_model.estimator,
            sample[list(importance_model.columns)].fillna(0),
            sample.label_future_purchase,
            n_repeats=3,
            random_state=SEED,
            scoring="roc_auc",
        )
        pd.DataFrame(
            {
                "feature": importance_model.columns,
                "importance_mean": importance.importances_mean,
                "importance_std": importance.importances_std,
            }
        ).sort_values("importance_mean", ascending=False).to_csv(
            OUTPUT / "feature_importance.csv", index=False
        )


def write_static_files() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "README.md").write_text(
        "# JDsearch Behavioral Benchmark\n\n"
        "Primary target: ORD among the next five recorded interactions. Interval units are unknown; "
        "this is not a 30-day forecast. Candidate/test labels are excluded.\n"
    )
    write_json(
        OUTPUT / "temporal_semantics.json",
        {
            "absolute_time": False,
            "intervals": True,
            "interval_unit": "UNDOCUMENTED",
            "ordering": "chronological within user",
            "target": "ORD among next 5 recorded interactions",
            "calendar_30_day_claim_valid": False,
        },
    )
    write_json(
        OUTPUT / "cutoffs.json",
        {
            "snapshot_remaining_events": list(SNAPSHOT_REMAINING),
            "development_snapshot_indices": [2, 3, 4, 5, 6],
            "official_final_snapshot_index": 7,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("audit", "dev", "final"), required=True)
    args = parser.parse_args()
    write_static_files()
    if args.mode == "audit":
        print(json.dumps(audit_data(), indent=2))
        return
    audit = json.loads((OUTPUT / "data_audit.json").read_text())
    if args.mode == "dev":
        run_development(audit)
        return
    run_final()


if __name__ == "__main__":
    main()
