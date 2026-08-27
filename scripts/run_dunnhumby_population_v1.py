"""Long-horizon observational population replication on Complete Journey."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

from commercial_twin.research_v1 import BenchmarkAuthority, ResearchMode, expected_calibration_error
from decision_engine.ledger.store import PredictionLedger

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/processed/dunnhumby/complete-journey/transaction_data.parquet"
DATA = ROOT / "data/processed/dunnhumby/research_v1"
OUT = ROOT / "benchmarks/customer_twin_research_v1/dunnhumby"
HORIZONS = (7, 30, 60, 90)
SEED = 20260826


def sha(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8")


def materialize() -> None:
    frame = pd.read_parquet(SOURCE)
    frame["time"] = pd.to_datetime(frame.TRANSACTION_TIMESTAMP, utc=True)
    baskets = (
        frame.groupby(["HOUSEHOLD_KEY", "BASKET_ID"], as_index=False)
        .agg(time=("time", "min"), sales=("SALES_VALUE", "sum"), items=("PRODUCT_ID", "size"))
        .sort_values(["HOUSEHOLD_KEY", "time"])
    )
    DATA.mkdir(parents=True, exist_ok=True)
    for name, cutoff in (
        ("train", pd.Timestamp("2017-06-01", tz="UTC")),
        ("development", pd.Timestamp("2017-08-01", tz="UTC")),
        ("official_final", pd.Timestamp("2017-10-01", tz="UTC")),
    ):
        history = baskets[baskets.time < cutoff]
        grouped = history.groupby("HOUSEHOLD_KEY")
        features = grouped.agg(
            baskets=("BASKET_ID", "size"),
            sales=("sales", "sum"),
            items=("items", "sum"),
            first_time=("time", "min"),
            last_time=("time", "max"),
            mean_basket=("sales", "mean"),
        ).reset_index()
        features["recency_days"] = (cutoff - features.last_time).dt.total_seconds() / 86400
        features["history_days"] = (cutoff - features.first_time).dt.total_seconds() / 86400
        features["basket_rate"] = features.baskets / np.maximum(features.history_days, 1)
        features["cutoff"] = cutoff
        future = baskets[baskets.time >= cutoff]
        targets = pd.DataFrame({"HOUSEHOLD_KEY": features.HOUSEHOLD_KEY})
        for horizon in HORIZONS:
            count = (
                future[future.time < cutoff + pd.Timedelta(days=horizon)]
                .groupby("HOUSEHOLD_KEY")
                .size()
                .reindex(features.HOUSEHOLD_KEY, fill_value=0)
            )
            targets[f"basket_count_{horizon}d"] = count.to_numpy(int)
            targets[f"purchase_any_{horizon}d"] = (count.to_numpy(int) > 0).astype(int)
        features.drop(columns=["first_time", "last_time"]).to_parquet(
            DATA / f"{name}_features.parquet", index=False
        )
        targets.to_parquet(DATA / f"{name}_outcomes.parquet", index=False)


def run(mode: ResearchMode) -> None:
    authority = BenchmarkAuthority(mode)
    OUT.mkdir(parents=True, exist_ok=True)
    if not (DATA / "train_features.parquet").exists():
        materialize()
    train_f, train_o = (
        pd.read_parquet(DATA / "train_features.parquet"),
        pd.read_parquet(DATA / "train_outcomes.parquet"),
    )
    dev_f, dev_o = (
        pd.read_parquet(DATA / "development_features.parquet"),
        pd.read_parquet(DATA / "development_outcomes.parquet"),
    )
    features = [
        "baskets",
        "sales",
        "items",
        "mean_basket",
        "recency_days",
        "history_days",
        "basket_rate",
    ]
    models = {}
    for horizon in HORIZONS:
        models[horizon] = lgb.LGBMClassifier(
            n_estimators=100, num_leaves=15, random_state=SEED, verbosity=-1
        ).fit(train_f[features], train_o[f"purchase_any_{horizon}d"])
    dev_rows = []
    for horizon, model in models.items():
        p = model.predict_proba(dev_f[features])[:, 1]
        y = dev_o[f"purchase_any_{horizon}d"].to_numpy(int)
        dev_rows.append(
            {
                "horizon": horizon,
                "brier": brier_score_loss(y, p),
                "logloss": log_loss(y, p),
                "ece": expected_calibration_error(y, p),
                "buyer_error": abs(p.mean() - y.mean()) / y.mean(),
            }
        )
    pd.DataFrame(dev_rows).to_csv(OUT / "development_results.csv", index=False)
    if mode == ResearchMode.QUICK:
        write_json(
            OUT / "quick_validation.json", {"official_authority": False, "final_read": False}
        )
        return
    if mode == ResearchMode.DEVELOPMENT:
        write_json(
            OUT / "development_selection.json",
            {"model": "GBDT purchase-state", "official_read": False},
        )
        return
    authority.require_official("run dunnhumby official replication")
    marker = OUT / "official_reveal_marker.json"
    if marker.exists():
        raise RuntimeError("dunnhumby official already revealed")
    final_f = pd.read_parquet(DATA / "official_final_features.parquet")
    frozen = pd.DataFrame({"HOUSEHOLD_KEY": final_f.HOUSEHOLD_KEY})
    for horizon, model in models.items():
        frozen[f"purchase_probability_{horizon}d"] = model.predict_proba(final_f[features])[:, 1]
    freeze = {
        "model": "GBDT purchase-state",
        "horizons": HORIZONS,
        "seed": SEED,
        "causal": False,
        "promotion_fields_used": False,
        "source_sha256": sha(SOURCE),
    }
    write_json(OUT / "benchmark_freeze.json", freeze)
    prediction_path = OUT / "official_predictions.parquet"
    frozen.to_parquet(prediction_path, index=False)
    ledger = PredictionLedger(OUT / "prediction_ledger.duckdb")
    batch = "dunnhumby-research-v1:official"
    ledger.append_frozen_batch(
        batch_id=batch,
        dataset_name="Complete Journey",
        dataset_version=sha(SOURCE),
        split="OFFICIAL_2017-10-01",
        model_name=freeze["model"],
        row_count=len(frozen),
        predictions_path=str(prediction_path),
        predictions_sha256=sha(prediction_path),
        config=freeze,
        outcome_columns_hidden=tuple(f"purchase_any_{h}d" for h in HORIZONS),
    )
    write_json(marker, {"status": "REVEAL_INITIATED", "count": 1})
    final_o = pd.read_parquet(DATA / "official_final_outcomes.parquet")
    rows = []
    for horizon in HORIZONS:
        p, y = (
            frozen[f"purchase_probability_{horizon}d"].to_numpy(),
            final_o[f"purchase_any_{horizon}d"].to_numpy(int),
        )
        rows.append(
            {
                "horizon": horizon,
                "brier": brier_score_loss(y, p),
                "logloss": log_loss(y, p),
                "ece": expected_calibration_error(y, p),
                "buyer_error": abs(p.mean() - y.mean()) / y.mean(),
            }
        )
    pd.DataFrame(rows).to_csv(OUT / "official_results.csv", index=False)
    ledger.append_frozen_batch_evaluation(batch, {"results": rows})
    verdict = (
        "PASS"
        if all(
            row["buyer_error"] <= 0.10 and row["ece"] <= 0.03
            for row in rows
            if row["horizon"] in {30, 90}
        )
        else "FAIL"
    )
    write_json(
        OUT / "final_metrics.json",
        {"verdict": verdict, "results": rows, "observational_only": True},
    )
    write_json(
        marker,
        {
            "status": "REVEAL_COMPLETED",
            "count": 1,
            "metrics_sha256": sha(OUT / "final_metrics.json"),
        },
    )
    (OUT / "REPORT.md").write_text(
        "# Complete Journey long-horizon replication\n\n"
        f"Verdict: **{verdict}**. This is observational natural-purchase "
        "prediction, not campaign causality.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=[mode.value for mode in ResearchMode])
    run(ResearchMode(parser.parse_args().mode))
