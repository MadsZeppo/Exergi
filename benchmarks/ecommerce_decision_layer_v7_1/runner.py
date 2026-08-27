"""Development selection and one-time validation runner for Exergi V7.1."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

import numpy as np

from .evaluation import V71WorldEvaluation, evaluate_candidate
from .models import EffectModel, candidate_models, causal_forest_availability
from .packs import final_commitment, v71_pack_specs, write_pack_manifest

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
MANIFESTS = ROOT / "manifests"
RESULTS = ROOT / "results"
DEVELOPMENT_FREEZE = ROOT / "FROZEN_DEVELOPMENT_SELECTION.json"
SOURCE_FREEZE = ROOT / "SOURCE_FREEZE.json"
VALIDATION_LOCK = ROOT / "VALIDATION_OPENED.json"
VALIDATION_REPORT = ROOT / "V7_1_VALIDATION_REPORT.md"
MODEL_NAMES = (
    "ridge_t_learner",
    "forest_t_learner",
    "x_learner",
    "r_learner",
    "dr_learner",
    "honest_policy_tree",
    "predefined_segment_policy",
)


def _sha(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _git(*args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=REPOSITORY,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def assert_clean_worktree() -> None:
    dirty = _git("status", "--porcelain")
    if dirty:
        raise RuntimeError("official V7.1 runs require a clean worktree")


def _source_tree_hash() -> str:
    tracked = _git("ls-files", "src", "benchmarks/ecommerce_decision_layer_v7_1", "tests")
    digest = hashlib.sha256()
    for relative in tracked.splitlines():
        is_benchmark_source = relative.startswith("benchmarks/ecommerce_decision_layer_v7_1/") and (
            relative.endswith(".py")
            or Path(relative).name
            in {
                "V7.1_PREREGISTRATION.md",
                "REAL_DATA_PROTOCOL.md",
                "LEGACY_CLAIMS_INVALIDATED.json",
                "LEGACY_ORACLE_QUARANTINE.md",
            }
        )
        if not (
            relative.startswith("src/")
            or relative.startswith("tests/")
            or is_benchmark_source
        ):
            continue
        path = REPOSITORY / relative
        if path.is_file():
            digest.update(relative.encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _dependency_versions() -> dict[str, str]:
    packages = ("numpy", "scipy", "scikit-learn", "polars", "pydantic", "duckdb")
    return {package: importlib.metadata.version(package) for package in packages}


def materialize_commitments() -> dict[str, object]:
    hashes = {
        pack: hashlib.sha256(write_pack_manifest(pack, MANIFESTS).read_bytes()).hexdigest()
        for pack in "OPQRST"
    }
    commitment_path = MANIFESTS / "pack_U_commitment.json"
    encoded = json.dumps(final_commitment(), indent=2, sort_keys=True) + "\n"
    if commitment_path.exists() and commitment_path.read_text() != encoded:
        raise RuntimeError("sealed Pack U commitment changed")
    commitment_path.parent.mkdir(parents=True, exist_ok=True)
    commitment_path.write_text(encoded)
    return {"manifest_hashes": hashes, "final_commitment": final_commitment()}


def _fresh_model(name: str, seed: int) -> EffectModel:
    models = {model.name: model for model in candidate_models(seed)}
    return models[name]


def _evaluate(packs: str, model_name: str) -> list[V71WorldEvaluation]:
    rows: list[V71WorldEvaluation] = []
    for pack in packs:
        for spec in v71_pack_specs(pack):
            model = _fresh_model(model_name, spec.seed)
            try:
                rows.append(evaluate_candidate(spec, model))
            except Exception as exc:  # fail-closed benchmark row, never silent
                rows.append(
                    V71WorldEvaluation(
                        spec.world_id,
                        spec.family.value,
                        model_name,
                        "UNKNOWN_EVALUATION_FAILURE",
                        "ESTIMATION_OR_POLICY_FAILURE",
                        "BAU_OR_TEST",
                        "BAU",
                        "INSUFFICIENT",
                        False,
                        False,
                        False,
                        ("RUNTIME_ERROR",),
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        float("inf"),
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0,
                        0.0,
                        0.0,
                        1.0,
                        spec.treatment_cost,
                        spec.switching_cost,
                        f"{type(exc).__name__}: {exc}",
                    )
                )
    return rows


def _summary(rows: list[V71WorldEvaluation]) -> dict[str, Any]:
    material = [row for row in rows if row.oracle_taxonomy == "MATERIAL_OBSERVABLE_PERSONALIZATION"]
    nonmaterial = [row for row in rows if row.oracle_taxonomy == "NONMATERIAL_PERSONALIZATION"]
    unobservable = [
        row
        for row in rows
        if row.oracle_taxonomy == "MATERIAL_UNOBSERVABLE_PERSONALIZATION"
    ]
    unsupported = [
        row for row in rows if row.oracle_taxonomy == "UNSUPPORTED_PERSONALIZATION"
    ]
    homogeneous = [row for row in rows if row.family == "HOMOGENEOUS_POSITIVE"]
    null_harm = [row for row in rows if row.family in {"NULL", "GLOBALLY_HARMFUL"}]

    def mean(values: list[float]) -> float:
        return float(np.mean(values)) if values else 0.0

    return {
        "worlds": len(rows),
        "runtime_errors": sum(row.runtime_error is not None for row in rows),
        "unsupported_act_count": sum(row.unsupported_act for row in rows),
        "material_worlds": len(material),
        "material_positive_increment_rate": mean(
            [float(row.heldout_increment_over_static > 0) for row in material]
        ),
        "material_positive_lower_rate": mean(
            [float(row.heldout_increment_lower > 0) for row in material]
        ),
        "material_mean_increment": mean([row.heldout_increment_over_static for row in material]),
        "material_mean_lower": mean([row.heldout_increment_lower for row in material]),
        "material_mean_observable_capture": mean(
            [row.observable_oracle_capture for row in material]
        ),
        "material_fold_stability": mean([row.fold_positive_fraction for row in material]),
        "nonmaterial_personalization_rate": mean(
            [float(row.personalization_promoted) for row in nonmaterial]
        ),
        "unobservable_rejection_rate": mean(
            [float(not row.personalization_promoted) for row in unobservable]
        ),
        "unsupported_rejection_rate": mean(
            [
                float(not row.personalization_promoted and not row.unsupported_act)
                for row in unsupported
            ]
        ),
        "homogeneous_static_rate": mean(
            [float(row.selected_policy == "TREAT_ALL") for row in homogeneous]
        ),
        "homogeneous_personalization_rate": mean(
            [float(row.personalization_promoted) for row in homogeneous]
        ),
        "null_harm_personalization_rate": mean(
            [float(row.personalization_promoted) for row in null_harm]
        ),
        "null_harm_action_rate": mean([float(row.decision == "ACT") for row in null_harm]),
        "mean_calibration_rmse": mean([row.calibration_rmse for row in rows]),
        "act_count": sum(row.decision == "ACT" for row in rows),
        "bau_or_test_count": sum(row.decision == "BAU_OR_TEST" for row in rows),
        "avoid_count": sum(row.decision == "AVOID" for row in rows),
    }


def run_development() -> dict[str, object]:
    assert_clean_worktree()
    if VALIDATION_LOCK.exists():
        raise RuntimeError("validation has opened; development is permanently closed")
    commitment = materialize_commitments()
    tournament: dict[str, dict[str, Any]] = {}
    all_rows: dict[str, list[V71WorldEvaluation]] = {}
    for name in MODEL_NAMES:
        started = time.perf_counter()
        rows = _evaluate("OPQ", name)
        elapsed = time.perf_counter() - started
        summary = _summary(rows)
        summary["runtime_seconds"] = elapsed
        eligible = bool(
            summary["runtime_errors"] == 0
            and summary["unsupported_act_count"] == 0
            and summary["null_harm_personalization_rate"] <= 0.05
            and summary["nonmaterial_personalization_rate"] <= 0.10
        )
        summary["eligible"] = eligible
        tournament[name] = summary
        all_rows[name] = rows
    eligible_names = [name for name in MODEL_NAMES if tournament[name]["eligible"]]
    if not eligible_names:
        winner = None
    else:
        winner = max(
            eligible_names,
            key=lambda name: (
                tournament[name]["material_mean_increment"],
                tournament[name]["material_mean_lower"],
                tournament[name]["homogeneous_static_rate"],
                -tournament[name]["mean_calibration_rmse"],
                -tournament[name]["runtime_seconds"],
            ),
        )
    RESULTS.mkdir(parents=True, exist_ok=True)
    result_payload: dict[str, object] = {
        "stage": "DEVELOPMENT_O_P_Q",
        "source_commit": _git("rev-parse", "HEAD"),
        "tournament": tournament,
        "causal_forest": causal_forest_availability(),
        "winner": winner,
        "rows": {name: [row.to_dict() for row in rows] for name, rows in all_rows.items()},
    }
    (RESULTS / "development_tournament.json").write_text(
        json.dumps(result_payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    if winner is None:
        return result_payload
    freeze: dict[str, object] = {
        "schema_version": 1,
        "selected_model": winner,
        "selection_stage": "O_P_Q_ONLY",
        "selector_rule": (
            "hard safety eligibility then lexicographic material increment, lower bound, "
            "static fallback, calibration, runtime"
        ),
        "thresholds": {
            "materiality": 0.10,
            "material_success_rate": 0.75,
            "material_capture": 0.50,
            "nonmaterial_false_promotion": 0.05,
            "unobservable_rejection": 0.95,
            "homogeneous_static": 0.90,
            "null_harm_false_promotion": 0.05,
            "minimum_ess": 200,
        },
        "manifest_hashes": commitment["manifest_hashes"],
        "pack_u_commitment": commitment["final_commitment"],
        "development_source_commit": _git("rev-parse", "HEAD"),
        "source_tree_sha256": _source_tree_hash(),
        "dependency_versions": _dependency_versions(),
        "model_hyperparameters": {
            "forest_estimators": 100,
            "forest_max_depth": 7,
            "forest_min_samples_leaf": 30,
            "nuisance_cross_fit_folds": 3,
            "ridge_alpha": 2.0,
        },
        "python": sys.version,
        "platform": platform.platform(),
    }
    freeze["config_hash"] = _sha(freeze)
    encoded = json.dumps(freeze, indent=2, sort_keys=True) + "\n"
    if DEVELOPMENT_FREEZE.exists() and DEVELOPMENT_FREEZE.read_text() != encoded:
        raise RuntimeError("development selection freeze is immutable")
    DEVELOPMENT_FREEZE.write_text(encoded)
    source_freeze = {
        "schema_version": 1,
        "git_sha": _git("rev-parse", "HEAD"),
        "dirty": False,
        "source_tree_sha256": freeze["source_tree_sha256"],
        "development_config_hash": freeze["config_hash"],
        "manifest_hashes": commitment["manifest_hashes"],
        "dependencies": freeze["dependency_versions"],
        "python": sys.version,
        "platform": platform.platform(),
    }
    source_freeze["freeze_sha256"] = _sha(source_freeze)
    SOURCE_FREEZE.write_text(json.dumps(source_freeze, indent=2, sort_keys=True) + "\n")
    return result_payload


def _validation_gates(summary: dict[str, Any]) -> dict[str, bool]:
    return {
        "no_runtime_errors": summary["runtime_errors"] == 0,
        "unsupported_act_zero": summary["unsupported_act_count"] == 0,
        "material_positive_world_rate": summary["material_positive_increment_rate"] >= 0.75,
        "material_mean_lower_positive": summary["material_mean_lower"] > 0,
        "material_observable_capture": summary["material_mean_observable_capture"] >= 0.50,
        "material_fold_stability": summary["material_fold_stability"] >= 0.75,
        "nonmaterial_false_promotion": summary["nonmaterial_personalization_rate"] <= 0.05,
        "unobservable_rejection": summary["unobservable_rejection_rate"] >= 0.95,
        "unsupported_rejection": summary["unsupported_rejection_rate"] == 1.0,
        "homogeneous_static": summary["homogeneous_static_rate"] >= 0.90,
        "homogeneous_false_personalization": summary["homogeneous_personalization_rate"] <= 0.05,
        "null_harm_false_personalization": summary["null_harm_personalization_rate"] <= 0.05,
        "null_harm_act_zero": summary["null_harm_action_rate"] == 0,
    }


def run_validation() -> dict[str, object]:
    assert_clean_worktree()
    if VALIDATION_LOCK.exists():
        raise RuntimeError("V7.1 validation has already been opened")
    if not DEVELOPMENT_FREEZE.exists() or not SOURCE_FREEZE.exists():
        raise RuntimeError("development and source freeze must exist before validation opens")
    freeze = json.loads(DEVELOPMENT_FREEZE.read_text())
    if freeze["source_tree_sha256"] != _source_tree_hash():
        raise RuntimeError("policy source changed after development selection")
    selected_model = str(freeze["selected_model"])
    opened = {
        "opened_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": _git("rev-parse", "HEAD"),
        "source_tree_sha256": _source_tree_hash(),
        "selected_model": selected_model,
        "packs": ["R", "S", "T"],
    }
    opened["lock_sha256"] = _sha(opened)
    VALIDATION_LOCK.write_text(json.dumps(opened, indent=2, sort_keys=True) + "\n")
    started = time.perf_counter()
    rows = _evaluate("RST", selected_model)
    elapsed = time.perf_counter() - started
    summary = _summary(rows)
    summary["runtime_seconds"] = elapsed
    gates = _validation_gates(summary)
    payload: dict[str, object] = {
        "stage": "ONE_TIME_VALIDATION_R_S_T",
        "selected_model": selected_model,
        "source_tree_sha256": _source_tree_hash(),
        "summary": summary,
        "gates": gates,
        "overall_pass": all(gates.values()),
        "pack_u_status": "SEALED_NOT_MATERIALIZED",
        "rows": [row.to_dict() for row in rows],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "validation_results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    VALIDATION_REPORT.write_text(_validation_markdown(payload))
    return payload


def _validation_markdown(payload: dict[str, object]) -> str:
    gates = cast(dict[str, bool], payload["gates"])
    summary = cast(dict[str, Any], payload["summary"])
    lines = [
        "# Exergi V7.1 one-time validation",
        "",
        f"Overall: **{'PASS' if payload['overall_pass'] else 'FAIL'}**.",
        "Pack U remains `SEALED_NOT_MATERIALIZED`.",
        "",
        "## Frozen gates",
        "",
    ]
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in gates.items())
    lines.extend(
        [
            "",
            "## Key results",
            "",
            f"- selected model: `{payload['selected_model']}`",
            f"- material positive-world rate: {summary['material_positive_increment_rate']:.1%}",
            f"- mean material increment over static: {summary['material_mean_increment']:.4f}",
            f"- mean observable-oracle capture: {summary['material_mean_observable_capture']:.1%}",
            f"- unsupported ACT count: {summary['unsupported_act_count']}",
            f"- runtime: {summary['runtime_seconds']:.2f}s",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("materialize", "development", "validation"))
    args = parser.parse_args()
    if args.stage == "materialize":
        result = materialize_commitments()
    elif args.stage == "development":
        result = run_development()
    else:
        result = run_validation()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
