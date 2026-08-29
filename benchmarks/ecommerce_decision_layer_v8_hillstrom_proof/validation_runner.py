"""Mechanical, fail-closed, one-shot Hillstrom VALIDATION runner."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from decision_engine.economic_policy_v72.splits import stable_unit_hash

from .estimators import (
    arm_stratified_bootstrap,
    cross_fitted_aipw,
    difference_in_means,
    encode_pretreatment_features,
    lin_ancova,
    permutation_p_value,
    winsorized_difference,
)
from .integrity import (
    BUY_BAITS_LOCK,
    CONSUMED_LOCK,
    DEVELOPMENT_RESULT,
    FREEZE_MANIFEST,
    RAW,
    RESULTS,
    REVEAL_START,
    ROOT,
    VALIDATION_RESULT,
    IntegrityError,
    current_head,
    load_manifest,
    require_pre_reveal_integrity,
    sha256_file,
    v8_worktree_is_clean,
    verify_frozen_sources,
)
from .report import write_reports

EXPECTED_COLUMNS = (
    "recency",
    "history_segment",
    "history",
    "mens",
    "womens",
    "zip_code",
    "newbie",
    "channel",
    "segment",
    "visit",
    "conversion",
    "spend",
)
NUMERIC = ("recency", "history", "mens", "womens", "newbie")
RELEVANT_ARMS = ("No E-Mail", "Mens E-Mail")


@dataclass(frozen=True)
class OneShotFiles:
    reveal_start: Path
    result: Path
    consumed: Path


@dataclass(frozen=True)
class RevealAuthorization:
    reveal_start: Path
    nonce: str


DEFAULT_ONE_SHOT_FILES = OneShotFiles(REVEAL_START, VALIDATION_RESULT, CONSUMED_LOCK)


def _exclusive_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def begin_reveal(files: OneShotFiles, payload: dict[str, Any]) -> RevealAuthorization:
    if files.reveal_start.exists() or files.result.exists() or files.consumed.exists():
        raise IntegrityError("Hillstrom VALIDATION has already been consumed")
    nonce = sha256_file(FREEZE_MANIFEST) if FREEZE_MANIFEST.exists() else "fixture-freeze"
    _exclusive_json(files.reveal_start, {**payload, "nonce": nonce, "consumed_on_start": True})
    return RevealAuthorization(files.reveal_start, nonce)


def _assert_authorized(authorization: RevealAuthorization) -> None:
    if not authorization.reveal_start.exists():
        raise IntegrityError("validation outcome access requires reveal-start lock")
    record = json.loads(authorization.reveal_start.read_text())
    if record.get("nonce") != authorization.nonce or not record.get("consumed_on_start"):
        raise IntegrityError("invalid reveal authorization")


def parse_validation_rows(authorization: RevealAuthorization) -> pd.DataFrame:
    """Read only manifest-selected VALIDATION rows after the permanent lock exists."""
    _assert_authorized(authorization)
    manifest = load_manifest()
    validation_hashes = set(manifest["unit_hashes"]["VALIDATION"])
    sealed_hashes = set(manifest["unit_hashes"]["SEALED_TEST"])
    row_zero = stable_unit_hash("hillstrom", "row-0")
    records: list[dict[str, Any]] = []
    with RAW.open("rb") as handle:
        iterator = iter(handle)
        header = tuple(next(csv.reader([next(iterator).decode("utf-8")])))
        if header != EXPECTED_COLUMNS:
            raise IntegrityError("unexpected raw Hillstrom schema")
        positions = {name: index for index, name in enumerate(header)}
        for row_id, raw_line in enumerate(iterator):
            unit_hash = stable_unit_hash("hillstrom", f"row-{row_id}")
            if unit_hash not in validation_hashes:
                continue
            if unit_hash in sealed_hashes or unit_hash == row_zero:
                raise IntegrityError("SEALED_TEST or quarantined row reached validation parser")
            values = next(csv.reader(io.StringIO(raw_line.decode("utf-8"))))
            if len(values) != len(header):
                raise IntegrityError(f"malformed validation row {row_id}")
            record: dict[str, Any] = {
                "unit_hash": unit_hash,
                "segment": values[positions["segment"]],
            }
            for feature in (*NUMERIC, "history_segment", "zip_code", "channel"):
                record[feature] = values[positions[feature]]
            if record["segment"] in RELEVANT_ARMS:
                record["spend"] = values[positions["spend"]]
            else:
                record["spend"] = None
            records.append(record)
    frame = pd.DataFrame.from_records(records)
    if len(frame) != manifest["row_counts"]["VALIDATION"]:
        raise IntegrityError("validation row count differs from frozen manifest")
    if frame["unit_hash"].duplicated().any():
        raise IntegrityError("duplicate randomized unit in validation")
    if set(frame["segment"].unique()) != {"No E-Mail", "Mens E-Mail", "Womens E-Mail"}:
        raise IntegrityError("unexpected validation randomized arm labels")
    observed_counts = frame["segment"].value_counts().to_dict()
    if observed_counts != manifest["treatment_counts"]["VALIDATION"]:
        raise IntegrityError("validation arm counts differ from frozen manifest")
    contrast = frame[frame["segment"].isin(RELEVANT_ARMS)].copy()
    for column in NUMERIC:
        contrast[column] = pd.to_numeric(contrast[column], errors="raise")
    contrast["spend"] = pd.to_numeric(contrast["spend"], errors="raise")
    if contrast["spend"].isna().any():
        raise IntegrityError("missing spend in primary randomized population")
    return contrast.reset_index(drop=True)


def _arm_statistics(spend: np.ndarray, treatment: np.ndarray, cost: float) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for arm, label in ((0, "No E-Mail"), (1, "Mens E-Mail")):
        values = spend[treatment == arm]
        net = values - (cost if arm == 1 else 0.0)
        purchasers = values > 0
        output[label] = {
            "n": len(values),
            "spend_sum": float(values.sum()),
            "mean_spend": float(values.mean()),
            "spend_variance": float(values.var(ddof=1)),
            "mean_net_revenue": float(net.mean()),
            "zero_count": int(np.sum(values == 0)),
            "purchaser_count": int(purchasers.sum()),
            "purchaser_rate": float(purchasers.mean()),
            "revenue_per_purchaser": float(values[purchasers].mean()) if purchasers.any() else 0.0,
            "maximum_spend": float(values.max()),
        }
    return output


def _heavy_tail_diagnostics(
    spend: np.ndarray,
    treatment: np.ndarray,
    unit_hashes: np.ndarray,
    cost: float,
    config: dict[str, Any],
) -> dict[str, Any]:
    winsorized = {
        name: winsorized_difference(spend, treatment, cost, float(cap)).as_dict()
        for name, cap in config["heavy_tail"]["nonzero_caps_from_development"].items()
    }
    order = np.argsort(spend)[::-1]
    leave_top: dict[str, Any] = {}
    for k in config["heavy_tail"]["leave_top_k"]:
        keep = np.ones(len(spend), dtype=bool)
        keep[order[: int(k)]] = False
        leave_top[str(k)] = difference_in_means(spend[keep], treatment[keep], cost).as_dict()
    n_t, n_c = int(np.sum(treatment == 1)), int(np.sum(treatment == 0))
    top = []
    for index in order[:10]:
        arm = int(treatment[index])
        signed = (spend[index] - cost) / n_t if arm == 1 else -spend[index] / n_c
        top.append(
            {
                "unit_hash": str(unit_hashes[index]),
                "arm": "Mens E-Mail" if arm == 1 else "No E-Mail",
                "spend": float(spend[index]),
                "signed_point_contribution": float(signed),
            }
        )
    return {
        "winsorization_caps_source": "DEVELOPMENT nonzero outcomes only",
        "winsorized": winsorized,
        "leave_top": leave_top,
        "top_observation_influence": top,
        "full_distribution_p99_prohibited_reason": (
            "zero inflation can make the full-distribution P99 cap equal zero, mechanically "
            "destroying the marginal mean economic estimand"
        ),
    }


def analyze_validation(
    frame: pd.DataFrame, config: dict[str, Any], development: dict[str, Any]
) -> dict[str, Any]:
    treatment = (frame["segment"] == "Mens E-Mail").to_numpy(dtype=np.int64)
    spend = frame["spend"].to_numpy(dtype=float)
    unit_hashes = frame["unit_hash"].to_numpy(dtype=str)
    cost = float(config["email_cost"])
    features, levels, feature_names = encode_pretreatment_features(
        frame, development["category_levels"]
    )
    primary = difference_in_means(spend, treatment, cost)
    primary_dict = primary.as_dict()
    z = primary.point / primary.standard_error
    primary_dict["two_sided_p_value"] = float(2 * norm.sf(abs(z)))
    primary_dict["total_incremental_value"] = float(primary.point * len(frame))
    ancova = lin_ancova(spend, treatment, features, cost)
    aipw_config = config["aipw"]
    aipw, score, fold_ids = cross_fitted_aipw(
        spend,
        treatment,
        features,
        unit_hashes,
        cost,
        folds=int(aipw_config["folds"]),
        seed=int(aipw_config["seed"]),
        ridge_alpha=float(aipw_config["ridge_alpha"]),
    )
    permutation = config["permutation"]
    randomization_p = permutation_p_value(
        spend,
        treatment,
        cost,
        replicates=int(permutation["replicates"]),
        seed=int(permutation["seed"]),
    )
    bootstrap_config = config["bootstrap"]
    bootstrap, bootstrap_values = arm_stratified_bootstrap(
        spend,
        treatment,
        cost,
        replicates=int(bootstrap_config["replicates"]),
        seed=int(bootstrap_config["seed"]),
    )
    arm_stats = _arm_statistics(spend, treatment, cost)
    purchaser_rate_difference = (
        arm_stats["Mens E-Mail"]["purchaser_rate"] - arm_stats["No E-Mail"]["purchaser_rate"]
    )
    verdict = "PASS" if primary.point > 0 and primary.lower_95 > 0 else "FAIL"
    return {
        "verdict": verdict,
        "analysis_population_n": len(frame),
        "primary": primary_dict,
        "arm_statistics": arm_stats,
        "secondary": {
            "lin_ancova": ancova.as_dict(),
            "cross_fitted_aipw": {
                **aipw.as_dict(),
                "known_propensity": 0.5,
                "fold_counts": {
                    str(fold): int(np.sum(fold_ids == fold))
                    for fold in range(int(aipw_config["folds"]))
                },
                "influence_score_standard_deviation": float(score.std(ddof=1)),
            },
            "randomization_inference": {
                "two_sided_p_value": randomization_p,
                "replicates": int(permutation["replicates"]),
                "seed": int(permutation["seed"]),
                "group_size_preserved": True,
            },
            "arm_stratified_bootstrap": {
                **bootstrap.as_dict(),
                "replicates": int(bootstrap_config["replicates"]),
                "valid_replicates": len(bootstrap_values),
                "seed": int(bootstrap_config["seed"]),
            },
            "purchaser_decomposition": {
                "purchaser_rate_difference": float(purchaser_rate_difference),
                "mens_revenue_per_purchaser": arm_stats["Mens E-Mail"]["revenue_per_purchaser"],
                "control_revenue_per_purchaser": arm_stats["No E-Mail"]["revenue_per_purchaser"],
            },
            "heavy_tail": _heavy_tail_diagnostics(spend, treatment, unit_hashes, cost, config),
        },
        "feature_contract": {
            "category_levels": levels,
            "encoded_feature_names": feature_names,
            "post_treatment_features_used": [],
        },
    }


def dry_run() -> dict[str, Any]:
    integrity = require_pre_reveal_integrity()
    if not FREEZE_MANIFEST.exists():
        raise IntegrityError("validation dry-run requires a freeze manifest")
    freeze = json.loads(FREEZE_MANIFEST.read_text())
    verify_frozen_sources(freeze)
    result = {
        "status": "V8_DRY_RUN_VALIDATION_OUTCOMES_NOT_READ",
        "integrity": integrity.as_dict(),
        "freeze_verified": True,
        "validation_outcome_parser_called": False,
        "validation_opened": False,
        "sealed_test_opened": False,
    }
    (RESULTS / "V8_PRE_REVEAL_DRY_RUN.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def run_validation(freeze_commit: str) -> dict[str, Any]:
    integrity = require_pre_reveal_integrity()
    if current_head() != freeze_commit:
        raise IntegrityError("authorized freeze commit is not current HEAD")
    if not v8_worktree_is_clean():
        raise IntegrityError("frozen V8 files have uncommitted changes")
    freeze = json.loads(FREEZE_MANIFEST.read_text())
    verify_frozen_sources(freeze)
    config = json.loads((ROOT / "FROZEN_ANALYSIS_CONFIG.json").read_text())
    development = json.loads(DEVELOPMENT_RESULT.read_text())
    start_payload = {
        "status": "VALIDATION_PERMANENTLY_CONSUMED_ON_REVEAL_START",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "freeze_commit": freeze_commit,
        "freeze_manifest_sha256": sha256_file(FREEZE_MANIFEST),
        "source_tree_sha256": freeze["source_tree_sha256"],
    }
    authorization = begin_reveal(DEFAULT_ONE_SHOT_FILES, start_payload)
    try:
        frame = parse_validation_rows(authorization)
        analysis = analyze_validation(frame, config, development)
        sufficient = {
            "analysis_population_n": analysis["analysis_population_n"],
            "arm_statistics": analysis["arm_statistics"],
            "primary": analysis["primary"],
        }
        (RESULTS / "V8_VALIDATION_SUFFICIENT_STATISTICS.json").write_text(
            json.dumps(sufficient, indent=2, sort_keys=True) + "\n"
        )
        claim_contract = json.loads((ROOT / "CLAIM_CONTRACT.json").read_text())
        result = {
            **analysis,
            "schema_version": 1,
            "status": f"V8_HILLSTROM_RANDOMIZED_NET_REVENUE_PROOF_{analysis['verdict']}",
            "freeze_commit": freeze_commit,
            "freeze_manifest_sha256": sha256_file(FREEZE_MANIFEST),
            "source_tree_sha256": freeze["source_tree_sha256"],
            "development_comparison": {
                "gross_uplift": development["raw_gross"]["point"],
                "net_uplift": development["raw_net_at_declared_cost"]["point"],
            },
            "integrity": {
                **integrity.as_dict(),
                "frozen_sources_verified": True,
                "randomization_unit_equals_analysis_unit": True,
                "post_treatment_filtering": False,
                "sealed_test_opened": False,
                "buy_baits_lock_sha256": sha256_file(BUY_BAITS_LOCK),
            },
            "claim_authority": claim_contract["authority"],
            "claim_text": (
                claim_contract["allowed_claim_on_pass"]
                if analysis["verdict"] == "PASS"
                else (
                    "Hillstrom did not independently confirm the development-selected action. "
                    "Exergi remains shadow-only, and the next evidence must come from a new "
                    "randomized economic dataset or a merchant-approved prospective experiment."
                )
            ),
            "validation_permanently_consumed": True,
            "sealed_test_untouched_by_v8": True,
            "sealed_test_historically_quarantined": True,
            "buy_baits_unchanged": True,
            "completed_at_utc": datetime.now(UTC).isoformat(),
        }
        _exclusive_json(VALIDATION_RESULT, result)
        _exclusive_json(
            CONSUMED_LOCK,
            {
                "status": "VALIDATION_PERMANENTLY_CONSUMED",
                "freeze_commit": freeze_commit,
                "result_sha256": sha256_file(VALIDATION_RESULT),
                "completed_at_utc": result["completed_at_utc"],
                "second_reveal_allowed": False,
            },
        )
        write_reports()
        if analysis["verdict"] != "PASS":
            (ROOT / "V8_FAILURE_REPORT.md").write_text(
                "# V8 Failure Report\n\n"
                "The frozen primary randomized mean comparison did not satisfy both a positive "
                "point estimate and a strictly positive two-sided 95% lower confidence bound. "
                "No alternative estimator, subgroup, action, cost, alpha, split, or SEALED_TEST "
                "fallback may repair this result.\n"
            )
        return result
    except Exception as error:
        failure = {
            "status": "V8_HILLSTROM_RANDOMIZED_NET_REVENUE_PROOF_INVALID",
            "validation_permanently_consumed": True,
            "error_type": type(error).__name__,
            "error": str(error),
            "freeze_commit": freeze_commit,
            "failed_at_utc": datetime.now(UTC).isoformat(),
        }
        if not CONSUMED_LOCK.exists():
            _exclusive_json(CONSUMED_LOCK, failure)
        (ROOT / "V8_FAILURE_REPORT.md").write_text(
            "# V8 Integrity Failure\n\n"
            f"Validation was permanently consumed after reveal-start, but analysis failed: "
            f"`{type(error).__name__}: {error}`. The split cannot be reopened.\n"
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--reveal", action="store_true")
    parser.add_argument("--freeze-commit")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(dry_run(), indent=2, sort_keys=True))
        return
    if not args.freeze_commit:
        parser.error("--reveal requires --freeze-commit")
    print(json.dumps(run_validation(args.freeze_commit), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
