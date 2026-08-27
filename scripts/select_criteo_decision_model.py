from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from decision_engine.benchmark.criteo_uplift import (
    _score_order,
    masked_policy_value,
    uplift_bin_assignments,
    uplift_calibration,
    uplift_ranking_metrics,
)
from decision_engine.datasets.criteo_uplift import CriteoUpliftAdapter
from decision_engine.decision.model_selection import (
    DevelopmentCandidate,
    DevelopmentSelectionConfig,
    GateBenchmark,
    promote_customer_facing_gate,
    select_development_model,
)
from decision_engine.registry import ModelPerformanceRegistry


def _top_fraction(score: np.ndarray, fraction: float) -> np.ndarray:
    targeted = np.zeros(len(score), dtype=bool)
    order = _score_order(score, descending=True)
    targeted[order[: int(round(len(score) * fraction))]] = True
    return targeted


def _calibration_error(y: np.ndarray, t: np.ndarray, score: np.ndarray) -> float:
    return float(
        np.mean(
            [
                abs(row["predicted_uplift"] - row["observed_uplift"])
                for row in uplift_calibration(y, t, score)
            ]
        )
    )


def _gate_benchmark(
    y: np.ndarray,
    t: np.ndarray,
    selected_score: np.ndarray,
    simple_score: np.ndarray,
    gated: np.ndarray,
    propensity: float,
) -> GateBenchmark:
    return GateBenchmark(
        gated_policy_value=masked_policy_value(y, t, gated, propensity)["policy_value"],
        ungated_policy_value=masked_policy_value(y, t, selected_score > 0, propensity)[
            "policy_value"
        ],
        simple_targeting_value=masked_policy_value(
            y, t, _top_fraction(simple_score, 0.20), propensity
        )["policy_value"],
        treat_all_value=masked_policy_value(y, t, np.ones(len(y), dtype=bool), propensity)[
            "policy_value"
        ],
        treat_none_value=masked_policy_value(y, t, np.zeros(len(y), dtype=bool), propensity)[
            "policy_value"
        ],
    )


def select_criteo_model(
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
    y_dev = development["conversion"].to_numpy().astype(int)
    t_dev = development["treatment"].to_numpy().astype(int)
    propensity = 0.85
    prediction_paths = sorted(target.glob("frozen_*_development.parquet"))
    candidates: list[DevelopmentCandidate] = []
    scores: dict[str, np.ndarray] = {}
    for path in prediction_paths:
        name = path.name.removeprefix("frozen_").removesuffix("_development.parquet")
        prediction = pl.read_parquet(path)
        if not prediction["row_id"].equals(development["row_id"]):
            raise ValueError(f"development alignment failed for {name}")
        score = prediction["uplift"].to_numpy()
        scores[name] = score
        candidates.append(
            DevelopmentCandidate(
                model_name=name,
                policy_value=masked_policy_value(
                    y_dev, t_dev, _top_fraction(score, 0.20), propensity
                )["policy_value"],
                calibration_error=_calibration_error(y_dev, t_dev, score),
                policy_name="TOP_20_PERCENT_CAPACITY",
            )
        )
    selection = select_development_model(
        tuple(candidates),
        DevelopmentSelectionConfig(
            decision_type="binary_ad_targeting",
            calibration_tolerance=0.00025,
        ),
    )
    selected_score_dev = scores[selection.selected_model]
    dev_calibration = uplift_calibration(y_dev, t_dev, selected_score_dev)
    act_bins = {
        int(row["bin"])
        for row in dev_calibration
        if row["predicted_uplift"] > 0 and row["lower_90"] > 0
    }
    dev_bins = uplift_bin_assignments(selected_score_dev)
    dev_gated = np.isin(dev_bins, list(act_bins))
    simple_dev = scores["outcome_propensity"]
    development_gate = _gate_benchmark(
        y_dev,
        t_dev,
        selected_score_dev,
        simple_dev,
        dev_gated,
        propensity,
    )

    # Selection is now frozen. Test outcomes enter only below this point.
    test = (
        CriteoUpliftAdapter.split(pl.scan_parquet(parquet), "test")
        .select("row_id", "treatment", "conversion")
        .collect()
    )
    y_test = test["conversion"].to_numpy().astype(int)
    t_test = test["treatment"].to_numpy().astype(int)
    selected_test_prediction = pl.read_parquet(
        target / f"frozen_{selection.selected_model}_test.parquet"
    )
    simple_test_prediction = pl.read_parquet(target / "frozen_outcome_propensity_test.parquet")
    selected_score_test = selected_test_prediction["uplift"].to_numpy()
    test_bins = uplift_bin_assignments(selected_score_test)
    test_gated = np.isin(test_bins, list(act_bins))
    final_gate = _gate_benchmark(
        y_test,
        t_test,
        selected_score_test,
        simple_test_prediction["uplift"].to_numpy(),
        test_gated,
        propensity,
    )
    gate = promote_customer_facing_gate("binary_ad_targeting", development_gate, final_gate)
    ranking = uplift_ranking_metrics(y_test, t_test, selected_score_test, propensity)
    final_result = {
        **ranking,
        "calibration_error": _calibration_error(y_test, t_test, selected_score_test),
        "top_20_policy_value": masked_policy_value(
            y_test, t_test, _top_fraction(selected_score_test, 0.20), propensity
        )["policy_value"],
    }
    selection_path = target / "development_model_selection.json"
    payload: dict[str, Any] = {
        "selection": selection.model_dump(mode="json"),
        "selected_model_final_result": final_result,
        "customer_facing_gate": gate.model_dump(mode="json"),
        "freeze_boundary": "selection serialized before final-test outcome evaluation",
    }
    selection_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    product_view = {
        "label": "RESEARCH BENCHMARK — CRITEO IS NOT A CUSTOMER",
        "decision_type": "binary_ad_targeting",
        "empirically_selected_model": selection.selected_model,
        "customer_facing_decision": (
            "DO THIS" if gate.customer_facing_do_this_enabled else "TEST THIS"
        ),
        "do_this_enabled": gate.customer_facing_do_this_enabled,
        "internal_labels_available": list(gate.internal_labels_enabled),
        "reason": gate.reason,
    }
    (target / "selected_model_product_view.json").write_text(
        json.dumps(product_view, indent=2), encoding="utf-8"
    )
    registry = ModelPerformanceRegistry(target / "model_registry.duckdb")
    registry.set_decision_model_default(
        decision_type="binary_ad_targeting",
        model=selection.selected_model,
        selection_artifact=str(selection_path),
        customer_facing_do_this_enabled=gate.customer_facing_do_this_enabled,
    )
    registry.close()
    return payload


if __name__ == "__main__":
    print(select_criteo_model())
