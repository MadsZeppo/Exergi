"""Run the preregistered V7.3 disjoint stability-gate tournament."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from decision_engine.stability_v73 import (
    CANDIDATE_GATES,
    GateDecision,
    GateInput,
    WorldFamily,
    assess_candidates,
    compute_evidence,
    generate_world,
)

ROOT = Path(__file__).resolve().parent
PREREGISTRATION = ROOT / "V7_3_PREREGISTRATION.md"
CONFIG = ROOT / "manifests/gate_benchmark_preregistration.json"
RESULTS = ROOT / "results"
FREEZE = ROOT / "manifests/V7_3_GATE_FREEZE.json"
V72_REFERENCE = "3ec80610c1cb990a9440b67ec60b2ab7ad75cc57"
SENSITIVITY_WORLDS_PER_FAMILY = 50


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True
    ).stdout.strip()


def _quantile(values: np.ndarray, probability: float) -> float:
    return 0.0 if len(values) == 0 else float(np.quantile(values, probability))


def _metrics(rows: list[dict[str, Any]], gate: str) -> dict[str, Any]:
    selected = [row for row in rows if row["gate"] == gate]
    acts = np.asarray([row["act"] for row in selected], dtype=bool)
    truth = np.asarray([row["true_net_value"] for row in selected], dtype=float)
    unsupported = np.asarray([not row["supported_action"] for row in selected], dtype=bool)
    harmful = np.asarray([row["harmful"] for row in selected], dtype=bool)
    null = np.asarray([row["null"] for row in selected], dtype=bool)
    material = np.asarray(
        [
            row["materially_positive"]
            and row["supported_action"]
            and row["budget_valid"]
            and row["early_release_safe"]
            for row in selected
        ],
        dtype=bool,
    )
    budget_invalid = np.asarray([not row["budget_valid"] for row in selected], dtype=bool)
    early_invalid = np.asarray([not row["early_release_safe"] for row in selected], dtype=bool)
    value = acts * truth
    loss = np.maximum(-value, 0.0)
    positive_loss = np.sort(loss[loss > 0])
    cvar_cut = _quantile(loss, 0.99)
    cvar_tail = loss[loss >= cvar_cut]
    confidence = np.asarray([row["confidence"] for row in selected], dtype=float)
    target = truth > 0
    return {
        "worlds": len(selected),
        "act_rate": float(acts.mean()),
        "unsupported_act_count": int(np.sum(acts & unsupported)),
        "harmful_act_rate": float(np.mean(acts[harmful])) if np.any(harmful) else 0.0,
        "null_act_rate": float(np.mean(acts[null])) if np.any(null) else 0.0,
        "material_true_act_rate": float(np.mean(acts[material])) if np.any(material) else 0.0,
        "false_negative_rate": float(np.mean(~acts[material])) if np.any(material) else 0.0,
        "expected_policy_value": float(value.mean()),
        "mean_regret_vs_oracle_bau": float(np.mean(np.maximum(truth, 0.0) - value)),
        "maximum_drawdown": float(positive_loss[-1]) if len(positive_loss) else 0.0,
        "p95_loss": _quantile(loss, 0.95),
        "p99_loss": _quantile(loss, 0.99),
        "cvar99_loss": float(cvar_tail.mean()) if len(cvar_tail) else 0.0,
        "budget_violation_count": int(np.sum(acts & budget_invalid)),
        "early_release_violation_count": int(np.sum(acts & early_invalid)),
        "confidence_brier_score": float(np.mean((confidence - target.astype(float)) ** 2)),
    }


def _decision_row(
    level: str,
    family: WorldFamily,
    index: int,
    truth: Any,
    decision: GateDecision,
) -> dict[str, Any]:
    return {
        "level": level,
        "family": family.value,
        "world_index": index,
        "gate": decision.gate,
        "act": decision.act,
        "point_net_value": decision.point_net_value,
        "lower_bound": decision.lower_bound,
        "confidence": decision.confidence,
        "supported": decision.supported,
        "reasons": list(decision.reasons),
        **asdict(truth),
    }


def _drop_largest_observation(data: GateInput) -> GateInput:
    mature_indices = np.flatnonzero(data.mature)
    drop = int(mature_indices[np.argmax(np.abs(data.outcome[mature_indices]))])
    keep = np.arange(len(data.outcome)) != drop
    return GateInput(
        outcome=data.outcome[keep],
        treatment=data.treatment[keep],
        features=data.features[keep],
        unit_id=data.unit_id[keep],
        split_key=data.split_key[keep],
        logged_propensity=data.logged_propensity[keep],
        mature=data.mature[keep],
        action_cost=data.action_cost,
        per_unit_budget=data.per_unit_budget,
        assignment_integrity_valid=data.assignment_integrity_valid,
        support_valid=data.support_valid,
        post_treatment_feature_present=data.post_treatment_feature_present,
        assignment_contamination=data.assignment_contamination,
    )


def _run_development(config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    level = "gate_development"
    root_seed = int(config["levels"][level]["seed_root"])
    worlds_per_family = int(config["levels"][level]["worlds_per_family"])
    rows: list[dict[str, Any]] = []
    sensitivity = {
        gate: {"base": [], "seed": [], "fold3": [], "fold10": [], "drop_top": []}
        for gate in CANDIDATE_GATES
    }
    for family_index, family in enumerate(WorldFamily):
        for index in range(worlds_per_family):
            world_index = family_index * worlds_per_family + index
            world = generate_world(family, root_seed, world_index)
            evidence = compute_evidence(
                world.gate_input, seed=root_seed + world_index, bootstrap_replicates=200
            )
            decisions = assess_candidates(evidence)
            rows.extend(
                _decision_row(level, family, index, world.evaluator_truth, decision)
                for decision in decisions.values()
            )
            if index < SENSITIVITY_WORLDS_PER_FAMILY:
                alternatives = {
                    "seed": assess_candidates(
                        compute_evidence(
                            world.gate_input,
                            seed=root_seed + 10_000_000 + world_index,
                            bootstrap_replicates=200,
                        )
                    ),
                    "fold3": assess_candidates(
                        compute_evidence(
                            world.gate_input,
                            seed=root_seed + world_index,
                            folds=3,
                            bootstrap_replicates=200,
                        )
                    ),
                    "fold10": assess_candidates(
                        compute_evidence(
                            world.gate_input,
                            seed=root_seed + world_index,
                            folds=10,
                            bootstrap_replicates=200,
                        )
                    ),
                    "drop_top": assess_candidates(
                        compute_evidence(
                            _drop_largest_observation(world.gate_input),
                            seed=root_seed + world_index,
                            bootstrap_replicates=200,
                        )
                    ),
                }
                for gate in CANDIDATE_GATES:
                    sensitivity[gate]["base"].append(decisions[gate].act)
                    for name, values in alternatives.items():
                        sensitivity[gate][name].append(values[gate].act)
    metrics = {gate: _metrics(rows, gate) for gate in CANDIDATE_GATES}
    for gate in CANDIDATE_GATES:
        base = np.asarray(sensitivity[gate]["base"], dtype=bool)
        metrics[gate]["seed_decision_agreement"] = float(
            np.mean(base == np.asarray(sensitivity[gate]["seed"], dtype=bool))
        )
        metrics[gate]["fold_count_decision_agreement"] = float(
            min(
                np.mean(base == np.asarray(sensitivity[gate]["fold3"], dtype=bool)),
                np.mean(base == np.asarray(sensitivity[gate]["fold10"], dtype=bool)),
            )
        )
        metrics[gate]["drop_top_decision_agreement"] = float(
            np.mean(base == np.asarray(sensitivity[gate]["drop_top"], dtype=bool))
        )
    baseline_fnr = metrics["existing_v72_fold_veto"]["false_negative_rate"]
    limits = config["risk_limits"]
    eligible: list[str] = []
    for gate, value in metrics.items():
        improvement = baseline_fnr - value["false_negative_rate"]
        value["false_negative_improvement_vs_existing"] = improvement
        checks = {
            "selectable_not_bayesian": gate != "bayesian_positive_probability",
            "unsupported_act_zero": value["unsupported_act_count"] == limits["unsupported_act"],
            "harmful_act": value["harmful_act_rate"] <= limits["harmful_act_rate_max"],
            "null_act": value["null_act_rate"] <= limits["null_act_rate_max"],
            "positive_expected_value": value["expected_policy_value"] > 0,
            "p95_loss": value["p95_loss"] <= limits["p95_loss_max"],
            "p99_loss": value["p99_loss"] <= limits["p99_loss_max"],
            "cvar99_loss": value["cvar99_loss"] <= limits["cvar99_loss_max"],
            "maximum_drawdown": value["maximum_drawdown"] <= limits["maximum_drawdown_max"],
            "budget": value["budget_violation_count"] == limits["budget_violations"],
            "early_release": value["early_release_violation_count"]
            == limits["early_release_violations"],
            "seed_stability": value["seed_decision_agreement"] >= 0.90,
            "fold_stability": value["fold_count_decision_agreement"] >= 0.85,
            "false_negative_improvement": improvement
            >= limits["material_false_negative_improvement_min"],
        }
        value["selection_checks"] = checks
        value["development_pass"] = all(checks.values())
        if value["development_pass"]:
            eligible.append(gate)
    selected = None
    if eligible:
        selected = min(
            eligible,
            key=lambda gate: (
                metrics[gate]["harmful_act_rate"],
                metrics[gate]["null_act_rate"],
                metrics[gate]["act_rate"],
                -metrics[gate]["material_true_act_rate"],
            ),
        )
    summary = {
        "level": level,
        "worlds_per_family": worlds_per_family,
        "total_worlds": worlds_per_family * len(WorldFamily),
        "metrics": metrics,
        "eligible_gates": eligible,
        "selected_gate": selected,
        "selection_rule_applied": True,
    }
    return summary, rows


def _run_frozen_level(
    config: dict[str, Any], level: str, selected_gate: str, development: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root_seed = int(config["levels"][level]["seed_root"])
    worlds_per_family = int(config["levels"][level]["worlds_per_family"])
    rows: list[dict[str, Any]] = []
    for family_index, family in enumerate(WorldFamily):
        for index in range(worlds_per_family):
            world_index = family_index * worlds_per_family + index
            world = generate_world(family, root_seed, world_index)
            evidence = compute_evidence(
                world.gate_input, seed=root_seed + world_index, bootstrap_replicates=200
            )
            decision = assess_candidates(evidence)[selected_gate]
            rows.append(_decision_row(level, family, index, world.evaluator_truth, decision))
    metrics = _metrics(rows, selected_gate)
    limits = config["risk_limits"]
    development_metrics = development["metrics"][selected_gate]
    fnr_improvement = (
        development["metrics"]["existing_v72_fold_veto"]["false_negative_rate"]
        - metrics["false_negative_rate"]
    )
    checks = {
        "unsupported_act_zero": metrics["unsupported_act_count"] == limits["unsupported_act"],
        "harmful_act": metrics["harmful_act_rate"] <= limits["harmful_act_rate_max"],
        "null_act": metrics["null_act_rate"] <= limits["null_act_rate_max"],
        "positive_expected_value": metrics["expected_policy_value"] > 0,
        "p95_loss": metrics["p95_loss"] <= limits["p95_loss_max"],
        "p99_loss": metrics["p99_loss"] <= limits["p99_loss_max"],
        "cvar99_loss": metrics["cvar99_loss"] <= limits["cvar99_loss_max"],
        "maximum_drawdown": metrics["maximum_drawdown"] <= limits["maximum_drawdown_max"],
        "budget": metrics["budget_violation_count"] == 0,
        "early_release": metrics["early_release_violation_count"] == 0,
        "power_retained": metrics["material_true_act_rate"]
        >= 0.90 * development_metrics["material_true_act_rate"],
        "false_negative_improvement": fnr_improvement
        >= limits["material_false_negative_improvement_min"],
    }
    return {
        "level": level,
        "selected_gate": selected_gate,
        "worlds_per_family": worlds_per_family,
        "total_worlds": worlds_per_family * len(WorldFamily),
        "metrics": metrics,
        "checks": checks,
        "passed": all(checks.values()),
        "false_negative_improvement_reference": fnr_improvement,
    }, rows


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows))


def _freeze(selected: str, development: dict[str, Any]) -> dict[str, Any]:
    freeze = {
        "status": "FROZEN_FOR_GATE_VALIDATION",
        "selected_gate": selected,
        "source_commit": V72_REFERENCE,
        "runtime_head_before_v73": _source_commit(),
        "preregistration_sha256": _sha256(PREREGISTRATION),
        "configuration_sha256": _sha256(CONFIG),
        "gate_code_sha256": _sha256(Path("src/decision_engine/stability_v73/gates.py")),
        "dgp_code_sha256": _sha256(Path("src/decision_engine/stability_v73/dgp.py")),
        "development_result_sha256": _sha256(RESULTS / "gate_development_summary.json"),
        "thresholds": json.loads(CONFIG.read_text())["risk_limits"],
        "gate_definition": selected,
        "cost_semantics": "observed monetary outcome minus declared per-unit action cost",
        "truth_available_to_gate": False,
        "hillstrom_development_consumed": True,
        "hillstrom_validation_opened": False,
    }
    _write_json(FREEZE, freeze)
    return freeze


def run() -> dict[str, Any]:
    started = time.perf_counter()
    config = json.loads(CONFIG.read_text())
    if config["source_commit"] != V72_REFERENCE or _source_commit() != V72_REFERENCE:
        raise RuntimeError("V7.3 must start from immutable V7.2 reference commit")
    development, development_rows = _run_development(config)
    _write_json(RESULTS / "gate_development_summary.json", development)
    _write_jsonl(RESULTS / "gate_development_worlds.jsonl", development_rows)
    selected = development["selected_gate"]
    outcome: dict[str, Any] = {
        "status": "V7_3_GATE_FAILED_HILLSTROM_NOT_REASSESSED",
        "v7_2_reference_commit": V72_REFERENCE,
        "development": development,
        "validation": None,
        "sealed_gate_test": None,
        "freeze": None,
        "hillstrom_validation_opened": False,
        "hillstrom_reassessed": False,
        "buy_baits_negative_control_run": False,
    }
    if selected is None:
        outcome["runtime_seconds"] = time.perf_counter() - started
        _write_json(RESULTS / "v7_3_result.json", outcome)
        return outcome

    freeze = _freeze(str(selected), development)
    outcome["freeze"] = freeze
    validation, validation_rows = _run_frozen_level(
        config, "gate_validation", str(selected), development
    )
    _write_json(RESULTS / "gate_validation_summary.json", validation)
    _write_jsonl(RESULTS / "gate_validation_worlds.jsonl", validation_rows)
    outcome["validation"] = validation
    if not validation["passed"]:
        outcome["runtime_seconds"] = time.perf_counter() - started
        _write_json(RESULTS / "v7_3_result.json", outcome)
        return outcome

    sealed, sealed_rows = _run_frozen_level(config, "sealed_gate_test", str(selected), development)
    _write_json(RESULTS / "sealed_gate_test_summary.json", sealed)
    _write_jsonl(RESULTS / "sealed_gate_test_worlds.jsonl", sealed_rows)
    outcome["sealed_gate_test"] = sealed
    if not sealed["passed"]:
        outcome["runtime_seconds"] = time.perf_counter() - started
        _write_json(RESULTS / "v7_3_result.json", outcome)
        return outcome
    outcome["status"] = "SYNTHETIC_GATE_ASSURANCE_PASS_PENDING_NEGATIVE_CONTROL"
    outcome["runtime_seconds"] = time.perf_counter() - started
    _write_json(RESULTS / "v7_3_result.json", outcome)
    return outcome


if __name__ == "__main__":
    result = run()
    print(
        json.dumps(
            {
                "status": result["status"],
                "selected_gate": result["development"]["selected_gate"],
                "validation_passed": None
                if result["validation"] is None
                else result["validation"]["passed"],
                "sealed_passed": None
                if result["sealed_gate_test"] is None
                else result["sealed_gate_test"]["passed"],
                "runtime_seconds": result["runtime_seconds"],
            },
            indent=2,
        )
    )
