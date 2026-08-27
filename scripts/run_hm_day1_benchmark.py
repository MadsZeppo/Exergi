#!/usr/bin/env python3
# ruff: noqa: E501
"""Run the H&M merchant day-1 readiness benchmark in dev or final mode."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from commercial_twin.hm_day1 import (  # noqa: E402
    FEATURE_COLUMNS,
    HISTORY_MONTHS,
    LABEL_COLUMNS,
    RANDOM_SEED,
    HMPaths,
    HMWindow,
    ProbabilityCalibrator,
    assert_state_is_leak_safe,
    audit_hm_data,
    bootstrap_intervals,
    build_state_frame,
    choose_cutoffs,
    file_sha256,
    fit_candidate,
    prediction_metrics,
    readiness_verdict,
    select_model,
    split_training_snapshots,
    stable_hash,
    subgroup_metrics,
)
from decision_engine.ledger import PredictionLedger  # noqa: E402

OUTPUT = ROOT / "benchmarks" / "hm_day1"
CACHE = ROOT / "data" / "raw" / "relbench-cache" / "rel-hm" / "db"
PATHS = HMPaths(
    transactions=CACHE / "transactions.parquet",
    customers=CACHE / "customer.parquet",
    articles=CACHE / "article.parquet",
)
MODELS = (
    "population_rate",
    "recency_logistic",
    "rfm_logistic",
    "empirical_bayes_lifecycle",
    "logistic",
    "gradient_boosting",
)
CALIBRATIONS = ("none", "platt", "isotonic")
TRAINING_OFFSETS = (120, 90, 60, 30)
TRAIN_SAMPLE_MODULUS = 4


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=None)


def ensure_data() -> None:
    missing = [str(path) for path in PATHS.__dict__.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "rel-hm data missing. Expected RelBench Parquet files: " + ", ".join(missing)
        )


def prepare_training_frames(cutoff: datetime, history_start: datetime) -> list[pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    for offset in TRAINING_OFFSETS:
        snapshot = cutoff - timedelta(days=offset)
        frame = build_state_frame(
            PATHS,
            history_start=history_start,
            as_of=snapshot,
            include_labels=True,
            sample_modulus=TRAIN_SAMPLE_MODULUS,
        )
        assert_state_is_leak_safe(frame, history_start=history_start, as_of=snapshot)
        frame["snapshot"] = snapshot.date().isoformat()
        frames.append(frame)
    return frames


def run_development(audit: dict[str, Any], cutoffs: dict[str, Any]) -> None:
    started = time.perf_counter()
    data_min = dt(audit["transactions"]["min_date"])
    data_max = dt(audit["transactions"]["max_date"])
    result_rows: list[dict[str, Any]] = []
    feasibility: dict[str, Any] = {}
    for months in HISTORY_MONTHS:
        history_rows = []
        for cutoff_text in cutoffs["development"]:
            cutoff = dt(cutoff_text)
            window = HMWindow(cutoff, months, data_min, data_max)
            try:
                window.validate()
            except ValueError as error:
                history_rows.append({"cutoff": cutoff_text, "status": "NOT_EVALUABLE", "reason": str(error)})
                continue
            training_frames = prepare_training_frames(cutoff, window.history_start)
            train, calibration = split_training_snapshots(training_frames)
            evaluation = build_state_frame(
                PATHS, history_start=window.history_start, as_of=cutoff,
                include_labels=True,
            )
            assert_state_is_leak_safe(evaluation, history_start=window.history_start, as_of=cutoff)
            y_cal = calibration["label_repeat"].to_numpy(int)
            y_eval = evaluation["label_repeat"].to_numpy(int)
            for model_name in MODELS:
                model = fit_candidate(model_name, train)
                raw_cal = model.predict_proba(calibration)
                raw_eval = model.predict_proba(evaluation)
                for calibration_name in CALIBRATIONS:
                    calibrator = ProbabilityCalibrator(calibration_name).fit(raw_cal, y_cal)
                    probability = calibrator.transform(raw_eval)
                    metrics = prediction_metrics(y_eval, probability)
                    result_rows.append(
                        {
                            "history_months": months,
                            "cutoff": cutoff_text,
                            "eligible_customers": len(evaluation),
                            "model": model_name,
                            "calibration": calibration_name,
                            **{key: value for key, value in metrics.items() if not isinstance(value, list)},
                        }
                    )
            history_rows.append({"cutoff": cutoff_text, "status": "EVALUATED"})
        feasibility[str(months)] = history_rows
    results = pd.DataFrame(result_rows)
    results.to_csv(OUTPUT / "development_results.csv", index=False)
    selections: dict[str, Any] = {}
    tournament_rows: list[dict[str, Any]] = []
    for months in HISTORY_MONTHS:
        subset = results[results["history_months"] == months]
        if subset.empty:
            selections[str(months)] = {
                "status": "NOT_EVALUABLE",
                "reason": "RelBench coverage cannot supply this imported history plus full futures",
            }
            continue
        selection = select_model(subset)
        selection["status"] = "FROZEN_FROM_DEVELOPMENT"
        selections[str(months)] = selection
        aggregate = subset.groupby(["model", "calibration"], as_index=False).agg(
            mean_auroc=("auroc", "mean"), std_auroc=("auroc", "std"),
            mean_pr_auc=("pr_auc", "mean"), mean_brier=("brier", "mean"),
            mean_ece=("ece", "mean"), mean_buyer_error=("buyer_count_error", "mean"),
            mean_top10_lift=("lift_at_10", "mean"), windows=("cutoff", "nunique"),
        )
        tournament_rows.extend(
            {"history_months": months, **row} for row in aggregate.to_dict("records")
        )
    pd.DataFrame(tournament_rows).to_csv(OUTPUT / "model_tournament.csv", index=False)
    freeze = {
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": "NOT_AVAILABLE_NOT_A_GIT_WORKTREE",
        "dataset": {
            "source": audit["source"],
            "transactions_sha256": audit["files"]["transactions"]["sha256"],
            "rows": audit["transactions"]["rows"],
            "min_date": audit["transactions"]["min_date"],
            "max_date": audit["transactions"]["max_date"],
        },
        "cutoffs": cutoffs,
        "history_months": list(HISTORY_MONTHS),
        "horizon_days": 30,
        "feature_columns": list(FEATURE_COLUMNS),
        "feature_schema_hash": stable_hash(FEATURE_COLUMNS),
        "models_compared": list(MODELS),
        "calibrations_compared": list(CALIBRATIONS),
        "training_snapshot_offsets_days": list(TRAINING_OFFSETS),
        "training_sample": "deterministic hash quarter; evaluation populations are full",
        "random_seed": RANDOM_SEED,
        "selection_rule": (
            "reject mean ECE>0.05 and repeated buyer error>20%; among eligible choose "
            "lowest mean Brier, then buyer error, then AUROC"
        ),
        "selections": selections,
        "feasibility": feasibility,
        "development_runtime_seconds": time.perf_counter() - started,
        "final_labels_accessed": False,
        "test_metrics_used_for_selection": False,
    }
    freeze["config_hash"] = stable_hash(freeze)
    write_json(OUTPUT / "benchmark_freeze.json", freeze)
    print(json.dumps({"mode": "dev", "selections": selections}, indent=2))


def fit_value_model(train: pd.DataFrame) -> HistGradientBoostingRegressor:
    buyers = train[train["label_repeat"] == 1]
    return HistGradientBoostingRegressor(
        loss="absolute_error", max_iter=80, max_leaf_nodes=15, random_state=RANDOM_SEED
    ).fit(buyers[list(FEATURE_COLUMNS)].fillna(0), buyers["label_value"])


def render_report(final_rows: list[dict[str, Any]], audit: dict[str, Any], freeze: dict[str, Any]) -> None:
    by_month = {int(row["history_months"]): row for row in final_rows}
    table = []
    for months in HISTORY_MONTHS:
        row = by_month.get(months)
        if row is None:
            table.append(f"| {months}m | NOT EVALUABLE | — | — | — | — | — | — | — | — | NOT EVALUABLE |")
        else:
            table.append(
                f"| {months}m | {row['auroc']:.4f} | {row['pr_auc']:.4f} | {row['brier']:.4f} | "
                f"{row['ece']:.4f} | {row['repeat_buyers_predicted']:.1f} | "
                f"{row['repeat_buyers_actual']} | {row['buyer_count_error']:.1%} | "
                f"{row['lift_at_10']:.2f}x | {row['transaction_value_error']:.1%} | {row['verdict']} |"
            )
    twelve = by_month.get(12)
    answer = "NO"
    if twelve is not None and twelve["verdict"] == "STRONG":
        answer = "YES"
    elif twelve is not None and twelve["verdict"] == "PROMISING":
        answer = "PARTIALLY"
    report = f"""# H&M Merchant Day-1 Readiness Benchmark

## Executive verdict

**DAY-1 CUSTOMER STATE:** PASS for the RelBench schema and leak-safe state construction  
**12-MONTH REPEAT PREDICTION:** NOT EVALUABLE — fallback history is too short  
**CALIBRATION:** See final 6m/9m results below  
**AGGREGATE BUYER FORECAST:** See final 6m/9m results below  
**MONETARY FORECAST:** Transaction value only; economics NOT VALIDATED  
**COHORT SIGNAL:** Predictive/descriptive only  
**OVERALL DAY-1 READINESS:** {answer} — the exact 12-month thesis is not identified by this fallback

> If a new large ecommerce merchant gave us exactly 12 months of purchase history today, does
> H&M support materially useful predictive customer intelligence on day 1?

**{answer}.** The benchmark produces real evidence for shorter histories, but RelBench `rel-hm`
contains transactions only from {audit['transactions']['min_date']} through
{audit['transactions']['max_date']}. It cannot supply 12 months of imported history plus a full
untouched 30-day future. A 12m number would therefore be fabricated.

## Final headline table

| History | AUROC | PR-AUC | Brier | ECE | Repeat Buyers Pred | Repeat Buyers Actual | Buyer Error | Top10 Lift | Tx Value Error | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(table)}

## Dataset

- Source: Stanford RelBench `rel-hm` fallback, derived from the H&M Kaggle competition data.
- It is **not byte-identical to the full Kaggle source**.
- Transaction lines: {audit['transactions']['rows']:,}.
- Customers in transactions: {audit['transactions']['unique_customers']:,}.
- Articles in transactions: {audit['transactions']['unique_articles']:,}.
- No true order/invoice identifier exists; no order count or AOV is reported.
- `price` is called observed transaction value in dataset units, never profit or contribution profit.
- Country/market validation: NOT AVAILABLE.

## Freeze and leakage status

- Development cutoffs: {', '.join(freeze['cutoffs']['development'])}.
- Final cutoff: {freeze['cutoffs']['final']}.
- Target horizon: `[T, T+30d)`.
- Features use only `[T-H, T)` and historical training snapshots whose labels end by T.
- Model/calibration selections were serialized before final labels were read.
- Full final predictions were written and hashed in the Prediction Ledger before reveal.
- Customer identifiers are keys only and are excluded from model features.
- Future-acquired customers are excluded from the known-customer repeat task.

## What the Twin can honestly say on day 1

- Build a point-in-time customer state for known customers.
- Describe lifecycle, activity depth, cadence, product diversity and channel behavior.
- Estimate next-30-day repeat propensity and aggregate expected repeat buyers for evaluated histories.
- Rank known customers by repeat propensity.
- Quantify calibration and subgroup failures.
- Produce descriptive/predictive opportunity signals.

## What it cannot honestly say

- It cannot identify future new customers individually.
- It cannot call transaction lines orders or compute true AOV.
- It cannot infer profit, contribution profit, COGS or campaign cost.
- It cannot recommend discounts or claim causal treatment effects.
- It cannot establish country-specific performance because geography is unavailable.
- It cannot prove Shopify/Klaviyo onboarding, World State value, cross-merchant transfer or willingness to pay.
- This fallback cannot answer the exact 12-month learning-curve point.

## H&M can and cannot prove

H&M tests state construction, repeat prediction, ranking, probability calibration, aggregate
repeat-buyer calibration, lifecycle heterogeneity, transaction-value prediction and large-data
scalability. It does not validate causal actions, pricing, economic optimization, merchant transfer,
integrations, World State, experiments, geography, or profit.

## Comparison with Customer Twin V1

The prior Online Retail II run selected logistic regression on development, then achieved final
AUROC 0.784, Brier 0.1537 and ECE 0.0535, but buyer-count error remained 19.45%; its status was
`RANKING_ONLY`. H&M comparisons use the same conceptual 30-day repeat task but a different dataset,
eligible population and transaction semantics, so only directional comparison is valid.

## Highest-information next experiment

Acquire the official full H&M transaction/customer/article files under accepted Kaggle terms and
rerun the already frozen 6m/9m/12m protocol, or use a second merchant-like dataset with at least
13 months of coverage. Do not build Customer Population V4 first.
"""
    (OUTPUT / "REPORT.md").write_text(report)


def run_final(*, diagnostic_override: bool) -> None:
    freeze_path = OUTPUT / "benchmark_freeze.json"
    marker = OUTPUT / "official_final_evaluated.json"
    if not freeze_path.exists():
        raise RuntimeError("development freeze is missing; run --mode dev first")
    if marker.exists() and not diagnostic_override:
        raise RuntimeError(
            "official final already evaluated; refusing second reveal. Use --diagnostic-override "
            "only for explicitly labelled diagnostics"
        )
    freeze = json.loads(freeze_path.read_text())
    audit = json.loads((OUTPUT / "data_audit.json").read_text())
    cutoff = dt(freeze["cutoffs"]["final"])
    data_min = dt(audit["transactions"]["min_date"])
    data_max = dt(audit["transactions"]["max_date"])
    final_rows: list[dict[str, Any]] = []
    subgroup_rows: list[dict[str, Any]] = []
    ledger = PredictionLedger(OUTPUT / "prediction_ledger.duckdb")
    started = time.perf_counter()
    for months in HISTORY_MONTHS:
        selection = freeze["selections"][str(months)]
        if selection["status"] == "NOT_EVALUABLE":
            continue
        window = HMWindow(cutoff, months, data_min, data_max)
        window.validate()
        training_frames = prepare_training_frames(cutoff, window.history_start)
        train, calibration = split_training_snapshots(training_frames)
        model = fit_candidate(selection["model"], train)
        calibrator = ProbabilityCalibrator(selection["calibration"]).fit(
            model.predict_proba(calibration), calibration["label_repeat"].to_numpy(int)
        )
        # First score without reading final labels.
        scoring = build_state_frame(
            PATHS, history_start=window.history_start, as_of=cutoff, include_labels=False,
        )
        assert_state_is_leak_safe(scoring, history_start=window.history_start, as_of=cutoff)
        probability = calibrator.transform(model.predict_proba(scoring))
        value_model = fit_value_model(train)
        conditional_value = np.maximum(
            value_model.predict(scoring[list(FEATURE_COLUMNS)].fillna(0)), 0
        )
        expected_value = probability * conditional_value
        predictions = pd.DataFrame(
            {
                "customer_id": scoring["customer_id"].astype("Int64"),
                "as_of": cutoff,
                "history_months": months,
                "probability_repeat_30d": probability,
                "conditional_transaction_value_if_repeat": conditional_value,
                "expected_transaction_value": expected_value,
                "lifecycle": scoring["lifecycle"],
            }
        )
        prediction_path = OUTPUT / f"final_predictions_{months}m.parquet"
        predictions.to_parquet(prediction_path, index=False)
        batch_id = f"hm-day1-final-{months}m"
        ledger.append_frozen_batch(
            batch_id=batch_id,
            dataset_name="relbench-rel-hm",
            dataset_version=audit["files"]["transactions"]["sha256"],
            split="final_untouched",
            model_name=selection["model"],
            row_count=len(predictions),
            predictions_path=str(prediction_path),
            predictions_sha256=file_sha256(prediction_path),
            config={"freeze_hash": freeze["config_hash"], "history_months": months},
            outcome_columns_hidden=LABEL_COLUMNS,
        )
        # Reveal only after prediction persistence and ledger append.
        revealed = build_state_frame(
            PATHS, history_start=window.history_start, as_of=cutoff, include_labels=True,
        )
        if not np.array_equal(scoring["customer_id"].to_numpy(), revealed["customer_id"].to_numpy()):
            raise AssertionError("eligible population changed during reveal")
        y = revealed["label_repeat"].to_numpy(int)
        metrics = prediction_metrics(y, probability)
        actual_value = revealed["label_value"].to_numpy(float)
        value_error = abs(float(expected_value.sum()) - float(actual_value.sum())) / max(
            float(actual_value.sum()), 1e-12
        )
        baseline_model = fit_candidate("population_rate", train)
        baseline_probability = baseline_model.predict_proba(revealed)
        baseline_metrics = prediction_metrics(y, baseline_probability)
        verdict = readiness_verdict(metrics, baseline_metrics)
        row = {
            "history_months": months,
            "cutoff": cutoff.date().isoformat(),
            "eligible_customers": len(revealed),
            "selected_model": selection["model"],
            "calibration": selection["calibration"],
            **{key: value for key, value in metrics.items() if not isinstance(value, list)},
            "transaction_value_predicted": float(expected_value.sum()),
            "transaction_value_actual": float(actual_value.sum()),
            "transaction_value_error": float(value_error),
            "baseline_auroc": baseline_metrics["auroc"],
            "baseline_brier": baseline_metrics["brier"],
            "verdict": verdict,
            "uncertainty": bootstrap_intervals(
                y, probability, actual_value, expected_value, replicates=100,
            ),
        }
        final_rows.append(row)
        subgroup_rows.extend(
            {"history_months": months, **item}
            for item in subgroup_metrics(revealed, probability)
        )
        ledger.append_frozen_batch_evaluation(batch_id, row)
        write_json(OUTPUT / f"calibration_{months}m.json", metrics["deciles"])
    ledger.close()
    pd.DataFrame(final_rows).to_csv(OUTPUT / "history_learning_curve.csv", index=False)
    pd.DataFrame(subgroup_rows).to_csv(OUTPUT / "subgroup_results.csv", index=False)
    final_summary = {
        "status": "DIAGNOSTIC_OVERRIDE" if diagnostic_override else "OFFICIAL_FINAL",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "freeze_hash": freeze["config_hash"],
        "runtime_seconds": time.perf_counter() - started,
        "results": final_rows,
        "twelve_month_status": "NOT_EVALUABLE_DATA_COVERAGE",
        "overall_answer": "NO",
    }
    write_json(OUTPUT / "final_metrics.json", final_summary)
    if not diagnostic_override:
        write_json(marker, {"evaluated_at": final_summary["evaluated_at"], "freeze_hash": freeze["config_hash"]})
    render_report(final_rows, audit, freeze)
    print(json.dumps(final_summary, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("audit", "dev", "final"), required=True)
    parser.add_argument("--diagnostic-override", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ensure_data()
    if args.mode == "audit":
        audit = audit_hm_data(PATHS)
        data_min = dt(audit["transactions"]["min_date"])
        data_max = dt(audit["transactions"]["max_date"])
        cutoffs = choose_cutoffs(data_min, data_max)
        write_json(OUTPUT / "data_audit.json", audit)
        write_json(OUTPUT / "cutoffs.json", cutoffs)
        write_json(
            OUTPUT / "feature_schema.json",
            {"features": list(FEATURE_COLUMNS), "hash": stable_hash(FEATURE_COLUMNS)},
        )
        print(json.dumps({"audit": audit, "cutoffs": cutoffs}, indent=2))
    elif args.mode == "dev":
        audit = json.loads((OUTPUT / "data_audit.json").read_text())
        cutoffs = json.loads((OUTPUT / "cutoffs.json").read_text())
        run_development(audit, cutoffs)
    else:
        run_final(diagnostic_override=args.diagnostic_override)


if __name__ == "__main__":
    main()
