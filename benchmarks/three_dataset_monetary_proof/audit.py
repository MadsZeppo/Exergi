"""Read-only integrity audit for the two persisted randomized monetary proofs."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
V8 = ROOT / "benchmarks/ecommerce_decision_layer_v8_hillstrom_proof"
V9 = ROOT / "benchmarks/ecommerce_decision_layer_v9_concealing_prices"


class ProofIntegrityError(RuntimeError):
    """Raised when an immutable proof no longer matches its persisted authority."""


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _unchanged_since(commit: str, path: Path) -> bool:
    relative = path.relative_to(ROOT).as_posix()
    result = subprocess.run(
        ["git", "diff", "--quiet", commit, "--", relative], cwd=ROOT, check=False
    )
    return result.returncode == 0


def _paths_unchanged_since(commit: str, paths: tuple[Path, ...]) -> bool:
    relative = [path.relative_to(ROOT).as_posix() for path in paths]
    result = subprocess.run(
        ["git", "diff", "--quiet", commit, "--", *relative], cwd=ROOT, check=False
    )
    return result.returncode == 0


def _is_ancestor(older: str, newer: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer], cwd=ROOT, check=False
    )
    return result.returncode == 0


def audit_immutable_proofs() -> dict[str, Any]:
    v8_result_path = V8 / "V8_VALIDATION_RESULT.json"
    v8_lock_path = V8 / "results/V8_VALIDATION_CONSUMED.json"
    v8_result = _json(v8_result_path)
    v8_lock = _json(v8_lock_path)
    v8_freeze = _json(V8 / "V8_FREEZE_MANIFEST.json")

    v9_result_path = V9 / "results/study3/V9_VALIDATION_RESULT.json"
    v9_lock_path = V9 / "results/study3/V9_VALIDATION_CONSUMED.json"
    v9_overall = _json(V9 / "V9_RESULT.json")
    v9_study = v9_overall["studies"]["study3"]
    v9_lock = _json(v9_lock_path)
    v9_freeze = _json(V9 / "V9_FREEZE_MANIFEST.json")
    v9_stats = _json(V9 / "results/study3/V9_VALIDATION_SUFFICIENT_STATISTICS.json")

    v8_checks = {
        "artifact_tree_unchanged_since_reveal_commit": _unchanged_since("0fa7944", V8),
        "consumed_lock_matches_result": v8_lock["result_sha256"] == _sha256(v8_result_path),
        "consumed_permanently": (
            v8_result["validation_permanently_consumed"]
            and not v8_lock["second_reveal_allowed"]
            and v8_lock["status"] == "VALIDATION_PERMANENTLY_CONSUMED"
        ),
        "development_selected_policy_matches_freeze": (
            v8_freeze["policy"] == "STATIC_MENS_EMAIL_FOR_ALL_ELIGIBLE_CUSTOMERS"
            and v8_result["development_comparison"]["net_uplift"] > 0.0
        ),
        "freeze_precedes_reveal": _is_ancestor(v8_result["freeze_commit"], "0fa7944"),
        "integrity_artifact_passed": v8_result["integrity"]["passed"],
        "no_post_treatment_features": not v8_result["feature_contract"][
            "post_treatment_features_used"
        ],
        "sealed_not_opened_by_v8": not v8_result["integrity"]["sealed_test_opened"],
    }

    v9_checks = {
        "artifact_tree_unchanged_since_reveal_commit": _unchanged_since("e4fefa9", V9),
        "consumed_lock_matches_result": v9_lock["result_sha256"] == _sha256(v9_result_path),
        "consumed_permanently": (
            v9_study["validation_consumed"]
            and not v9_lock["second_reveal_permitted"]
            and v9_lock["status"] == "V9_VALIDATION_PERMANENTLY_CONSUMED"
        ),
        "development_selected_policy_matches_freeze": (
            v9_study["development"]["selection"] == "AVOID_DELAYED_PRICE"
            and v9_study["frozen_policy"] == "AVOID_DELAYED_PRICE"
            and v9_freeze["studies"]["study3"]["policy"] == "AVOID_DELAYED_PRICE"
        ),
        "freeze_precedes_reveal": _is_ancestor(v9_overall["freeze_commit"], "e4fefa9"),
        "no_post_treatment_features": not v9_freeze["allowed_features"],
        "sealed_not_opened": not v9_study["sealed_test_opened"],
    }

    immutable_history = {
        "buy_baits_unchanged_since_checkpoint": _paths_unchanged_since(
            "1bd06ac",
            tuple(
                ROOT / "benchmarks/ecommerce_decision_layer_v7_2" / name
                for name in (
                    "BUY_BAITS_DEVELOPMENT_LOCK.json",
                    "BUY_BAITS_PROVENANCE_REPORT.md",
                    "BUY_BAITS_REPLICATION_REPORT.md",
                    "V7_2_BUY_BAITS_CHECKPOINT.md",
                    "buy_baits_audit.py",
                    "buy_baits_development.py",
                    "manifests/buy_baits_split_manifest.json",
                    "results/buy_baits_development_tournament.json",
                    "results/buy_baits_forensic_audit.json",
                )
            ),
        ),
        "v13_unchanged_since_checkpoint": _unchanged_since(
            "a5936d8", ROOT / "benchmarks/ecommerce_decision_layer_v13_jtpa_personalized_value"
        ),
        "v14_unchanged_since_checkpoint": _unchanged_since(
            "753eb56", ROOT / "benchmarks/ecommerce_decision_layer_v14_multichannel_proof"
        ),
    }
    if not all((*v8_checks.values(), *v9_checks.values(), *immutable_history.values())):
        raise ProofIntegrityError("one or more immutable proof checks failed")

    delayed = v9_stats["revenue"]["delayed"]
    immediate = v9_stats["revenue"]["immediate"]
    delayed_mean = delayed["sum"] / delayed["n"]
    immediate_mean = immediate["sum"] / immediate["n"]
    protected_point = -v9_study["primary"]["point"]
    protected_lower = -v9_study["primary"]["upper_95"]
    protected_upper = -v9_study["primary"]["lower_95"]

    return {
        "audit_scope": "Persisted tracked artifacts and git history only; no raw outcomes read",
        "head": _git("rev-parse", "HEAD"),
        "immutable_history": immutable_history,
        "v8": {
            "checks": v8_checks,
            "decision": v8_freeze["policy"],
            "bau": v8_freeze["control_label"],
            "bau_value": v8_result["arm_statistics"]["No E-Mail"]["mean_net_revenue"],
            "exergi_value": v8_result["arm_statistics"]["Mens E-Mail"]["mean_net_revenue"],
            "incremental_value_per_customer": v8_result["primary"]["point"],
            "lower_95": v8_result["primary"]["lower_95"],
            "upper_95": v8_result["primary"]["upper_95"],
            "n": v8_result["analysis_population_n"],
            "p_value": v8_result["primary"]["two_sided_p_value"],
            "total_incremental_value": v8_result["primary"]["total_incremental_value"],
            "authority": v8_result["claim_authority"],
            "pass": v8_result["verdict"] == "PASS",
        },
        "v9_study3": {
            "checks": v9_checks,
            "decision": "SHOW_PRICE_IN_EMAIL / AVOID_DELAYED_PRICE",
            "bau": "HIDE_PRICE_UNTIL_PRODUCT_PAGE",
            "bau_value": delayed_mean,
            "exergi_value": immediate_mean,
            "incremental_protected_value_per_recipient": protected_point,
            "lower_95": protected_lower,
            "upper_95": protected_upper,
            "n": delayed["n"] + immediate["n"],
            "p_value": v9_study["secondary"]["assignment_randomization_p_value"],
            "total_protected_value": protected_point * (delayed["n"] + immediate["n"]),
            "authority": "REAL_RANDOMIZED_GROSS_REVENUE_AVOIDANCE",
            "pass": v9_study["status"] == "CONFIRMED_AVOID",
        },
    }


def write_audit(path: Path = HERE / "V8_V9_IMMUTABLE_AUDIT.json") -> dict[str, Any]:
    result = audit_immutable_proofs()
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    write_audit()
