from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from decision_engine.benchmark.criteo_uplift import (
    masked_policy_value,
    policy_table,
    uplift_bin_assignments,
    uplift_calibration,
)
from decision_engine.datasets.criteo_uplift import CriteoUpliftAdapter


def finalize(
    root: str | Path = "artifacts/benchmarks/criteo/definitive-seed-42-v2",
    parquet_path: str | Path = "data/processed/criteo/criteo-uplift-v2.1.parquet",
) -> dict[str, Any]:
    target = Path(root)
    parquet = Path(parquet_path)
    development = (
        CriteoUpliftAdapter.split(pl.scan_parquet(parquet), "development")
        .select("row_id", "treatment", "conversion")
        .collect()
    )
    test = (
        CriteoUpliftAdapter.split(pl.scan_parquet(parquet), "test")
        .select("row_id", "treatment", "conversion")
        .collect()
    )
    dev_prediction = pl.read_parquet(target / "frozen_commercial_twin_dr_development.parquet")
    test_prediction = pl.read_parquet(target / "frozen_commercial_twin_dr_test.parquet")
    if not dev_prediction["row_id"].equals(development["row_id"]):
        raise ValueError("development predictions do not align with frozen outcomes")
    if not test_prediction["row_id"].equals(test["row_id"]):
        raise ValueError("test predictions do not align with frozen outcomes")
    y_dev = development["conversion"].to_numpy().astype(int)
    t_dev = development["treatment"].to_numpy().astype(int)
    y_test = test["conversion"].to_numpy().astype(int)
    t_test = test["treatment"].to_numpy().astype(int)
    dev_score = dev_prediction["uplift"].to_numpy()
    test_score = test_prediction["uplift"].to_numpy()
    # The randomized design probability is known; do not fit or re-estimate a propensity model.
    propensity = 0.85
    dev_calibration = uplift_calibration(y_dev, t_dev, dev_score)
    test_calibration = uplift_calibration(y_test, t_test, test_score)
    act_bins = {
        int(row["bin"])
        for row in dev_calibration
        if row["predicted_uplift"] > 0 and row["lower_90"] > 0
    }
    experiment_bins = {
        int(row["bin"])
        for row in dev_calibration
        if row["predicted_uplift"] > 0 and int(row["bin"]) not in act_bins
    }
    abstain_bins = set(range(1, 11)) - act_bins - experiment_bins
    test_bins = uplift_bin_assignments(test_score)
    gated = np.isin(test_bins, list(act_bins))
    ungated = test_score > 0
    all_treated = np.ones(len(test_score), dtype=bool)
    none_treated = np.zeros(len(test_score), dtype=bool)
    comparison = {
        "ungated_positive": masked_policy_value(y_test, t_test, ungated, propensity),
        "gated_act": masked_policy_value(y_test, t_test, gated, propensity),
        "treat_all": masked_policy_value(y_test, t_test, all_treated, propensity),
        "treat_none": masked_policy_value(y_test, t_test, none_treated, propensity),
    }
    best_value = max(row["policy_value"] for row in comparison.values())
    for row in comparison.values():
        row["regret_vs_best_compared"] = best_value - row["policy_value"]
        row["incremental_conversions_vs_none"] = (
            row["policy_value"] - comparison["treat_none"]["policy_value"]
        ) * len(test_score)
    incorrect_confident_bins = [
        int(row["bin"])
        for row in test_calibration
        if int(row["bin"]) in act_bins and row["observed_uplift"] <= 0
    ]
    disposition = {
        "DO_THIS": int(np.sum(np.isin(test_bins, list(act_bins)))),
        "TEST_THIS": int(np.sum(np.isin(test_bins, list(experiment_bins)))),
        "NOT_ENOUGH_EVIDENCE": int(np.sum(np.isin(test_bins, list(abstain_bins)))),
    }
    top = test_calibration[-1]
    top_positions = test_bins == 10
    top_p0 = float(np.mean(test_prediction["p_control"].to_numpy()[top_positions]))
    top_p1 = float(np.mean(test_prediction["p_treatment"].to_numpy()[top_positions]))
    product_view = {
        "label": "RESEARCH BENCHMARK — CRITEO IS NOT A CUSTOMER",
        "customer_segment": "top predicted uplift decile; anonymized features",
        "twin_estimate": {
            "no_campaign_conversion": top_p0,
            "campaign_conversion": top_p1,
            "incremental_response": top_p1 - top_p0,
        },
        "randomized_validation": {
            "observed_incremental_response": top["observed_uplift"],
            "lower_90": top["lower_90"],
            "upper_90": top["upper_90"],
        },
        "decision": "DO THIS" if 10 in act_bins else "TEST THIS",
        "evidence": "held-out randomized population-level validation",
        "warning": "not an individual counterfactual or customer deployment claim",
    }
    payload: dict[str, Any] = {
        "development_act_bins": sorted(act_bins),
        "development_experiment_bins": sorted(experiment_bins),
        "development_abstain_bins": sorted(abstain_bins),
        "test_dispositions": disposition,
        "incorrect_confident_bins": incorrect_confident_bins,
        "comparison": comparison,
        "conclusion": (
            "gating adds value"
            if comparison["gated_act"]["policy_value"]
            > comparison["ungated_positive"]["policy_value"]
            else "gating does not add value"
        ),
    }
    (target / "gating_comparison.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (target / "research_product_view.json").write_text(
        json.dumps(product_view, indent=2), encoding="utf-8"
    )
    # A compact table for policy comparisons, including random targeting at each budget.
    commercial = policy_table(
        y_test, t_test, test_score, (0.05, 0.10, 0.20, 0.30, 0.50, 1.0), propensity
    )
    pl.DataFrame(commercial).write_parquet(target / "commercial_twin_policy_curve.parquet")
    return {"gating": payload, "product_view": product_view}


if __name__ == "__main__":
    print(finalize())
