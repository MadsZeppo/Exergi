from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from commercial_twin.customer_twin_core import EvidenceBoundAnswerRenderer, EvidenceType
from decision_engine.causal.layer3_validation import cross_fitted_aipw, generate_synthetic_uplift
from decision_engine.ledger.store import PredictionLedger

OUTPUT = Path("artifacts/layer3_validation/synthetic")
SEEDS = range(100)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ledger = PredictionLedger(OUTPUT / "prediction_ledger.duckdb")
    renderer = EvidenceBoundAnswerRenderer()
    rows: list[dict[str, object]] = []
    for scenario in ("randomized", "confounded", "placebo"):
        evidence = (
            EvidenceType.CAUSAL_OBSERVATIONAL
            if scenario == "confounded"
            else EvidenceType.CAUSAL_RCT
        )
        for seed in SEEDS:
            data = generate_synthetic_uplift(seed=seed, scenario=scenario)
            estimate = cross_fitted_aipw(
                data.features,
                data.treatment,
                data.outcome,
                data.segment,
                seed=seed,
            )
            query_id = f"synthetic-{scenario}-{seed}"
            ledger.append_twin_query(
                query_id=query_id,
                as_of=datetime(2026, 1, 1, tzinfo=UTC),
                query_plan={"intent": "CAUSAL", "metric": "purchase_uplift", "scenario": scenario},
                snapshot_version=f"synthetic-v1-seed-{seed}",
                model_version="cross-fitted-aipw-logistic-v1",
                answer_distribution={
                    "ate": estimate.ate,
                    "lower": estimate.lower,
                    "upper": estimate.upper,
                    "standard_error": estimate.standard_error,
                },
                evidence_type=evidence.value,
                validation_status="FROZEN_BEFORE_ORACLE_EVALUATION",
                predicted_incremental_effect={"purchase_probability": estimate.ate},
                decision_state="INTERNAL_VALIDATION_ONLY",
            )
            # Oracle values are accessed only after the estimate has been frozen above.
            truth = float(data.true_effect.mean())
            segment_truth = {
                int(value): float(data.true_effect[data.segment == value].mean())
                for value in np.unique(data.segment)
            }
            segment_errors = {
                value: estimate.segment_effects[value] - segment_truth[value]
                for value in segment_truth
            }
            covered = estimate.lower <= truth <= estimate.upper
            significant = not (estimate.lower <= 0 <= estimate.upper)
            ledger.append_twin_query_outcome(
                query_id,
                realized_outcome={"oracle_ate": truth, "oracle_segment_effects": segment_truth},
                calibration_update={"bias": estimate.ate - truth, "covered": covered},
            )
            rows.append(
                {
                    "scenario": scenario,
                    "seed": seed,
                    "true_ate": truth,
                    "adjusted_ate": estimate.ate,
                    "naive_ate": estimate.naive_ate,
                    "lower": estimate.lower,
                    "upper": estimate.upper,
                    "covered": covered,
                    "significant": significant,
                    "segment_errors": segment_errors,
                    "cate_rmse": float(
                        np.sqrt(np.mean(np.square(estimate.individual_effect - data.true_effect)))
                    ),
                    "fraction_clipped": estimate.fraction_clipped,
                    "overlap_fraction": estimate.overlap_fraction,
                    "treated_ess": estimate.treated_ess,
                    "control_ess": estimate.control_ess,
                    "evidence_type": evidence.value,
                    "rendered_answer": renderer.render_statement(
                        evidence, f"the offer changed purchase probability by {estimate.ate:.3f}"
                    ),
                }
            )
    ledger.close()
    scenarios: dict[str, dict[str, object]] = {}
    for scenario in ("randomized", "confounded", "placebo"):
        selected = [row for row in rows if row["scenario"] == scenario]
        adjusted_error = np.array(
            [float(row["adjusted_ate"]) - float(row["true_ate"]) for row in selected]
        )
        naive_error = np.array(
            [float(row["naive_ate"]) - float(row["true_ate"]) for row in selected]
        )
        segment_absolute = [
            abs(float(error)) for row in selected for error in dict(row["segment_errors"]).values()
        ]
        scenarios[scenario] = {
            "valid_seeds": len(selected),
            "true_ate_mean": float(np.mean([row["true_ate"] for row in selected])),
            "adjusted_ate_mean": float(np.mean([row["adjusted_ate"] for row in selected])),
            "naive_ate_mean": float(np.mean([row["naive_ate"] for row in selected])),
            "adjusted_bias": float(adjusted_error.mean()),
            "naive_bias": float(naive_error.mean()),
            "adjusted_rmse": float(np.sqrt(np.mean(np.square(adjusted_error)))),
            "naive_rmse": float(np.sqrt(np.mean(np.square(naive_error)))),
            "mean_absolute_segment_error": float(np.mean(segment_absolute)),
            "mean_cate_rmse": float(np.mean([row["cate_rmse"] for row in selected])),
            "coverage_95": float(np.mean([row["covered"] for row in selected])),
            "false_positive_rate": float(np.mean([row["significant"] for row in selected])),
            "mean_fraction_clipped": float(np.mean([row["fraction_clipped"] for row in selected])),
            "mean_overlap_fraction": float(np.mean([row["overlap_fraction"] for row in selected])),
            "mean_treated_ess": float(np.mean([row["treated_ess"] for row in selected])),
            "mean_control_ess": float(np.mean([row["control_ess"] for row in selected])),
        }
    randomized = scenarios["randomized"]
    confounded = scenarios["confounded"]
    placebo = scenarios["placebo"]
    conditions = {
        "randomized_absolute_bias": abs(float(randomized["adjusted_bias"])) < 0.005,
        "randomized_rmse": float(randomized["adjusted_rmse"]) < 0.010,
        "randomized_segment_error": float(randomized["mean_absolute_segment_error"]) < 0.010,
        "randomized_coverage": 0.88 <= float(randomized["coverage_95"]) <= 0.99,
        "placebo_mean": abs(float(placebo["adjusted_ate_mean"])) < 0.005,
        "placebo_false_positive": float(placebo["false_positive_rate"]) <= 0.10,
        "confounded_naive_biased": abs(float(confounded["naive_bias"])) >= 0.010,
        "confounded_adjustment_reduces_bias": abs(float(confounded["adjusted_bias"]))
        <= 0.60 * abs(float(confounded["naive_bias"])),
        "valid_seeds": all(int(value["valid_seeds"]) >= 95 for value in scenarios.values()),
    }
    summary = {
        "label": "SYNTHETIC ORACLE — INTERNAL METHOD VALIDATION ONLY",
        "preregistration": "docs/LAYER3_VALIDATION_PREREGISTRATION.md",
        "seeds": [0, 99],
        "customers_per_seed": 20_000,
        "estimator": "five-fold cross-fitted AIPW with logistic propensity/outcome nuisances",
        "scenarios": scenarios,
        "acceptance_conditions": conditions,
        "verdict": "PASS" if all(conditions.values()) else "FAIL",
        "oracle_isolation": (
            "truth accessed only after each estimate was frozen in Prediction Ledger"
        ),
    }
    (OUTPUT / "seed_results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
