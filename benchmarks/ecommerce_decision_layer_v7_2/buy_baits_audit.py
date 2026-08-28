"""Forensic, pre-model audit of the official Buy Baits V1 package.

This is the only V7.2 program allowed to inspect the complete raw outcome table. It
produces aggregate replication evidence and a DEVELOPMENT-only ignored parquet.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2, chisquare

from decision_engine.datasets.buy_baits import (
    ACTION_GOVERNANCE,
    DATA_COLUMNS,
    ENTERPRISE_ALLOWED_ARMS,
    SCIENTIFIC_ALL_ARMS,
    TREATMENT_LABELS,
    VARIABLE_TIMING,
    development_frame_from_audit,
    read_assignment_only,
)
from decision_engine.economic_policy_v72.splits import (
    build_split_manifest,
    sha256_file,
    write_manifest_immutable,
)

ROOT = Path(__file__).resolve().parent
RAW_ZIP = Path("data/raw/buy_baits/198781-V1.zip")
STAGING = Path("data/processed/buy_baits/198781-V1")
DATA = STAGING / "data/data.dta"
EXPECTED_ZIP_SHA256 = "3242238801aa40f5802e356d6a5d8cc108ccce9044be6586709017684a1642bc"
SPLIT_SEED = 72_2001


def _cluster_ols(
    y: np.ndarray, columns: Sequence[np.ndarray], groups: np.ndarray
) -> dict[str, Any]:
    valid = np.isfinite(y)
    x = np.column_stack([np.ones(len(y)), *columns])[valid].astype(float)
    outcome = y[valid].astype(float)
    cluster = groups[valid]
    xtx_inverse = np.linalg.pinv(x.T @ x)
    beta = xtx_inverse @ x.T @ outcome
    residual = outcome - x @ beta
    _, inverse = np.unique(cluster, return_inverse=True)
    scores = np.zeros((int(inverse.max()) + 1, x.shape[1]))
    np.add.at(scores, inverse, x * residual[:, None])
    meat = scores.T @ scores
    n, k, g = len(outcome), x.shape[1], len(scores)
    correction = (g / (g - 1)) * ((n - 1) / (n - k))
    covariance = correction * xtx_inverse @ meat @ xtx_inverse
    return {
        "n": n,
        "coefficients": beta.tolist(),
        "cluster_standard_errors": np.sqrt(np.maximum(np.diag(covariance), 0)).tolist(),
    }


def _dummy_columns(treatment: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "auto": treatment == 1,
        "rebate10": np.isin(treatment, [2, 3, 4]),
        "reminder10": np.isin(treatment, [3, 4]),
        "announce10": treatment == 4,
        "rebate15": np.isin(treatment, [5, 6, 7]),
        "reminder15": np.isin(treatment, [6, 7]),
        "announce15": treatment == 7,
    }


def _regression(
    y: np.ndarray,
    names: Sequence[str],
    dummies: dict[str, np.ndarray],
    ids: np.ndarray,
) -> dict[str, Any]:
    result = _cluster_ols(y, [dummies[name] for name in names], ids)
    result["terms"] = ["constant", *names]
    return result


def _arm_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for arm, group in frame.groupby("treatment", sort=True):
        records.append(
            {
                "arm": int(arm),
                "label": TREATMENT_LABELS[int(arm)],
                "rows": int(len(group)),
                "randomized_units": int(group["id"].nunique()),
                "empirical_unit_propensity": float(group["id"].nunique() / frame["id"].nunique()),
                "purchases": int(group["purchase"].sum()),
                "purchase_rate_per_row": float(group["purchase"].mean()),
                "redemptions": int(group["red"].fillna(0).sum()),
                "profit_observed_rows": int(group["profit"].notna().sum()),
                "purchasevalue_observed_rows": int(group["purchasevalue"].notna().sum()),
            }
        )
    return records


def audit(source_commit: str, source_tree_sha256: str) -> dict[str, Any]:
    if sha256_file(RAW_ZIP) != EXPECTED_ZIP_SHA256:
        raise RuntimeError("official Buy Baits ZIP checksum mismatch")
    assignment = read_assignment_only(DATA)
    manifest = build_split_manifest(
        dataset="buy_baits_v1",
        dataset_path=DATA,
        unit_ids=assignment.unit_id.tolist(),
        treatments=[str(value) for value in assignment.treatment],
        split_seed=SPLIT_SEED,
        source_commit=source_commit,
        source_tree_sha256=source_tree_sha256,
    )
    manifest_path = ROOT / "manifests/buy_baits_split_manifest.json"
    write_manifest_immutable(manifest, manifest_path)

    frame = pd.read_stata(DATA, convert_categoricals=False, preserve_dtypes=False)
    if tuple(frame.columns) != DATA_COLUMNS:
        raise RuntimeError("official data schema differs from the audited contract")
    development = development_frame_from_audit(frame, set(manifest.unit_hashes["DEVELOPMENT"]))
    development_path = Path("data/processed/buy_baits/v7_2/development.parquet")
    development_path.parent.mkdir(parents=True, exist_ok=True)
    development.to_parquet(development_path, index=False)

    units = frame.drop_duplicates("id")
    counts = units["treatment"].value_counts().sort_index().to_numpy()
    srm = chisquare(counts, np.full(8, len(units) / 8))
    device_table = pd.crosstab(units["treatment"], units["device"])
    observed = device_table.to_numpy(dtype=float)
    expected = (
        observed.sum(axis=1, keepdims=True)
        @ observed.sum(axis=0, keepdims=True)
        / observed.sum()
    )
    device_statistic = float(np.sum((observed - expected) ** 2 / expected))
    device_df = int((observed.shape[0] - 1) * (observed.shape[1] - 1))

    treatment = frame["treatment"].to_numpy(dtype=int)
    ids = frame["id"].to_numpy()
    dummies = _dummy_columns(treatment)
    table1_names = (
        "auto",
        "rebate10",
        "reminder10",
        "announce10",
        "rebate15",
        "reminder15",
        "announce15",
    )
    table1_purchase = _regression(frame["purchase"].to_numpy(float), table1_names, dummies, ids)
    noncontrol = treatment != 8
    table1_redemption = _regression(
        frame["red"].to_numpy(float)[noncontrol],
        ("rebate10", "reminder10", "announce10", "rebate15", "reminder15", "announce15"),
        {name: values[noncontrol] for name, values in dummies.items()},
        ids[noncontrol],
    )

    table2: dict[str, Any] = {}
    for outcome_name in ("purchasevalue", "profit"):
        outcome = frame[outcome_name].to_numpy(float).copy()
        outcome[(frame["purchase"].to_numpy() != 1) & ~np.isfinite(outcome)] = 0.0
        if outcome_name == "profit":
            outcome[(frame["purchase"].to_numpy() == 1) & (outcome == 0)] = np.nan
        control_mean = float(np.nanmean(outcome[treatment == 8]))
        normalized = outcome / control_mean
        table2[outcome_name] = {
            "control_mean": control_mean,
            "pooled": _regression(normalized, ("auto", "rebate10", "rebate15"), dummies, ids),
            "reminders": _regression(
                normalized,
                ("auto", "rebate10", "reminder10", "rebate15", "reminder15"),
                dummies,
                ids,
            ),
        }

    sizes = frame.groupby("id").size()
    treatment_per_id = frame.groupby("id")["treatment"].nunique()
    purchase = frame["purchase"].eq(1)
    code_hashes = {
        path.name: sha256_file(path) for path in sorted((STAGING / "code").glob("*.do"))
    }
    result: dict[str, Any] = {
        "status": "AUDIT_PASS_WITH_CLAIM_DOWNGRADE",
        "source": {
            "archive": str(RAW_ZIP),
            "archive_sha256": sha256_file(RAW_ZIP),
            "archive_mode": oct(RAW_ZIP.stat().st_mode & 0o777),
            "data_sha256": sha256_file(DATA),
            "readme_sha256": sha256_file(STAGING / "README.pdf"),
            "replication_code_sha256": code_hashes,
        },
        "design": {
            "randomization_unit": "HTTP cookie / website visitor",
            "known_propensity_each_arm": 0.125,
            "period": "14 anonymized date codes; calendar dates unavailable in package",
            "outcome_window": (
                "not precisely documented; fail-closed UNKNOWN beyond observed experiment records"
            ),
            "scientific_all_arms": list(SCIENTIFIC_ALL_ARMS),
            "enterprise_allowed_arms": list(ENTERPRISE_ALLOWED_ARMS),
            "governance": {str(key): value.value for key, value in ACTION_GOVERNANCE.items()},
            "governance_rule": (
                "Only control, automatic rebate, and pre-announced reminder mechanics are "
                "enterprise-allowed; unannounced reminders are restricted and no-reminder "
                "claim frictions are prohibited, independent of outcomes."
            ),
        },
        "schema": {
            "rows": int(len(frame)),
            "randomized_units": int(frame["id"].nunique()),
            "columns": list(frame.columns),
            "timing": {name: value.value for name, value in VARIABLE_TIMING.items()},
            "dtypes": {name: str(dtype) for name, dtype in frame.dtypes.items()},
            "missing": {name: int(value) for name, value in frame.isna().sum().items()},
            "unique": {name: int(frame[name].nunique(dropna=True)) for name in frame.columns},
        },
        "assignment": {
            "arms": _arm_records(frame),
            "srm_chi_square": float(srm.statistic),
            "srm_p_value": float(srm.pvalue),
            "device_balance_chi_square": device_statistic,
            "device_balance_df": device_df,
            "device_balance_p_value": float(chi2.sf(device_statistic, device_df)),
            "treatment_contaminated_units": int(treatment_per_id.gt(1).sum()),
            "exact_duplicate_rows": int(frame.duplicated().sum()),
            "repeated_units": int(sizes.gt(1).sum()),
            "max_rows_per_unit": int(sizes.max()),
        },
        "outcomes": {
            "purchase_complete_rows": int(frame["purchase"].notna().sum()),
            "buyer_rows": int(purchase.sum()),
            "buyer_rows_missing_purchasevalue": int(
                (purchase & frame["purchasevalue"].isna()).sum()
            ),
            "buyer_rows_missing_profit": int((purchase & frame["profit"].isna()).sum()),
            "redemption_observed_buyer_rows": int(frame.loc[purchase, "red"].notna().sum()),
            "profit_definition": (
                "package-provided retailer profit aggregated by official code; COGS and "
                "variable-cost components are not separately available"
            ),
            "discount_cost": (
                "not a separate field; encoded, if at all, inside package-provided profit"
            ),
            "claim_authority": (
                "REAL_RANDOMIZED_ECONOMIC_VALUE_UNDER_OBSERVED_RETAILER_PROFIT; "
                "not contribution profit"
            ),
        },
        "replication": {
            "table1": {"purchase": table1_purchase, "redemption": table1_redemption},
            "table2": table2,
        },
        "split_manifest": {
            "path": str(manifest_path),
            "sha256": manifest.manifest_sha256,
            "row_counts": manifest.row_counts,
            "treatment_counts": manifest.treatment_counts,
            "development_materialization": str(development_path),
            "development_rows": int(len(development)),
            "development_units": int(development["unit_hash"].nunique()),
        },
        "limitations": [
            "The public V1 package omits confidential browsing.dta, so Appendix Table D1 "
            "cannot be reproduced.",
            "The exact calendar period and outcome-maturity window are not disclosed in "
            "the anonymized data.",
            "Monetary outcomes are missing for a non-trivial subset of purchaser rows; "
            "official Table 2 uses complete-case regression after zero-filling non-purchasers.",
            "No separate COGS, shipping, payment, return, or variable-cost ledger supports "
            "a contribution-profit claim.",
        ],
    }
    output = ROOT / "results/buy_baits_forensic_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree-sha256", required=True)
    args = parser.parse_args()
    report = audit(args.source_commit, args.source_tree_sha256)
    print(json.dumps({"status": report["status"], "split": report["split_manifest"]}, indent=2))
