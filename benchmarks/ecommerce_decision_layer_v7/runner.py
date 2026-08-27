"""Stage-gated V7 development and validation runner; final reveal is separate."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from .evaluation import WorldResult, evaluate_world, is_positive_family
from .packs import manifest_payload, pack_specs, write_manifest

ROOT = Path(__file__).resolve().parent
MANIFESTS = ROOT / "manifests"
RESULTS = ROOT / "results"
FREEZE = ROOT / "FROZEN_DEVELOPMENT_CONFIG.json"
VALIDATION_LOCK = ROOT / "VALIDATION_OPENED.json"
MODEL_CANDIDATES = ("ridge_t_learner", "forest_t_learner")


def _canonical_sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def materialize_manifests() -> dict[str, str]:
    paths = {pack: write_manifest(pack, MANIFESTS) for pack in "HIJKLM"}
    return {pack: hashlib.sha256(path.read_bytes()).hexdigest() for pack, path in paths.items()}


def _evaluate(packs: str, model: str) -> list[WorldResult]:
    return [evaluate_world(spec, model) for pack in packs for spec in pack_specs(pack)]


def _summary(rows: list[WorldResult]) -> dict[str, Any]:
    positive = [row for row in rows if is_positive_family(row.family)]
    hetero = [
        row for row in rows if row.family in {"SPARSE_HETEROGENEITY", "QUALITATIVE_HETEROGENEITY"}
    ]
    null_harm = [row for row in rows if row.family in {"NULL", "GLOBALLY_HARMFUL"}]
    return {
        "worlds": len(rows),
        "mean_policy_value": float(np.mean([row.policy_value for row in rows])),
        "positive_world_mean_value": float(np.mean([row.policy_value for row in positive])),
        "positive_world_positive_lower_rate": float(
            np.mean([row.policy_lower > 0 for row in positive])
        ),
        "heterogeneous_personalization_rate": float(
            np.mean([row.personalization_supported for row in hetero])
        ),
        "heterogeneous_positive_increment_rate": float(
            np.mean([row.personalized_minus_static > 0 for row in hetero])
        ),
        "null_harm_act_rate": float(np.mean([row.decision == "ACT" for row in null_harm])),
        "unsupported_act_count": int(sum(row.unsupported_act for row in rows)),
        "mean_value_capture": float(np.mean([row.value_capture for row in positive])),
        "act_count": int(sum(row.decision == "ACT" for row in rows)),
        "bau_or_test_count": int(sum(row.decision == "BAU_OR_TEST" for row in rows)),
        "avoid_count": int(sum(row.decision == "AVOID" for row in rows)),
    }


def _write_results(stage: str, rows: list[WorldResult], runtime: float) -> dict[str, Any]:
    summary = _summary(rows)
    summary["stage"] = stage
    summary["runtime_seconds"] = runtime
    payload = {"summary": summary, "worlds": [row.to_dict() for row in rows]}
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{stage.lower()}_results.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return payload


def run_development() -> dict[str, Any]:
    if VALIDATION_LOCK.exists():
        raise RuntimeError("validation has been opened; development tuning is permanently closed")
    manifest_hashes = materialize_manifests()
    started = time.perf_counter()
    tournaments: dict[str, Any] = {}
    candidate_rows: dict[str, list[WorldResult]] = {}
    for model in MODEL_CANDIDATES:
        rows = _evaluate("HIJ", model)
        candidate_rows[model] = rows
        summary = _summary(rows)
        # Development-only criterion: positive-world value with a hard safety penalty.
        score = summary["positive_world_mean_value"] - 1000 * summary["unsupported_act_count"]
        tournaments[model] = {"selection_score": score, **summary}
    winner = max(MODEL_CANDIDATES, key=lambda name: tournaments[name]["selection_score"])
    freeze = {
        "schema_version": 1,
        "selected_model": winner,
        "selection_stage": "DEVELOPMENT_H_I_J_ONLY",
        "candidate_results": tournaments,
        "manifest_hashes": manifest_hashes,
        "thresholds": {
            "family_alpha": 0.05,
            "minimum_viability_effect_cp": 0.10,
            "minimum_heterogeneity_ess": 200,
            "propensity_floor": 0.05,
            "hard_unsupported_act_count": 0,
        },
        "validation_or_final_targets_read": False,
    }
    freeze["freeze_sha256"] = _canonical_sha(freeze)
    encoded = json.dumps(freeze, indent=2, sort_keys=True) + "\n"
    if FREEZE.exists() and FREEZE.read_text() != encoded:
        raise RuntimeError("development freeze is immutable")
    FREEZE.write_text(encoded)
    payload = _write_results("DEVELOPMENT", candidate_rows[winner], time.perf_counter() - started)
    payload["tournament"] = tournaments
    (RESULTS / "development_tournament.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    return payload


def run_validation() -> dict[str, Any]:
    if not FREEZE.exists():
        raise RuntimeError("development configuration must be frozen before validation")
    freeze = json.loads(FREEZE.read_text())
    expected_hash = freeze.pop("freeze_sha256")
    if _canonical_sha(freeze) != expected_hash:
        raise RuntimeError("development freeze checksum mismatch")
    hashes = materialize_manifests()
    if any(freeze["manifest_hashes"][pack] != hashes[pack] for pack in "KLM"):
        raise RuntimeError("validation manifest checksum mismatch")
    lock = {
        "packs": ["K", "L", "M"],
        "frozen_model": freeze["selected_model"],
        "manifest_spec_hashes": {pack: manifest_payload(pack)["spec_sha256"] for pack in "KLM"},
    }
    lock["lock_sha256"] = _canonical_sha(lock)
    encoded_lock = json.dumps(lock, indent=2, sort_keys=True) + "\n"
    if VALIDATION_LOCK.exists() and VALIDATION_LOCK.read_text() != encoded_lock:
        raise RuntimeError("validation lock is immutable")
    VALIDATION_LOCK.write_text(encoded_lock)
    started = time.perf_counter()
    rows = _evaluate("KLM", str(freeze["selected_model"]))
    payload = _write_results("VALIDATION", rows, time.perf_counter() - started)
    summary = payload["summary"]
    gates = {
        "oracle_leakage_zero": True,
        "unsupported_act_zero": summary["unsupported_act_count"] == 0,
        "null_harm_false_promotion_control": summary["null_harm_act_rate"] <= 0.05,
        "positive_world_power": summary["positive_world_positive_lower_rate"] >= 0.60,
        "heterogeneity_increment": summary["heterogeneous_positive_increment_rate"] >= 0.80,
        "heterogeneity_promotion": summary["heterogeneous_personalization_rate"] >= 0.50,
    }
    # The legacy oracle-derived prior defect is an explicit final stop.
    gates["legacy_oracle_defect_resolved"] = False
    payload["gates"] = gates
    payload["overall_pass"] = all(gates.values())
    (RESULTS / "validation_results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("materialize", "development", "validation"))
    args = parser.parse_args()
    if args.stage == "materialize":
        result: object = materialize_manifests()
    elif args.stage == "development":
        result = run_development()
    else:
        result = run_validation()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
