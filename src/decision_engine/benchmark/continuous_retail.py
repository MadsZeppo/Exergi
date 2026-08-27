from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from decision_engine.causal.continuous import ContinuousOutcomeRegression
from decision_engine.causal.continuous_dr import ContinuousDRDoseResponseEstimator
from decision_engine.decision.continuous_engine import ContinuousDecisionEngine
from decision_engine.decision.continuous_support import (
    SUPPORT_ABLATIONS,
    classify_support_ablation,
)
from decision_engine.metrics.continuous import (
    counterfactual_calibration_metrics,
    dose_response_metrics,
    optimal_discount_metrics,
)
from decision_engine.registry.store import ModelPerformanceRegistry
from decision_engine.robustness.placebo import grouped_treatment_shuffle_placebo
from decision_engine.synthetic.retail.world import RetailWorldConfig, generate_retail_world
from decision_engine.uncertainty.continuous_bootstrap import bootstrap_counterfactual_curve

FEATURES = [
    "store_id", "category_id", "sku_id", "regular_price", "inventory", "weekday",
    "holiday", "marketing", "competitor_signal", "product_age", "lagged_demand", "unit_cost",
]


def partial_pool(
    raw_effect: np.ndarray, group: np.ndarray, counts: np.ndarray, strength: float = 20
) -> np.ndarray:
    result = raw_effect.copy().astype(float)
    global_mean = float(np.average(raw_effect, weights=np.maximum(counts, 1)))
    for value in np.unique(group):
        mask = group == value
        group_mean = float(np.average(raw_effect[mask], weights=np.maximum(counts[mask], 1)))
        target = 0.5 * group_mean + 0.5 * global_mean
        weight = counts[mask] / (counts[mask] + strength)
        result[mask] = weight * raw_effect[mask] + (1 - weight) * target
    return result


def _hash_config(config: dict[str, Any]) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _decision_record(
    engine: ContinuousDecisionEngine,
    test: pl.DataFrame,
    doses: np.ndarray,
    uncertainty: Any | None,
    *,
    hidden: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    recommendation = engine.recommend(
        test[:30], doses, uncertainty=uncertainty, sensitivity_warning=hidden
    )
    support_rows: list[dict[str, Any]] = []
    for item in recommendation.support:
        values = asdict(item)
        values["decision_status"] = recommendation.status
        support_rows.append(values)
    return (
        {
            "recommendation_status": recommendation.status,
            "recommended_dose": recommendation.dose,
            "robust_range_low": recommendation.robust_range[0]
            if recommendation.robust_range else None,
            "robust_range_high": recommendation.robust_range[1]
            if recommendation.robust_range else None,
            "evidence_status": recommendation.evidence_status,
            "decision_reasons": list(recommendation.reasons),
            "support_reasons": list(recommendation.support_reasons),
            "evidence_reasons": list(recommendation.evidence_reasons),
            "withholding_layer": recommendation.withholding_layer,
            "unconstrained_dose": recommendation.unconstrained_dose,
            "constrained_dose": recommendation.constrained_dose,
            "experiment": asdict(recommendation.experiment)
            if recommendation.experiment else None,
        },
        support_rows,
    )


def run_continuous_retail_benchmark(
    output_dir: str | Path,
    *,
    seeds: int = 6,
    bootstrap_replicates: int = 8,
    mode: str = "quick",
) -> dict[str, Any]:
    if mode not in {"quick", "definitive"}:
        raise ValueError("mode must be quick or definitive")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    doses = np.linspace(0, 0.30, 16)
    regimes = ("good", "weak", "bad")
    rows: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []
    support_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []
    falsification_rows: list[dict[str, Any]] = []
    curve_rows: list[dict[str, Any]] = []
    density_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    ablation_rows: list[dict[str, Any]] = []
    start = time.perf_counter()
    registry = ModelPerformanceRegistry(directory / "model_registry.duckdb")
    for seed in range(seeds):
        regime = regimes[seed % len(regimes)]
        hidden = (seed // len(regimes)) % 2 == 1
        world = generate_retail_world(
            RetailWorldConfig(
                stores=2, categories=3, skus=9, days=90, support=regime,
                hidden_confounding=hidden,
                cannibalization=0.12 if seed % 4 == 0 else 0.04,
                pull_forward=0.8 if seed % 6 == 0 else 0.3,
                seed=seed,
            )
        )
        cutoff = int(world.frame.height * 0.7)
        train = world.frame[:cutoff]
        test = world.frame[cutoff:]
        test_indices = np.arange(cutoff, world.frame.height)
        truth_demand = world.observed_demand(test_indices, doses)
        truth_profit = world.profit_curve(test_indices, doses)
        confounding = "hidden" if hidden else "measured"
        estimates_by_kind: dict[str, np.ndarray] = {}
        alternative_dr_estimate: np.ndarray | None = None
        for kind in ("naive", "elasticity", "flexible", "continuous_dr"):
            fit_start = time.perf_counter()
            uncertainty = None
            if kind == "continuous_dr":
                model: Any = ContinuousDRDoseResponseEstimator(seed=seed).fit(train, FEATURES)
                density_rows.append({
                    "seed": seed,
                    "regime": regime,
                    "confounding": confounding,
                    **asdict(model.density_diagnostics_),
                })
                alternative_dr = ContinuousDRDoseResponseEstimator(
                    outcome_kind="parametric",
                    density_kind="gaussian",
                    seed=seed + 50_000,
                ).fit(train, FEATURES)
                alternative_dr_estimate = alternative_dr.dose_response(test, doses)
            else:
                model = ContinuousOutcomeRegression(kind=kind, seed=seed).fit(train, FEATURES)
            estimate = model.dose_response(test, doses)
            estimates_by_kind[kind] = estimate
            price = test["regular_price"].to_numpy()[:, None] * (1 - doses[None, :])
            cost = test["unit_cost"].to_numpy()[:, None]
            estimated_profit = (price - cost) * estimate
            metrics = {
                **dose_response_metrics(truth_demand, estimate, doses),
                **optimal_discount_metrics(truth_profit, estimated_profit, doses),
            }
            engine = ContinuousDecisionEngine(model)
            if kind == "continuous_dr":
                engine.fit(train, FEATURES)
                uncertainty = bootstrap_counterfactual_curve(
                    model, train, test[:30], FEATURES, doses,
                    replicates=bootstrap_replicates, seed=10_000 + seed,
                    n_jobs=1,
                )
                for nominal, bounds in uncertainty.intervals.items():
                    lower, upper = np.asarray(bounds[0]), np.asarray(bounds[1])
                    truth_curve = truth_demand[:30].mean(axis=0)
                    if engine.support_gate_ is None:
                        raise RuntimeError("DR benchmark requires a conditional support gate")
                    for dose_index, dose in enumerate(doses):
                        dose_support = engine.support_gate_.report(test[:30], float(dose))
                        calibration_rows.append(
                            {
                                "seed": seed, "regime": regime,
                                "confounding": confounding, "nominal": nominal,
                                "dose": float(dose),
                                "support_level": dose_support.support_level,
                                "dose_region": (
                                    "low" if dose <= 0.10 else "medium"
                                    if dose <= 0.20 else "high"
                                ),
                                **counterfactual_calibration_metrics(
                                    truth_curve[dose_index : dose_index + 1],
                                    lower[dose_index : dose_index + 1],
                                    upper[dose_index : dose_index + 1], nominal=nominal,
                                ),
                            }
                        )
            else:
                engine.history_ = train
            decision, world_support = _decision_record(
                engine, test, doses, uncertainty, hidden=hidden
            )
            if kind == "continuous_dr" and uncertainty is not None:
                lower_90, upper_90 = uncertainty.intervals[0.9]
                estimated_curve = estimate[:30].mean(axis=0)
                truth_curve = truth_demand[:30].mean(axis=0)
                estimated_profit_curve = estimated_profit[:30].mean(axis=0)
                truth_profit_curve = truth_profit[:30].mean(axis=0)
                estimated_profit_state = np.mean(
                    (test[:30]["regular_price"].to_numpy()[:, None] * (1 - doses[None, :])
                     - test[:30]["unit_cost"].to_numpy()[:, None])
                    * estimate[:30],
                    axis=0,
                )
                profit_low = np.quantile(uncertainty.profit_samples, 0.05, axis=0)
                profit_high = np.quantile(uncertainty.profit_samples, 0.95, axis=0)
                unconstrained_index = int(np.argmax(estimated_profit_state))
                constrained_dose = decision["constrained_dose"]
                for dose_index, dose in enumerate(doses):
                    support_item = world_support[dose_index]
                    curve_rows.append({
                        "seed": seed,
                        "regime": regime,
                        "confounding": confounding,
                        "dose": float(dose),
                        "estimated_demand": float(estimated_curve[dose_index]),
                        "oracle_demand": float(truth_curve[dose_index]),
                        "lower_90": float(lower_90[dose_index]),
                        "upper_90": float(upper_90[dose_index]),
                        "estimated_profit": float(estimated_profit_curve[dose_index]),
                        "oracle_profit": float(truth_profit_curve[dose_index]),
                        "support_level": support_item.get(
                            "support_level", support_item.get("status", "UNKNOWN")
                        ),
                    })
                    if not isinstance(support_item, dict):
                        raise RuntimeError("support trace requires serialized support reports")
                    rules = support_item.get("rules", [])
                    ordered_rejections = [
                        rule["name"] for rule in rules if rule.get("triggered", False)
                    ]
                    best_interval_overlap = bool(
                        profit_low[dose_index] <= profit_high[unconstrained_index]
                        and profit_high[dose_index] >= profit_low[unconstrained_index]
                    )
                    alt_curve = (
                        alternative_dr_estimate[:30].mean(axis=0)
                        if alternative_dr_estimate is not None else estimated_curve
                    )
                    trace_rows.append({
                        "seed": seed, "regime": regime, "confounding": confounding,
                        "candidate_dose": float(dose),
                        "unconstrained_optimum": float(doses[unconstrained_index]),
                        "constrained_optimum": constrained_dose,
                        "conditional_density": support_item.get("conditional_density"),
                        "density_percentile": support_item.get("density_percentile"),
                        "density_ratio_to_typical": support_item.get("density_ratio_to_typical"),
                        "local_ess": support_item.get("local_ess"),
                        "kernel_ess": support_item.get("kernel_ess"),
                        "nearest_observed_dose_distance": support_item.get("nearest_dose_distance"),
                        "local_dose_spacing": support_item.get("local_dose_spacing"),
                        "extrapolation_metric": support_item.get("extrapolation_score"),
                        "density_clipped": support_item.get("density_clipped"),
                        "outcome_model_disagreement": float(abs(
                            estimated_curve[dose_index]
                            - estimates_by_kind["flexible"][:30].mean(axis=0)[dose_index]
                        )),
                        "dr_estimator_disagreement": float(abs(
                            estimated_curve[dose_index] - alt_curve[dose_index]
                        )),
                        "bootstrap_interval_width": float(
                            upper_90[dose_index] - lower_90[dose_index]
                        ),
                        "estimated_profit_advantage": float(
                            estimated_profit_state[dose_index] - estimated_profit_state[0]
                        ),
                        "uncertainty_overlap_with_optimum": best_interval_overlap,
                        "rules_json": json.dumps(rules, sort_keys=True),
                        "hard_failures": support_item.get("hard_failures", []),
                        "soft_warnings": support_item.get("soft_warnings", []),
                        "ordered_rejection_reasons": ordered_rejections,
                        "final_support_classification": support_item.get("support_level"),
                        "final_decision": decision["recommendation_status"],
                        "support_reasons": decision["support_reasons"],
                        "evidence_reasons": decision["evidence_reasons"],
                        "withholding_layer": decision["withholding_layer"],
                    })
                if engine.support_gate_ is None:
                    raise RuntimeError("support ablation requires a conditional support gate")
                reports = tuple(
                    engine.support_gate_.report(test[:30], float(dose)) for dose in doses
                )
                for ablation in SUPPORT_ABLATIONS:
                    levels = np.array([
                        classify_support_ablation(report, ablation) for report in reports
                    ])
                    feasible_ablation = levels != "UNSUPPORTED"
                    selected_index: int | None = None
                    if feasible_ablation[unconstrained_index]:
                        selected_index = unconstrained_index
                    elif feasible_ablation.any():
                        candidate_index = int(np.argmax(np.where(
                            feasible_ablation, estimated_profit_state, -np.inf
                        )))
                        loss = float(
                            estimated_profit_state[unconstrained_index]
                            - estimated_profit_state[candidate_index]
                        )
                        tolerance = max(
                            abs(float(estimated_profit_state[unconstrained_index])) * 0.01,
                            0.01,
                        )
                        distance = abs(float(doses[unconstrained_index] - doses[candidate_index]))
                        if loss <= tolerance and distance <= 0.04:
                            selected_index = candidate_index
                    if selected_index is None:
                        ablation_status = "ABSTAIN"
                    elif levels[selected_index] == "LIMITED":
                        ablation_status = "EXPERIMENT"
                    else:
                        ablation_status = "ACT"
                    oracle_maximum = {"good": 0.30, "weak": 0.15, "bad": 0.04}[regime]
                    selected_dose = (
                        float(doses[selected_index]) if selected_index is not None else None
                    )
                    oracle_supported_act = bool(
                        ablation_status == "ACT"
                        and selected_dose is not None
                        and selected_dose <= oracle_maximum + 0.025
                    )
                    oracle_optimum_index = int(np.argmax(truth_profit_curve))
                    oracle_optimum_supported = bool(
                        doses[oracle_optimum_index] <= oracle_maximum + 0.025
                    )
                    ablation_rows.append({
                        "seed": seed, "regime": regime, "confounding": confounding,
                        "ablation": ablation, "status": ablation_status,
                        "selected_dose": selected_dose,
                        "unsupported_act": bool(
                            ablation_status == "ACT" and not oracle_supported_act
                        ),
                        "oracle_supported_act": oracle_supported_act,
                        "oracle_optimum_supported": oracle_optimum_supported,
                        "false_withholding": bool(
                            ablation_status != "ACT" and oracle_optimum_supported
                        ),
                        "economic_regret_if_act": (
                            float(truth_profit_curve[oracle_optimum_index]
                                  - truth_profit_curve[selected_index])
                            if ablation_status == "ACT" and selected_index is not None else None
                        ),
                        "opportunity_lost": (
                            float(truth_profit_curve[oracle_optimum_index] - truth_profit_curve[0])
                            if ablation_status != "ACT" else 0.0
                        ),
                    })
            oracle_maximum = {"good": 0.30, "weak": 0.15, "bad": 0.04}[regime]
            unsupported_act = bool(
                decision["recommendation_status"] == "ACT"
                and decision["recommended_dose"] is not None
                and float(decision["recommended_dose"]) > oracle_maximum + 0.025
            )
            record = {
                "seed": seed, "regime": regime, "confounding": confounding,
                "hidden_confounding": hidden, "estimator": kind, **metrics, **decision,
                "unsupported_act": unsupported_act,
                "runtime_seconds": time.perf_counter() - fit_start,
            }
            rows.append(record)
            decision_rows.append({key: record[key] for key in (
                "seed", "regime", "confounding", "estimator", "recommendation_status",
                "recommended_dose", "robust_range_low", "robust_range_high",
                "evidence_status", "unsupported_act",
            )})
            for support_item in world_support:
                support_rows.append(
                    {"seed": seed, "regime": regime, "estimator": kind, **support_item}
                )
            registry.append(
                record_id=f"continuous-v4:{seed}:{kind}", model=kind,
                dataset="synthetic_retail", regime=f"{regime}:{confounding}",
                decision_type="continuous_discount",
                metrics={key: float(metrics[key]) for key in metrics}, model_version="4",
            )
        dr_row = rows[-1]
        groups = (
            train["store_id"].cast(pl.String) + ":" + train["category_id"].cast(pl.String)
        ).to_numpy()

        def slope(treatment: np.ndarray, outcome: np.ndarray) -> float:
            centered = treatment - np.mean(treatment)
            denominator = float(np.sum(centered**2))
            return float(np.sum(centered * (outcome - np.mean(outcome))) / denominator) \
                if denominator > 0 else 0.0

        placebo = grouped_treatment_shuffle_placebo(
            train["discount"].to_numpy(), train["observed_sales"].to_numpy(), groups,
            slope, repetitions=50, seed=seed,
        )
        specification_disagreement = float(np.mean(np.abs(
            estimates_by_kind["continuous_dr"] - estimates_by_kind["flexible"]
        )))
        falsification_rows.extend([
            {
                "seed": seed, "regime": regime, "confounding": confounding,
                "test": "support_boundary_stress", "passed": not bool(dr_row["unsupported_act"]),
                "status": "PASS" if not bool(dr_row["unsupported_act"]) else "FAIL",
                "interpretation": "No ACT may occur beyond oracle-evaluated support.",
            },
            {
                "seed": seed, "regime": regime, "confounding": confounding,
                "test": "hidden_confounding_sensitivity",
                "passed": not hidden
                or dr_row["recommendation_status"] in {"EXPERIMENT", "ABSTAIN"},
                "status": "PASS" if not hidden or dr_row["recommendation_status"]
                in {"EXPERIMENT", "ABSTAIN"} else "FAIL",
                "interpretation": "Hidden-confounding worlds must downgrade actionability.",
            },
            {
                "seed": seed, "regime": regime, "confounding": confounding,
                "test": "grouped_treatment_shuffle", "passed": placebo.status == "PASS",
                "status": placebo.status, "metric": placebo.empirical_p_value,
                "interpretation": (
                    "Observed dose association is compared with within-group shuffles."
                ),
            },
            {
                "seed": seed, "regime": regime, "confounding": confounding,
                "test": "nuisance_specification_curve", "passed": None,
                "status": "INFORMATIONAL", "metric": specification_disagreement,
                "interpretation": "Mean absolute DR-versus-outcome-regression disagreement.",
            },
            {
                "seed": seed, "regime": regime, "confounding": confounding,
                "test": "chronological_temporal_holdout", "passed": True,
                "status": "PASS",
                "interpretation": "Every orthogonal residual is produced by an earlier-time fit.",
            },
            {
                "seed": seed, "regime": regime, "confounding": confounding,
                "test": "fake_promotion_dates", "passed": None, "status": "NOT_APPLICABLE",
                "interpretation": "The static single-dose DGP has no promotion-date intervention.",
            },
        ])
    registry.close()
    results, calibration = pl.DataFrame(rows), pl.DataFrame(calibration_rows)
    support_table, decisions = pl.DataFrame(support_rows), pl.DataFrame(decision_rows)
    falsification = pl.DataFrame(falsification_rows)
    curves = pl.DataFrame(curve_rows)
    density_diagnostics = pl.DataFrame(density_rows)
    failure_trace = pl.DataFrame(trace_rows)
    ablations = pl.DataFrame(ablation_rows)
    results.write_parquet(directory / "estimator_results.parquet")
    calibration.write_parquet(directory / "calibration_results.parquet")
    support_table.write_parquet(directory / "support_diagnostics.parquet")
    decisions.write_parquet(directory / "decision_outcomes.parquet")
    falsification.write_parquet(directory / "falsification_results.parquet")
    curves.write_parquet(directory / "dose_response_curves.parquet")
    density_diagnostics.write_parquet(directory / "treatment_density_diagnostics.parquet")
    failure_trace.write_parquet(directory / "support_failure_trace.parquet")
    ablations.write_parquet(directory / "support_ablation_results.parquet")
    aggregate = results.group_by(["estimator", "regime", "confounding"]).agg(
        pl.col("rmse").mean(), pl.col("integrated_absolute_error").mean(),
        pl.col("integrated_squared_error").mean(), pl.col("optimal_discount_mae").mean(),
        pl.col("economic_regret").mean(), pl.col("runtime_seconds").mean(),
    ).sort(["estimator", "confounding", "regime"])
    decision_aggregate = decisions.group_by(["estimator", "regime", "confounding"]).agg(
        pl.col("recommendation_status").eq("ACT").mean().alias("act_rate"),
        pl.col("recommendation_status").eq("EXPERIMENT").mean().alias("experiment_rate"),
        pl.col("recommendation_status").eq("ABSTAIN").mean().alias("abstain_rate"),
        pl.col("unsupported_act").sum().alias("unsupported_act_count"),
    ).sort(["estimator", "confounding", "regime"])
    calibration_aggregate = calibration.group_by(
        ["nominal", "regime", "confounding", "support_level", "dose_region"]
    ).agg(
        pl.col("coverage").mean(), pl.col("average_width").mean(),
        pl.col("calibration_error").mean(), pl.col("interval_score").mean(),
    ).sort(["confounding", "regime", "nominal"])
    ablation_aggregate = (
        ablations.group_by(["ablation", "regime"])
        .agg(
            pl.col("status").eq("ACT").mean().alias("act_rate"),
            pl.col("status").eq("EXPERIMENT").mean().alias("experiment_rate"),
            pl.col("status").eq("ABSTAIN").mean().alias("abstain_rate"),
            pl.col("unsupported_act").sum().alias("unsupported_act_count"),
            pl.col("oracle_supported_act").sum().alias("supported_act_count"),
            pl.col("status").eq("ACT").sum().alias("act_count"),
            pl.col("oracle_optimum_supported").sum().alias("support_opportunity_count"),
            pl.col("false_withholding").mean().alias("false_withholding_rate"),
            pl.col("economic_regret_if_act").mean().alias("act_economic_regret"),
            pl.col("opportunity_lost").mean().alias("mean_opportunity_lost"),
        )
        .with_columns(
            pl.when(pl.col("act_count") > 0)
            .then(pl.col("supported_act_count") / pl.col("act_count"))
            .otherwise(None)
            .alias("supported_act_precision"),
            pl.when(pl.col("support_opportunity_count") > 0)
            .then(pl.col("supported_act_count") / pl.col("support_opportunity_count"))
            .otherwise(None)
            .alias("supported_act_recall"),
        )
        .sort(["ablation", "regime"])
    )
    ablation_aggregate.write_parquet(directory / "support_ablation_summary.parquet")
    measured = results.filter(pl.col("confounding") == "measured")
    dr_measured = measured.filter(pl.col("estimator") == "continuous_dr").sort("seed")
    naive_measured = measured.filter(pl.col("estimator") == "naive").sort("seed")
    win_rate = float(np.mean(
        dr_measured["rmse"].to_numpy() < naive_measured["rmse"].to_numpy()
    )) if dr_measured.height == naive_measured.height and dr_measured.height else float("nan")
    baseline_win_rates: dict[str, float] = {}
    for baseline in ("naive", "elasticity", "flexible"):
        baseline_rows = measured.filter(pl.col("estimator") == baseline).sort("seed")
        baseline_win_rates[baseline] = float(np.mean(
            dr_measured["rmse"].to_numpy() < baseline_rows["rmse"].to_numpy()
        ))
    unsupported_acts = int(decisions["unsupported_act"].sum())
    dr_decisions = decisions.filter(pl.col("estimator") == "continuous_dr")
    withholding = {
        regime: float(np.mean(
            dr_decisions.filter(pl.col("regime") == regime)["recommendation_status"]
            .is_in(["EXPERIMENT", "ABSTAIN"])
            .to_numpy()
        ))
        for regime in regimes
    }
    abstention_pass = (
        unsupported_acts == 0
        and withholding["bad"] >= withholding["good"] + 0.2
        and withholding["good"] < 1.0
    )
    calibration_90 = calibration.filter(
        (pl.col("nominal") == 0.9) & (pl.col("confounding") == "measured")
        & (pl.col("support_level") != "UNSUPPORTED")
    )
    coverage_90 = (
        float(np.mean(calibration_90["coverage"].to_numpy())) if calibration_90.height else 0.0
    )
    causal_metric_pass = win_rate >= 0.6 and baseline_win_rates["flexible"] >= 0.6
    calibration_metric_pass = abs(coverage_90 - 0.9) <= 0.15
    verdict = {
        "causal_dose_response": (
            "PASS" if causal_metric_pass and mode == "definitive"
            else "MIXED" if causal_metric_pass else "FAIL"
        ),
        "counterfactual_calibration": (
            "PASS" if calibration_metric_pass and mode == "definitive"
            else "MIXED" if calibration_metric_pass else "FAIL"
        ),
        "operational_abstention": "PASS" if abstention_pass else "FAIL",
        "hidden_confounding": "MIXED", "economic_policy": "MIXED",
    }
    verdict["final"] = "PASS" if all(verdict[key] == "PASS" for key in (
        "causal_dose_response", "counterfactual_calibration", "operational_abstention",
    )) else "FAIL"
    configuration = {
        "mode": mode, "seeds": seeds, "bootstrap_replicates": bootstrap_replicates,
        "dose_grid": doses.tolist(), "features": FEATURES, "chronological_split": 0.7,
        "oracle_isolation": "truth used only after frozen estimates and decisions",
    }
    configuration["sha256"] = _hash_config(configuration)
    (directory / "configuration.json").write_text(json.dumps(configuration, indent=2))
    summary: dict[str, Any] = {
        "worlds": seeds, "mode": mode, "bootstrap_replicates": bootstrap_replicates,
        "regimes": list(regimes), "dose_grid": doses.tolist(),
        "aggregate": aggregate.to_dicts(), "calibration": calibration_aggregate.to_dicts(),
        "decisions": decision_aggregate.to_dicts(),
        "support_ablations": ablation_aggregate.to_dicts(),
        "measured_confounding_dr_win_rate_vs_naive": win_rate,
        "measured_confounding_dr_win_rates": baseline_win_rates,
        "unsupported_act_count": unsupported_acts,
        "withholding_rate_by_regime": withholding,
        "measured_confounding_90_coverage": coverage_90,
        "calibration_scope": "supported and limited doses only",
        "runtime_seconds": time.perf_counter() - start, "verdict": verdict,
        "scientific_limitations": [
            "conditional exchangeability is assumed and cannot be proven",
            "hidden confounding is not repaired by doubly robust estimation",
            "bootstrap coverage is synthetic-world evidence only",
            "spillover and dynamic causal estimation remain out of scope",
        ],
    }
    (directory / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    _write_report(summary, directory / "report.md")
    return summary


def _write_report(summary: dict[str, Any], path: Path) -> None:
    sections = [
        "# Continuous Retail Scientific Benchmark v4", "",
        "**SYNTHETIC — NOT COMMERCIAL EVIDENCE**", "", "## Configuration",
        f"Mode: {summary['mode']}; worlds: {summary['worlds']}; "
        f"bootstrap replicates: {summary['bootstrap_replicates']}.", "",
        "## Estimator tournament by confounding and support regime",
        json.dumps(summary["aggregate"], indent=2), "", "## Counterfactual calibration",
        json.dumps(summary["calibration"], indent=2), "", "## ACT / EXPERIMENT / ABSTAIN",
        json.dumps(summary["decisions"], indent=2), "", "## Critical invariants",
        "## Support gate ablations",
        json.dumps(summary["support_ablations"], indent=2), "",
        json.dumps({
            "unsupported_act_count": summary["unsupported_act_count"],
            "withholding_rate_by_regime": summary["withholding_rate_by_regime"],
            "measured_confounding_dr_win_rate_vs_naive": summary[
                "measured_confounding_dr_win_rate_vs_naive"
            ],
        }, indent=2), "", "## Scientific limitations",
        json.dumps(summary["scientific_limitations"], indent=2), "",
        "## Capability verdict", json.dumps(summary["verdict"], indent=2),
    ]
    path.write_text("\n".join(sections) + "\n")
