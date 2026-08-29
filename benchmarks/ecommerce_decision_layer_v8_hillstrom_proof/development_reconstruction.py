"""Reconstruct the already-selected V8 policy using DEVELOPMENT only."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .estimators import (
    cross_fitted_aipw,
    difference_in_means,
    encode_pretreatment_features,
    lin_ancova,
)
from .integrity import (
    DEVELOPMENT,
    DEVELOPMENT_RESULT,
    EXPECTED_DEVELOPMENT_SHA256,
    ROOT,
    IntegrityError,
    require_pre_reveal_integrity,
    sha256_file,
)

CONFIG = ROOT / "FROZEN_ANALYSIS_CONFIG.json"
PRIOR_AUDIT = (
    ROOT.parent / "ecommerce_decision_layer_v7_2/results/hillstrom_static_development_audit.json"
)
PRIOR_POLICY = ROOT.parent / "ecommerce_decision_layer_v7_2/results/hillstrom_policy_hierarchy.json"
ALLOWED_FEATURES = (
    "recency",
    "history_segment",
    "history",
    "mens",
    "womens",
    "zip_code",
    "newbie",
    "channel",
)


def reconstruct(*, write: bool = True) -> dict[str, Any]:
    integrity = require_pre_reveal_integrity()
    config = json.loads(CONFIG.read_text())
    frame = pd.read_parquet(DEVELOPMENT)
    expected_columns = {*ALLOWED_FEATURES, "segment", "visit", "conversion", "spend", "unit_hash"}
    if set(frame.columns) != expected_columns:
        raise IntegrityError("unexpected DEVELOPMENT schema")
    if frame["unit_hash"].duplicated().any():
        raise IntegrityError("duplicate DEVELOPMENT randomized units")
    contrast = frame[frame["segment"].isin(("No E-Mail", "Mens E-Mail"))].copy()
    treatment = (contrast["segment"] == "Mens E-Mail").to_numpy(dtype=np.int64)
    spend = contrast["spend"].to_numpy(dtype=float)
    unit_hashes = contrast["unit_hash"].to_numpy(dtype=str)
    features, category_levels, feature_names = encode_pretreatment_features(contrast)
    email_cost = float(config["email_cost"])
    raw_gross = difference_in_means(spend, treatment, 0.0)
    raw_net = difference_in_means(spend, treatment, email_cost)
    ancova = lin_ancova(spend, treatment, features, email_cost)
    aipw_config = config["aipw"]
    aipw, _, folds = cross_fitted_aipw(
        spend,
        treatment,
        features,
        unit_hashes,
        email_cost,
        folds=int(aipw_config["folds"]),
        seed=int(aipw_config["seed"]),
        ridge_alpha=float(aipw_config["ridge_alpha"]),
    )
    expected = config["development_expected"]
    tolerance = float(expected["gross_uplift_absolute_tolerance"])
    if abs(raw_gross.point - float(expected["gross_uplift"])) > tolerance:
        raise IntegrityError("V8_INVALID_DEVELOPMENT_RECONSTRUCTION_MISMATCH")
    if abs(raw_net.point - float(expected["net_uplift"])) > tolerance:
        raise IntegrityError("V8_INVALID_DEVELOPMENT_RECONSTRUCTION_MISMATCH")
    prior_audit = json.loads(PRIOR_AUDIT.read_text())
    prior_policy = json.loads(PRIOR_POLICY.read_text())
    if prior_policy["selected_level"] != "BAU":
        raise IntegrityError("historical V7.2 policy hierarchy changed")
    tournament = prior_audit["estimator_tournament"]["estimators"]
    adjusted_direction = {
        name: float(tournament[name]["net_value_by_cost"]["0.05"]["point"])
        for name in ("ancova_hc3", "cuped_history", "cross_fitted_aipw")
    }
    if not all(value > 0 for value in adjusted_direction.values()):
        raise IntegrityError("historical adjusted DEVELOPMENT direction mismatch")
    hierarchy = prior_policy["levels"]
    complex_promoted = any(
        row["promoted"]
        for row in hierarchy
        if row["level"] in {"supported_segment_policy", "supported_personalized_policy"}
    )
    if complex_promoted:
        raise IntegrityError("personalized challenger unexpectedly promoted over static")
    nonzero = frame.loc[frame["spend"] > 0, "spend"].to_numpy(dtype=float)
    caps = {
        "p99": float(np.quantile(nonzero, 0.99)),
        "p99_5": float(np.quantile(nonzero, 0.995)),
    }
    if caps != config["heavy_tail"]["nonzero_caps_from_development"]:
        raise IntegrityError("frozen DEVELOPMENT nonzero cap mismatch")
    result: dict[str, Any] = {
        "status": "V8_DEVELOPMENT_RECONSTRUCTION_MATCH",
        "development_rows": len(frame),
        "contrast_rows": len(contrast),
        "arm_counts": contrast["segment"].value_counts().sort_index().to_dict(),
        "development_parquet_sha256": sha256_file(DEVELOPMENT),
        "expected_development_parquet_sha256": EXPECTED_DEVELOPMENT_SHA256,
        "integrity": integrity.as_dict(),
        "policy_reconstructed_not_reselected": config["static_policy"],
        "raw_gross": raw_gross.as_dict(),
        "raw_net_at_declared_cost": raw_net.as_dict(),
        "lin_ancova_net": ancova.as_dict(),
        "cross_fitted_aipw_net": aipw.as_dict(),
        "adjusted_historical_directions": adjusted_direction,
        "personalized_challenger_promoted": complex_promoted,
        "category_levels": category_levels,
        "feature_names": feature_names,
        "cross_fit_fold_counts": {
            str(fold): int(np.sum(folds == fold)) for fold in range(int(aipw_config["folds"]))
        },
        "nonzero_development_caps": caps,
        "validation_opened": False,
        "sealed_test_opened": False,
    }
    if write:
        DEVELOPMENT_RESULT.parent.mkdir(parents=True, exist_ok=True)
        DEVELOPMENT_RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        _write_report(result)
    return result


def _write_report(result: dict[str, Any]) -> None:
    gross = result["raw_gross"]
    net = result["raw_net_at_declared_cost"]
    lines = [
        "# V8 Development Reconstruction",
        "",
        "Status: **MATCH — policy reconstructed, not reselected**.",
        "",
        f"The immutable DEVELOPMENT materialization contains {result['development_rows']:,} rows. ",
        "Only DEVELOPMENT was read; VALIDATION and SEALED_TEST remained closed.",
        "",
        f"- Frozen policy: `{result['policy_reconstructed_not_reselected']}`",
        f"- Raw gross Mens-minus-control uplift: `${gross['point']:.12f}`",
        f"- Raw net uplift after the frozen $0.05 cost: `${net['point']:.12f}`",
        f"- Raw net 95% CI: `[${net['lower_95']:.12f}, ${net['upper_95']:.12f}]`",
        f"- Lin ANCOVA net point: `${result['lin_ancova_net']['point']:.12f}`",
        f"- Cross-fitted AIPW net point: `${result['cross_fitted_aipw_net']['point']:.12f}`",
        "- Personalized challenger promoted over static: no",
        "",
        "V7.2 remains historically INCONCLUSIVE under its broader stability contract. V8 does not",
        "rewrite that decision; it freezes the already-observed static Mens candidate for a",
        "narrower independent randomized confirmation.",
        "",
    ]
    (ROOT / "V8_DEVELOPMENT_RECONSTRUCTION.md").write_text("\n".join(lines))


if __name__ == "__main__":
    print(json.dumps(reconstruct(), indent=2, sort_keys=True))
