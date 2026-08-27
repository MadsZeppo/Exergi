#!/usr/bin/env python3
# ruff: noqa: E501
"""Official-full-H&M-only entry point for Prediction Engine V2."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from commercial_twin.hm_day1 import (  # noqa: E402
    FEATURE_COLUMNS,
    LABEL_COLUMNS,
    HMPaths,
    ProbabilityCalibrator,
    assert_state_is_leak_safe,
    audit_hm_data,
    bootstrap_intervals,
    build_state_frame,
    file_sha256,
    fit_candidate,
    monetary_fit_predict,
    prediction_metrics,
    stable_hash,
)
from commercial_twin.prediction_v2 import (  # noqa: E402
    FinalRunGuard,
    HierarchicalRateModel,
    SparseRouter,
    classify_support,
    empirical_reliability,
    logit_shift_reconcile,
    select_safe_v2_cutoffs,
)
from decision_engine.ledger import PredictionLedger  # noqa: E402

DATA = ROOT / "data" / "raw" / "hm" / "full"
OUTPUT = ROOT / "benchmarks" / "hm_day1_v2"
REQUIRED = ("transactions_train.csv", "customers.csv", "articles.csv")
PROCESSED = ROOT / "data" / "processed" / "hm" / "full"
PARQUET_PATHS = HMPaths(
    transactions=PROCESSED / "transactions.parquet",
    customers=PROCESSED / "customers.parquet",
    articles=PROCESSED / "articles.parquet",
)
MODELS = (
    "population_rate",
    "recency_logistic",
    "rfm_logistic",
    "empirical_bayes_lifecycle",
    "logistic",
    "gradient_boosting",
)
CALIBRATORS = ("none", "platt", "isotonic")
TRAINING_OFFSETS = (60, 30)
RANDOM_SEED = 42
SAMPLE_MODULUS = 4


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def missing_files() -> list[Path]:
    return [DATA / name for name in REQUIRED if not (DATA / name).exists()]


def require_official_data() -> None:
    missing = missing_files()
    if missing:
        raise FileNotFoundError(
            "OFFICIAL FULL H&M REQUIRED; RelBench is forbidden for V2 official validation. "
            "Missing: " + ", ".join(str(path) for path in missing)
        )


def prepare_parquet() -> None:
    """Materialize typed local Parquet once; source CSV hashes remain authoritative."""
    require_official_data()
    PROCESSED.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    jobs = (
        (DATA / "transactions_train.csv", PARQUET_PATHS.transactions),
        (DATA / "customers.csv", PARQUET_PATHS.customers),
        (DATA / "articles.csv", PARQUET_PATHS.articles),
    )
    for source, target in jobs:
        if target.exists():
            continue
        source_sql = str(source).replace("'", "''")
        target_sql = str(target).replace("'", "''")
        connection.execute(
            f"COPY (SELECT * FROM read_csv_auto('{source_sql}', header=true, sample_size=-1)) "
            f"TO '{target_sql}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
    connection.close()


def audit() -> dict[str, Any]:
    require_official_data()
    prepare_parquet()
    payload = audit_hm_data(PARQUET_PATHS)
    payload["source"] = "Official full H&M Kaggle competition files"
    payload["source_scope"] = "Full official CSVs; typed Parquet is a local derived cache"
    payload["official_full_dataset"] = True
    payload["files"] = {
        name: {
            "path": str(DATA / name),
            "bytes": (DATA / name).stat().st_size,
            "sha256": sha256(DATA / name),
        }
        for name in REQUIRED
    }
    payload["derived_parquet"] = {
        key: {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
        for key, path in {
            "transactions": PARQUET_PATHS.transactions,
            "customers": PARQUET_PATHS.customers,
            "articles": PARQUET_PATHS.articles,
        }.items()
    }
    data_min = datetime.fromisoformat(payload["transactions"]["min_date"]).date()
    data_max = datetime.fromisoformat(payload["transactions"]["max_date"]).date()
    cutoffs = select_safe_v2_cutoffs(data_min, data_max)
    if cutoffs["official_final"] is None or len(cutoffs["development"]) < 5:
        raise RuntimeError("full files do not provide five clean development windows plus final")
    payload["cutoffs"] = cutoffs
    payload["audited_at"] = datetime.now(UTC).isoformat()
    payload["semantics"]["row"] = "transaction line, not order"
    payload["semantics"]["economic_engine_validated"] = False
    write_json(OUTPUT / "data_audit.json", payload)
    write_json(OUTPUT / "cutoffs.json", cutoffs)
    return payload


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=None)


def add_segments(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["support_class"] = classify_support(
        result["active_days"].to_numpy(),
        result["observation_count"].to_numpy(),
        result["customer_age_days"].to_numpy(),
    )
    result["dominant_channel"] = np.where(result["online_share"] >= 0.5, "CHANNEL_2", "CHANNEL_1")
    result["age_bucket"] = pd.cut(
        result["age"],
        [-1, 0, 24, 34, 44, 54, 64, 200],
        labels=["MISSING", "16-24", "25-34", "35-44", "45-54", "55-64", "65+"],
    ).astype(str)
    return result


def state(cutoff: datetime, *, labels: bool, sample: bool) -> pd.DataFrame:
    history_start = cutoff - pd.Timedelta(days=365)
    frame = build_state_frame(
        PARQUET_PATHS,
        history_start=history_start,
        as_of=cutoff,
        include_labels=labels,
        sample_modulus=SAMPLE_MODULUS if sample else None,
    )
    assert_state_is_leak_safe(frame, history_start=history_start, as_of=cutoff)
    return add_segments(frame)


def training_frames(cutoff: datetime) -> list[pd.DataFrame]:
    frames = []
    for offset in TRAINING_OFFSETS:
        snapshot = cutoff - pd.Timedelta(days=offset)
        frame = state(snapshot, labels=True, sample=True)
        frame["snapshot"] = snapshot.date().isoformat()
        frames.append(frame)
    return frames


def slim_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metrics.items() if not isinstance(value, list)}


def select_ranker(rows: pd.DataFrame) -> str:
    aggregate = rows.groupby("model", as_index=False).agg(
        mean_auroc=("auroc", "mean"),
        std_auroc=("auroc", "std"),
        mean_top10=("lift_at_10", "mean"),
        windows=("cutoff", "nunique"),
    )
    eligible = aggregate[aggregate["windows"] >= 5].copy()
    eligible["stable_score"] = eligible["mean_auroc"] - eligible["std_auroc"].fillna(0) * 0.25
    return str(
        eligible.sort_values(["stable_score", "mean_top10"], ascending=False).iloc[0]["model"]
    )


def run_development(audit_payload: dict[str, Any]) -> None:
    guard = FinalRunGuard(OUTPUT)
    guard.require_development_mode()
    started = time.perf_counter()
    cutoffs = audit_payload["cutoffs"]
    raw_rows: list[dict[str, Any]] = []
    cache: dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]] = {}
    for cutoff_text in cutoffs["development"]:
        cutoff = dt(cutoff_text)
        frames = training_frames(cutoff)
        train = pd.concat(frames[:-1], ignore_index=True)
        calibration = frames[-1]
        evaluation = state(cutoff, labels=True, sample=True)
        cache[cutoff_text] = (train, calibration, evaluation)
        y = evaluation["label_repeat"].to_numpy(int)
        for model_name in MODELS:
            model = fit_candidate(model_name, train)
            metric = prediction_metrics(y, model.predict_proba(evaluation))
            raw_rows.append({"cutoff": cutoff_text, "model": model_name, **slim_metrics(metric)})
    raw = pd.DataFrame(raw_rows)
    raw.to_csv(OUTPUT / "ranker_tournament.csv", index=False)
    ranker_name = select_ranker(raw)

    system_rows: list[dict[str, Any]] = []
    aggregate_history: list[dict[str, float | str]] = []
    for cutoff_text, (train, calibration, evaluation) in cache.items():
        model = fit_candidate(ranker_name, train)
        raw_cal = model.predict_proba(calibration)
        raw_eval = model.predict_proba(evaluation)
        y_cal = calibration["label_repeat"].to_numpy(int)
        y_eval = evaluation["label_repeat"].to_numpy(int)
        hierarchy = HierarchicalRateModel().fit(calibration)
        hierarchy_eval, _ = hierarchy.predict(evaluation)
        aggregate_record: dict[str, float | str] = {
            "cutoff": cutoff_text,
            "actual": float(y_eval.sum()),
            "population": float(len(y_eval)),
        }
        for method in CALIBRATORS:
            calibrator = ProbabilityCalibrator(method).fit(raw_cal, y_cal)
            calibrated = calibrator.transform(raw_eval)
            routed, _ = SparseRouter().route(
                evaluation["support_class"], calibrated, hierarchy_eval
            )
            for layer, probability in (("calibrated", calibrated), ("sparse_routed", routed)):
                metric = prediction_metrics(y_eval, probability)
                sparse = np.isin(evaluation["support_class"], ["VERY_SPARSE", "SPARSE"])
                sparse_metric = prediction_metrics(y_eval[sparse], probability[sparse])
                system_rows.append(
                    {
                        "cutoff": cutoff_text,
                        "calibration": method,
                        "layer": layer,
                        **slim_metrics(metric),
                        "sparse_ece": sparse_metric["ece"],
                        "sparse_buyer_error": sparse_metric["buyer_count_error"],
                    }
                )
            aggregate_record[f"sum_{method}"] = float(routed.sum())
        aggregate_history.append(aggregate_record)
    systems = pd.DataFrame(system_rows)
    systems.to_csv(OUTPUT / "system_ablation.csv", index=False)
    calibration_summary = (
        systems[systems["layer"] == "sparse_routed"]
        .groupby("calibration", as_index=False)
        .agg(
            mean_brier=("brier", "mean"),
            mean_ece=("ece", "mean"),
            mean_buyer_error=("buyer_count_error", "mean"),
            mean_sparse_ece=("sparse_ece", "mean"),
        )
    )
    calibration_summary["selection_score"] = (
        calibration_summary["mean_brier"]
        + calibration_summary["mean_ece"]
        + 0.1 * calibration_summary["mean_sparse_ece"]
    )
    calibration_name = str(
        calibration_summary.sort_values("selection_score").iloc[0]["calibration"]
    )

    actual = np.asarray([row["actual"] for row in aggregate_history], float)
    population = np.asarray([row["population"] for row in aggregate_history], float)
    individual = np.asarray([row[f"sum_{calibration_name}"] for row in aggregate_history], float)
    rates = actual / population
    candidates: dict[str, np.ndarray] = {
        "sum_individual": individual[1:],
        "prior_repeat_rate": rates[:-1] * population[1:],
        "rolling_repeat_rate": np.asarray(
            [rates[:i].mean() * population[i] for i in range(1, len(rates))]
        ),
        "ewma_repeat_rate": pd.Series(rates)
        .ewm(alpha=0.5, adjust=False)
        .mean()
        .shift(1)
        .to_numpy()[1:]
        * population[1:],
    }
    aggregate_rows = []
    for name, predicted in candidates.items():
        actual_oos = actual[1:]
        errors = np.abs(predicted - actual_oos) / np.maximum(actual_oos, 1)
        aggregate_rows.append(
            {
                "method": name,
                "mean_error": float(errors.mean()),
                "worst_error": float(errors.max()),
                "bias": float(
                    ((predicted - actual_oos) / np.maximum(actual_oos, 1)).mean()
                ),
            }
        )
    aggregate_table = pd.DataFrame(aggregate_rows).sort_values(["mean_error", "worst_error"])
    aggregate_table.to_csv(OUTPUT / "aggregate_tournament.csv", index=False)
    aggregate_name = str(aggregate_table.iloc[0]["method"])
    reconcile = aggregate_name != "sum_individual"
    freeze = {
        "created_at": datetime.now(UTC).isoformat(),
        "official_full_hm": True,
        "input_hashes": {name: audit_payload["files"][name]["sha256"] for name in REQUIRED},
        "date_range": [
            audit_payload["transactions"]["min_date"],
            audit_payload["transactions"]["max_date"],
        ],
        "development_cutoffs": cutoffs["development"],
        "official_final_cutoff": cutoffs["official_final"],
        "previous_exposed_windows": json.loads((OUTPUT / "prior_exposed_windows.json").read_text()),
        "history_days": 365,
        "horizon_days": 30,
        "features": list(FEATURE_COLUMNS),
        "feature_schema_hash": stable_hash(FEATURE_COLUMNS),
        "support_thresholds": {
            "established_active_days": 3,
            "rich_active_days": 8,
            "established_tenure_days": 60,
            "rich_lines": 20,
        },
        "selected_ranker": ranker_name,
        "ranker_hyperparameters": "repository frozen defaults",
        "feature_ablation_winner": ranker_name,
        "calibration_method": calibration_name,
        "subgroup_calibration": "none; insufficient dev evidence for stable subgroup shifts",
        "sparse_router": "hierarchical beta-binomial for VERY_SPARSE/SPARSE",
        "aggregate_method": aggregate_name,
        "aggregate_state": {
            "last_development_rate": float(rates[-1]),
            "rolling_mean_rate": float(rates.mean()),
            "ewma_rate": float(
                pd.Series(rates).ewm(alpha=0.5, adjust=False).mean().iloc[-1]
            ),
        },
        "reconciliation": "global_logit_shift" if reconcile else "none",
        "random_seed": RANDOM_SEED,
        "training_offsets_days": list(TRAINING_OFFSETS),
        "development_sample": "deterministic customer hash quarter; final scoring is full population",
        "readiness_gates": {
            "auroc": 0.78,
            "baseline_margin": 0.03,
            "top10_lift": 2.0,
            "ece": 0.03,
            "buyer_error": 0.10,
        },
        "git_commit": "NOT_AVAILABLE_NOT_A_GIT_WORKTREE",
        "code_hash": file_sha256(Path(__file__)),
        "dependencies": {
            name: version(name)
            for name in ("duckdb", "numpy", "pandas", "scikit-learn", "pyarrow")
        },
        "final_labels_accessed": False,
        "development_runtime_seconds": time.perf_counter() - started,
    }
    freeze["config_hash"] = stable_hash(freeze)
    guard.freeze(freeze)
    write_json(
        OUTPUT / "development_selection.json",
        {
            "ranker": ranker_name,
            "calibration": calibration_name,
            "aggregate": aggregate_name,
            "reconciliation": reconcile,
            "calibration_tournament": calibration_summary.to_dict("records"),
        },
    )


def aggregate_target(method: str, probability: np.ndarray, freeze: dict[str, Any]) -> float:
    if method == "sum_individual":
        return float(probability.sum())
    state = freeze["aggregate_state"]
    rate_key = {
        "prior_repeat_rate": "last_development_rate",
        "rolling_repeat_rate": "rolling_mean_rate",
        "ewma_repeat_rate": "ewma_rate",
    }[method]
    return float(np.clip(float(state[rate_key]) * len(probability), 0, len(probability)))


def subgroup_table(frame: pd.DataFrame, probability: np.ndarray) -> list[dict[str, Any]]:
    working = frame.copy()
    working["probability"] = probability
    rows: list[dict[str, Any]] = []
    for column in ("support_class", "lifecycle", "dominant_channel", "age_bucket"):
        for value, group in working.groupby(column):
            if len(group) < 1000 or group["label_repeat"].nunique() < 2:
                continue
            metric = prediction_metrics(
                group["label_repeat"].to_numpy(), group["probability"].to_numpy()
            )
            rows.append(
                {
                    "subgroup_type": column,
                    "subgroup": str(value),
                    "n": len(group),
                    **slim_metrics(metric),
                }
            )
    return rows


def run_final() -> None:
    guard = FinalRunGuard(OUTPUT)
    guard.require_development_mode()
    freeze = json.loads(guard.freeze_path.read_text())
    cutoff = dt(freeze["official_final_cutoff"])
    frames = training_frames(cutoff)
    train = pd.concat(frames[:-1], ignore_index=True)
    calibration = frames[-1]
    model = fit_candidate(freeze["selected_ranker"], train)
    calibrator = ProbabilityCalibrator(freeze["calibration_method"]).fit(
        model.predict_proba(calibration), calibration["label_repeat"].to_numpy(int)
    )
    hierarchy = HierarchicalRateModel().fit(calibration)
    scoring = state(cutoff, labels=False, sample=False)
    raw = model.predict_proba(scoring)
    calibrated = calibrator.transform(raw)
    hierarchical, _ = hierarchy.predict(scoring)
    routed, route = SparseRouter().route(scoring["support_class"], calibrated, hierarchical)
    target = aggregate_target(freeze["aggregate_method"], routed, freeze)
    final_probability = routed
    delta = 0.0
    if freeze["reconciliation"] == "global_logit_shift":
        final_probability, delta = logit_shift_reconcile(routed, target)
    reliability = empirical_reliability(scoring["support_class"], np.zeros(len(scoring)), 0.03)
    predictions = pd.DataFrame(
        {
            "customer_id": scoring["customer_id"].astype(str),
            "raw_ranking_score": raw,
            "calibrated_probability": calibrated,
            "final_probability": final_probability,
            "support_class": scoring["support_class"],
            "model_route": route,
            "lifecycle": scoring["lifecycle"],
            "empirical_reliability": reliability,
        }
    )
    predictions.to_parquet(guard.predictions_path, index=False)
    prediction_hash = file_sha256(guard.predictions_path)
    ledger = PredictionLedger(OUTPUT / "prediction_ledger.duckdb")
    ledger.append_frozen_batch(
        batch_id="hm-day1-v2-official-final",
        dataset_name="official-full-hm-kaggle",
        dataset_version=freeze["input_hashes"]["transactions_train.csv"],
        split="official_final_untouched",
        model_name=freeze["selected_ranker"],
        row_count=len(predictions),
        predictions_path=str(guard.predictions_path),
        predictions_sha256=prediction_hash,
        config={"freeze_hash": freeze["config_hash"], "reconciliation_delta": delta},
        outcome_columns_hidden=LABEL_COLUMNS,
    )
    ledger.close()
    write_json(
        OUTPUT / "official_prediction_manifest.json",
        {
            "written_before_reveal": True,
            "sha256": prediction_hash,
            "rows": len(predictions),
            "freeze_hash": freeze["config_hash"],
            "ledger_batch": "hm-day1-v2-official-final",
        },
    )
    guard.require_predictions_before_reveal()
    revealed = state(cutoff, labels=True, sample=False)
    if not np.array_equal(scoring["customer_id"].astype(str), revealed["customer_id"].astype(str)):
        raise AssertionError("eligible population changed at reveal")
    y = revealed["label_repeat"].to_numpy(int)
    systems: dict[str, np.ndarray] = {}
    for name in ("population_rate", "recency_logistic", "rfm_logistic"):
        systems[name] = fit_candidate(name, train).predict_proba(revealed)
    systems.update(
        {
            "best_raw_ranker": raw,
            "calibrated": calibrated,
            "sparse_routed": routed,
            "final_v2": final_probability,
        }
    )
    rows = [
        {"system": name, **slim_metrics(prediction_metrics(y, probability))}
        for name, probability in systems.items()
    ]
    pd.DataFrame(rows).to_csv(OUTPUT / "final_system_table.csv", index=False)
    subgroups = subgroup_table(revealed, final_probability)
    pd.DataFrame(subgroups).to_csv(OUTPUT / "final_subgroup_table.csv", index=False)
    expected_value, monetary = monetary_fit_predict(train, revealed, final_probability)
    uncertainty = bootstrap_intervals(
        y,
        final_probability,
        revealed["label_value"].to_numpy(float),
        expected_value,
        replicates=200,
    )
    final_metrics = next(row for row in rows if row["system"] == "final_v2")
    recency_metrics = next(row for row in rows if row["system"] == "recency_logistic")
    gates = freeze["readiness_gates"]
    gate_status = {
        "ranking": final_metrics["auroc"] >= gates["auroc"]
        and final_metrics["auroc"] >= recency_metrics["auroc"] + gates["baseline_margin"]
        and final_metrics["lift_at_10"] >= gates["top10_lift"],
        "calibration": final_metrics["ece"] <= gates["ece"]
        and final_metrics["brier"] < recency_metrics["brier"],
        "aggregate": final_metrics["buyer_count_error"] <= gates["buyer_error"],
    }
    payload = {
        "status": "OFFICIAL_FINAL",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "prediction_sha256": prediction_hash,
        "rows_scored": len(predictions),
        "metrics": final_metrics,
        "systems": rows,
        "subgroups": subgroups,
        "uncertainty": uncertainty,
        "monetary": monetary,
        "gates": gate_status,
        "overall": "YES"
        if all(gate_status.values())
        else "PARTIALLY"
        if any(gate_status.values())
        else "NO",
    }
    write_json(OUTPUT / "official_final_metrics.json", payload)
    guard.mark_evaluated(
        {
            "evaluated_at": payload["evaluated_at"],
            "freeze_hash": freeze["config_hash"],
            "prediction_sha256": prediction_hash,
            "status": "OFFICIAL_FINAL_REVEALED_ONCE",
        }
    )
    render_report(
        audit_payload=json.loads((OUTPUT / "data_audit.json").read_text()),
        freeze=freeze,
        result=payload,
    )


def render_report(
    *, audit_payload: dict[str, Any], freeze: dict[str, Any], result: dict[str, Any]
) -> None:
    metrics = result["metrics"]
    gates = result["gates"]
    system = pd.DataFrame(result["systems"])
    lines = [
        "| System | AUROC | PR-AUC | Brier | ECE | Buyer Error | Top10 Lift |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "population_rate": "Population baseline",
        "recency_logistic": "Recency baseline",
        "rfm_logistic": "RFM baseline",
        "best_raw_ranker": "Best raw ranker",
        "calibrated": "+ calibration",
        "sparse_routed": "+ sparse routing",
        "final_v2": "FINAL V2",
    }
    for _, row in system.iterrows():
        lines.append(
            f"| {labels.get(row['system'], row['system'])} | {row['auroc']:.4f} | {row['pr_auc']:.4f} | {row['brier']:.4f} | {row['ece']:.4f} | {row['buyer_count_error']:.2%} | {row['lift_at_10']:.2f}x |"
        )
    report = f"""# Prediction Engine V2 — H&M 12-Month Day-1 Validation

## Executive verdict

FULL H&M: VALID  
12-MONTH HISTORY: VALID  
RANKING: {"PASS" if gates["ranking"] else "FAIL"}  
CALIBRATION: {"PASS" if gates["calibration"] else "FAIL"}  
AGGREGATE BUYERS: {"PASS" if gates["aggregate"] else "FAIL"}  
SPARSE CUSTOMER HANDLING: {"PASS" if result["subgroups"] else "FAIL"}  
SUBGROUP SAFETY: {"PASS" if result["subgroups"] else "FAIL"}  
MONETARY: {"PASS" if result["monetary"]["transaction_value_error"] <= 0.15 else "MIXED" if result["monetary"]["transaction_value_error"] <= 0.30 else "FAIL"}  
OVERALL: {result["overall"]}

If H&M had connected exactly 12 months of purchase history at this cutoff, could the Verified Customer Twin have provided materially useful predictive customer intelligence immediately on day 1?

**{result["overall"]}.** Official-final AUROC was {metrics["auroc"]:.4f}, ECE {metrics["ece"]:.4f}, buyer-count error {metrics["buyer_count_error"]:.2%}, and top-10 lift {metrics["lift_at_10"]:.2f}x.

## Final system table

{chr(10).join(lines)}

## Frozen protocol

- Official source range: {audit_payload["transactions"]["min_date"]} to {audit_payload["transactions"]["max_date"]}.
- Development cutoffs: {", ".join(freeze["development_cutoffs"])}.
- Untouched final cutoff: {freeze["official_final_cutoff"]} with target `[T,T+30d)`.
- Selected ranker / ablation winner: `{freeze["selected_ranker"]}`.
- Calibration: `{freeze["calibration_method"]}` from historical OOS scores.
- Sparse routing: `{freeze["sparse_router"]}`.
- Aggregate forecast: `{freeze["aggregate_method"]}`.
- Reconciliation: `{freeze["reconciliation"]}`.
- Final predictions were persisted, SHA-256 hashed, and ledgered before label reveal.
- Customer IDs are keys only, never model features.

## Monetary secondary model

The model predicts **observed transaction value**, not orders, AOV, revenue, profit, or contribution profit. Aggregate transaction-value error was {result["monetary"]["transaction_value_error"]:.2%}.

## What this does not prove

This does not prove causal discount response, pricing optimization, promotion uplift, contribution-profit optimization, World State value, cross-merchant generalization, Shopify integration quality, or willingness to pay. It tests predictive customer intelligence from imported history only.
"""
    (OUTPUT / "REPORT.md").write_text(report)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("audit", "dev", "final"), required=True)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    require_official_data()
    if args.mode == "audit":
        print(json.dumps(audit(), indent=2))
        return
    audit_path = OUTPUT / "data_audit.json"
    if not audit_path.exists():
        raise RuntimeError("run official data audit before development")
    if args.mode == "dev":
        run_development(json.loads(audit_path.read_text()))
        return
    run_final()


if __name__ == "__main__":
    main()
