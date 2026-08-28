"""Forensic DEVELOPMENT-only Hillstrom static-action audit.

The executable accepts no split argument and reads only the pre-materialized
DEVELOPMENT parquet. Validation and sealed outcomes are intentionally unreachable.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2, norm
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from decision_engine.economic_policy_v72.splits import stable_unit_hash

ROOT = Path(__file__).resolve().parent
DEVELOPMENT = Path("data/processed/hillstrom/v7_2/development.parquet")
MANIFEST = ROOT / "manifests/hillstrom_split_manifest.json"
PREREGISTRATION = ROOT / "HILLSTROM_STATIC_PREREGISTRATION.md"
PRIOR_TOURNAMENT = ROOT / "results/hillstrom_development_tournament.json"
OUTPUT = ROOT / "results/hillstrom_static_development_audit.json"
POLICY_OUTPUT = ROOT / "results/hillstrom_policy_hierarchy.json"
FREEZE_OUTPUT = ROOT / "HILLSTROM_DEVELOPMENT_FREEZE_DECISION.json"
QUARANTINE_OUTPUT = ROOT / "HILLSTROM_SEALED_QUARANTINE.json"

SEED = 72_2031
FOLDS = 5
PRIMARY_COST = 0.05
COST_GRID = (0.0, 0.01, 0.05, 0.10, 0.25, 0.50, 1.0, 2.0)
RAW_BOOTSTRAPS = 2_000
ROBUST_BOOTSTRAPS = 300
NUMERIC = ("recency", "history", "mens", "womens", "newbie")
CATEGORICAL = ("history_segment", "zip_code", "channel")
PRETREATMENT = (*NUMERIC, *CATEGORICAL)
OUTCOMES = ("visit", "conversion", "spend")
ARM_ORDER = ("No E-Mail", "Mens E-Mail", "Womens E-Mail")
CORE_ADJUSTED = ("ancova_hc3", "cuped_history", "cross_fitted_aipw")


@dataclass(frozen=True)
class Estimate:
    point: float
    standard_error: float
    lower_95: float
    upper_95: float

    def as_dict(self) -> dict[str, float]:
        return {
            "gross_spend_uplift": self.point,
            "standard_error": self.standard_error,
            "lower_95": self.lower_95,
            "upper_95": self.upper_95,
            "break_even_action_cost": self.point,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _interval(point: float, standard_error: float) -> Estimate:
    critical = float(norm.ppf(0.975))
    return Estimate(
        float(point),
        float(standard_error),
        float(point - critical * standard_error),
        float(point + critical * standard_error),
    )


def _welch(y: np.ndarray, treatment: np.ndarray) -> Estimate:
    treated, control = y[treatment == 1], y[treatment == 0]
    point = float(treated.mean() - control.mean())
    se = float(np.sqrt(treated.var(ddof=1) / len(treated) + control.var(ddof=1) / len(control)))
    return _interval(point, se)


def _strata(frame: pd.DataFrame) -> np.ndarray:
    recency = frame["recency"].to_numpy()
    bucket = np.where(recency <= 3, "1-3", np.where(recency <= 6, "4-6", "7-12"))
    return np.char.add(frame["channel"].to_numpy(dtype=str), np.char.add("|", bucket))


def _stratified(y: np.ndarray, treatment: np.ndarray, strata: np.ndarray) -> Estimate:
    n = len(y)
    point = 0.0
    influence = np.zeros(n, dtype=float)
    for level in np.unique(strata):
        member = strata == level
        treated = member & (treatment == 1)
        control = member & (treatment == 0)
        if not np.any(treated) or not np.any(control):
            raise RuntimeError(f"empty randomized arm in stratum {level}")
        weight = float(member.mean())
        mean_t, mean_c = float(y[treated].mean()), float(y[control].mean())
        point += weight * (mean_t - mean_c)
        influence[treated] = n * weight * (y[treated] - mean_t) / int(treated.sum())
        influence[control] = -n * weight * (y[control] - mean_c) / int(control.sum())
    return _interval(point, float(influence.std(ddof=1) / np.sqrt(n)))


def _transform(frame: pd.DataFrame) -> np.ndarray:
    transformer = ColumnTransformer(
        [
            ("numeric", StandardScaler(), list(NUMERIC)),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", drop="first", sparse_output=False),
                list(CATEGORICAL),
            ),
        ]
    )
    return np.asarray(transformer.fit_transform(frame), dtype=float)


def _ols_hc3(y: np.ndarray, treatment: np.ndarray, x: np.ndarray) -> Estimate:
    design = np.column_stack((np.ones(len(y)), treatment, x))
    inverse = np.linalg.pinv(design.T @ design)
    beta = inverse @ design.T @ y
    residual = y - design @ beta
    leverage = np.einsum("ij,jk,ik->i", design, inverse, design)
    adjusted = residual / np.maximum(1.0 - leverage, 1e-8)
    meat = design.T @ (design * adjusted[:, None] ** 2)
    covariance = inverse @ meat @ inverse
    return _interval(float(beta[1]), float(np.sqrt(max(covariance[1, 1], 0.0))))


def _cuped(y: np.ndarray, treatment: np.ndarray, history: np.ndarray) -> Estimate:
    centered = history - history.mean()
    theta = float(np.cov(y, history, ddof=1)[0, 1] / np.var(history, ddof=1))
    return _welch(y - theta * centered, treatment)


def _folds(unit_hash: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            int(hashlib.sha256(f"hillstrom-static\0{value}".encode()).hexdigest()[:8], 16) % FOLDS
            for value in unit_hash
        ],
        dtype=int,
    )


def _aipw(
    y: np.ndarray,
    treatment: np.ndarray,
    x: np.ndarray,
    folds: np.ndarray,
) -> tuple[Estimate, np.ndarray]:
    m0, m1 = np.zeros(len(y)), np.zeros(len(y))
    for fold in range(FOLDS):
        test, train = folds == fold, folds != fold
        for arm, target in ((0, m0), (1, m1)):
            rows = train & (treatment == arm)
            model = Ridge(alpha=10.0).fit(x[rows], y[rows])
            target[test] = model.predict(x[test])
    score = m1 - m0 + treatment * (y - m1) / 0.5 - (1 - treatment) * (y - m0) / 0.5
    return _interval(float(score.mean()), float(score.std(ddof=1) / np.sqrt(len(score)))), score


def _huber_point(y: np.ndarray, treatment: np.ndarray, x: np.ndarray) -> float:
    design = np.column_stack((np.ones(len(y)), treatment, x))
    beta = np.linalg.lstsq(design, y, rcond=None)[0]
    for _ in range(40):
        residual = y - design @ beta
        scale = max(float(np.median(np.abs(residual - np.median(residual))) / 0.6745), 1e-6)
        cutoff = 1.345 * scale
        weights = np.minimum(1.0, cutoff / np.maximum(np.abs(residual), 1e-12))
        weighted = design * np.sqrt(weights)[:, None]
        updated = np.linalg.lstsq(weighted, y * np.sqrt(weights), rcond=None)[0]
        if np.max(np.abs(updated - beta)) < 1e-9:
            beta = updated
            break
        beta = updated
    return float(beta[1])


def _bootstrap_difference(
    y: np.ndarray,
    treatment: np.ndarray,
    replicates: int,
    rng: np.random.Generator,
) -> tuple[Estimate, np.ndarray]:
    treated, control = y[treatment == 1], y[treatment == 0]
    values = np.empty(replicates)
    chunk = 100
    for start in range(0, replicates, chunk):
        width = min(chunk, replicates - start)
        treated_index = rng.integers(0, len(treated), size=(width, len(treated)))
        control_index = rng.integers(0, len(control), size=(width, len(control)))
        values[start : start + width] = treated[treated_index].mean(axis=1) - control[
            control_index
        ].mean(axis=1)
    point = float(treated.mean() - control.mean())
    return Estimate(
        point,
        float(values.std(ddof=1)),
        float(np.quantile(values, 0.025)),
        float(np.quantile(values, 0.975)),
    ), values


def _huber_bootstrap(
    y: np.ndarray,
    treatment: np.ndarray,
    x: np.ndarray,
    replicates: int,
    rng: np.random.Generator,
) -> Estimate:
    groups = (np.flatnonzero(treatment == 0), np.flatnonzero(treatment == 1))
    values = np.empty(replicates)
    for replicate in range(replicates):
        indices = np.concatenate(
            [group[rng.integers(0, len(group), size=len(group))] for group in groups]
        )
        values[replicate] = _huber_point(y[indices], treatment[indices], x[indices])
    point = _huber_point(y, treatment, x)
    return Estimate(
        point,
        float(values.std(ddof=1)),
        float(np.quantile(values, 0.025)),
        float(np.quantile(values, 0.975)),
    )


def _with_economics(estimate: Estimate) -> dict[str, Any]:
    result: dict[str, Any] = estimate.as_dict()
    result["net_value_by_cost"] = {
        str(cost): {
            "point": estimate.point - cost,
            "lower_95": estimate.lower_95 - cost,
            "upper_95": estimate.upper_95 - cost,
        }
        for cost in COST_GRID
    }
    return result


def _fold_stability(
    y: np.ndarray,
    treatment: np.ndarray,
    frame: pd.DataFrame,
    x: np.ndarray,
    aipw_score: np.ndarray,
    folds: np.ndarray,
) -> dict[str, Any]:
    methods: dict[str, Callable[[np.ndarray], float]] = {
        "ancova_hc3": lambda rows: _ols_hc3(y[rows], treatment[rows], x[rows]).point,
        "cuped_history": lambda rows: (
            _cuped(y[rows], treatment[rows], frame["history"].to_numpy()[rows]).point
        ),
        "cross_fitted_aipw": lambda rows: float(aipw_score[rows].mean()),
        "robust_regression_hc3": lambda rows: (
            _ols_hc3(y[rows], treatment[rows], np.empty((int(rows.sum()), 0))).point
        ),
    }
    output: dict[str, Any] = {}
    for name, estimator in methods.items():
        by_fold = [estimator(folds == fold) - PRIMARY_COST for fold in range(FOLDS)]
        leave_one_out = [estimator(folds != fold) - PRIMARY_COST for fold in range(FOLDS)]
        output[name] = {
            "net_by_fold": by_fold,
            "positive_fold_count": int(np.sum(np.asarray(by_fold) > 0)),
            "minimum_fold_net": float(min(by_fold)),
            "net_leave_one_fold_out": leave_one_out,
            "all_leave_one_fold_out_positive": bool(np.all(np.asarray(leave_one_out) > 0)),
        }
    return output


def _numeric_balance(frame: pd.DataFrame, column: str, arm: str) -> dict[str, float]:
    treated = frame.loc[frame["segment"] == arm, column].to_numpy(dtype=float)
    control = frame.loc[frame["segment"] == "No E-Mail", column].to_numpy(dtype=float)
    pooled = np.sqrt((treated.var(ddof=1) + control.var(ddof=1)) / 2)
    smd = 0.0 if pooled == 0 else float((treated.mean() - control.mean()) / pooled)
    return {"standardized_mean_difference": smd, "absolute_smd": abs(smd)}


def _categorical_balance(frame: pd.DataFrame, column: str, arm: str) -> dict[str, float]:
    pair = frame[frame["segment"].isin(("No E-Mail", arm))]
    table = pd.crosstab(pair["segment"], pair[column]).to_numpy(dtype=float)
    expected = table.sum(axis=1)[:, None] * table.sum(axis=0)[None, :] / table.sum()
    statistic = float(np.sum((table - expected) ** 2 / np.maximum(expected, 1e-12)))
    dof = max((table.shape[0] - 1) * (table.shape[1] - 1), 1)
    cramers_v = float(np.sqrt(statistic / (table.sum() * max(min(table.shape) - 1, 1))))
    return {
        "chi_square": statistic,
        "degrees_of_freedom": dof,
        "p_value": float(chi2.sf(statistic, dof)),
        "cramers_v": cramers_v,
    }


def _outcome_summary(values: np.ndarray) -> dict[str, Any]:
    return {
        "count": len(values),
        "missing": int(np.isnan(values).sum()),
        "mean": float(np.mean(values)),
        "variance": float(np.var(values, ddof=1)),
        "standard_deviation": float(np.std(values, ddof=1)),
        "zero_fraction": float(np.mean(values == 0)),
        "positive_count": int(np.sum(values > 0)),
        "quantiles": {
            str(q): float(np.quantile(values, q)) for q in (0, 0.5, 0.9, 0.95, 0.99, 0.999, 1)
        },
    }


def _policy_hierarchy(static_pass: bool, prior: dict[str, Any]) -> dict[str, Any]:
    rows = prior["by_cost"][str(PRIMARY_COST)]["heldout_results"]
    indexed = {row["name"]: row for row in rows}
    static = indexed["best_static"]
    hierarchy: list[dict[str, Any]] = [{"level": "BAU", "promoted": True, "reason": "baseline"}]
    hierarchy.append(
        {
            "level": "best_supported_static_action",
            "candidate": prior["by_cost"][str(PRIMARY_COST)]["development_selected_best_static"],
            "promoted": static_pass,
            "heldout_incremental_net_value": static["versus_bau"],
            "reason": "static development gate passed"
            if static_pass
            else "static development gate failed",
        }
    )
    current = "best_supported_static_action" if static_pass else "BAU"
    segment = indexed["simple_rfm_affinity_segment"]
    segment_stability = segment["stability_vs_static"]
    segment_pass = bool(
        static_pass
        and segment["versus_best_static"]["point"] > 0
        and segment["versus_best_static"]["lower_95"] > 0
        and segment_stability["positive_fold_fraction"] >= 0.8
        and segment_stability["minimum_fold_increment"] >= -0.05
    )
    hierarchy.append(
        {
            "level": "supported_segment_policy",
            "candidate": "simple_rfm_affinity_segment",
            "promoted": segment_pass,
            "heldout_incremental_net_value_over_static": segment["versus_best_static"],
            "stability": segment_stability,
            "reason": "promotion criteria passed"
            if segment_pass
            else "no stable positive value over static",
        }
    )
    if segment_pass:
        current = "supported_segment_policy"
    challenger_rows = [
        row
        for row in rows
        if row["name"]
        not in {
            "BAU",
            "treat_all_mens",
            "treat_all_womens",
            "best_static",
            "simple_rfm_affinity_segment",
        }
    ]
    personalized = max(challenger_rows, key=lambda row: row["value_per_customer"])
    personalized_stability = personalized["stability_vs_static"]
    personalized_pass = bool(
        static_pass
        and not segment_pass
        and personalized["versus_best_static"]["point"] > 0
        and personalized["versus_best_static"]["lower_95"] > 0
        and personalized_stability["positive_fold_fraction"] >= 0.8
        and personalized_stability["minimum_fold_increment"] >= -0.05
    )
    hierarchy.append(
        {
            "level": "supported_personalized_policy",
            "candidate": personalized["name"],
            "promoted": personalized_pass,
            "heldout_incremental_net_value_over_static": personalized["versus_best_static"],
            "stability": personalized_stability,
            "reason": "promotion criteria passed"
            if personalized_pass
            else "no stable positive value over preceding supported level",
        }
    )
    if personalized_pass:
        current = "supported_personalized_policy"
    return {"selected_level": current, "levels": hierarchy, "validation_opened": False}


def _git_metadata() -> dict[str, str]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    tracked = subprocess.run(
        ["git", "ls-files"], check=True, capture_output=True, text=True
    ).stdout.splitlines()
    digest = hashlib.sha256()
    for name in sorted(tracked):
        path = Path(name)
        if path.is_file():
            digest.update(name.encode())
            digest.update(path.read_bytes())
    return {"source_commit": commit, "tracked_code_hash": digest.hexdigest()}


def run(
    *, raw_bootstraps: int = RAW_BOOTSTRAPS, robust_bootstraps: int = ROBUST_BOOTSTRAPS
) -> dict[str, Any]:
    started = time.perf_counter()
    if not DEVELOPMENT.exists():
        raise FileNotFoundError("Hillstrom DEVELOPMENT materialization is absent")
    frame = pd.read_parquet(DEVELOPMENT)
    allowed = {*PRETREATMENT, "segment", *OUTCOMES, "unit_hash"}
    if set(frame.columns) != allowed or {"row_id", "id"} & set(frame.columns):
        raise RuntimeError("invalid Hillstrom DEVELOPMENT schema or identifying column")
    if frame["unit_hash"].duplicated().any():
        raise RuntimeError("duplicate randomized unit hashes in DEVELOPMENT")
    if set(frame["segment"].unique()) != set(ARM_ORDER):
        raise RuntimeError("randomization arm mapping mismatch")

    manifest = json.loads(MANIFEST.read_text())
    development_hashes = set(manifest["unit_hashes"]["DEVELOPMENT"])
    validation_hashes = set(manifest["unit_hashes"]["VALIDATION"])
    sealed_hashes = set(manifest["unit_hashes"]["SEALED_TEST"])
    observed_hashes = set(frame["unit_hash"].astype(str))
    split_integrity = {
        "development_matches_manifest": observed_hashes == development_hashes,
        "development_validation_disjoint": not bool(observed_hashes & validation_hashes),
        "development_sealed_disjoint": not bool(observed_hashes & sealed_hashes),
        "validation_outcomes_read": False,
        "sealed_outcomes_read": False,
    }
    if not all(value for key, value in split_integrity.items() if not key.endswith("_read")):
        raise RuntimeError("Hillstrom split integrity failure")

    counts = frame["segment"].value_counts().to_dict()
    missingness = {column: int(frame[column].isna().sum()) for column in frame.columns}
    outcome_distributions = {
        arm: {
            outcome: _outcome_summary(
                frame.loc[frame["segment"] == arm, outcome].to_numpy(dtype=float)
            )
            for outcome in OUTCOMES
        }
        for arm in ARM_ORDER
    }
    exact_duplicate_profiles = int(frame.drop(columns="unit_hash").duplicated(keep=False).sum())
    expected = len(frame) / 3
    srm_statistic = float(sum((counts[arm] - expected) ** 2 / expected for arm in ARM_ORDER))

    balance: dict[str, Any] = {}
    for arm in ("Mens E-Mail", "Womens E-Mail"):
        balance[arm] = {
            "numeric": {column: _numeric_balance(frame, column, arm) for column in NUMERIC},
            "categorical": {
                column: _categorical_balance(frame, column, arm) for column in CATEGORICAL
            },
        }
    max_abs_smd = max(
        item["absolute_smd"] for arm in balance.values() for item in arm["numeric"].values()
    )
    max_cramers_v = max(
        item["cramers_v"] for arm in balance.values() for item in arm["categorical"].values()
    )

    pair = frame[frame["segment"].isin(("No E-Mail", "Mens E-Mail"))].reset_index(drop=True)
    treatment = (pair["segment"] == "Mens E-Mail").to_numpy(dtype=int)
    y = pair["spend"].to_numpy(dtype=float)
    x = _transform(pair)
    fold = _folds(pair["unit_hash"].to_numpy(dtype=str))
    rng = np.random.default_rng(SEED)

    raw = _welch(y, treatment)
    stratified = _stratified(y, treatment, _strata(pair))
    ancova = _ols_hc3(y, treatment, x)
    cuped = _cuped(y, treatment, pair["history"].to_numpy(dtype=float))
    aipw, aipw_score = _aipw(y, treatment, x, fold)
    robust = _ols_hc3(y, treatment, np.empty((len(y), 0)))
    huber_sensitivity = _huber_bootstrap(y, treatment, x, robust_bootstraps, rng)
    bootstrap, bootstrap_values = _bootstrap_difference(y, treatment, raw_bootstraps, rng)
    estimates = {
        "raw_difference_in_means": raw,
        "stratified_difference_in_means": stratified,
        "ancova_hc3": ancova,
        "cuped_history": cuped,
        "cross_fitted_aipw": aipw,
        "robust_regression_hc3": robust,
        "customer_level_bootstrap": bootstrap,
    }
    estimator_results = {name: _with_economics(value) for name, value in estimates.items()}
    stability = _fold_stability(y, treatment, pair, x, aipw_score, fold)

    winsorization: dict[str, Any] = {}
    for quantile in (None, 0.999, 0.995, 0.99):
        capped = y if quantile is None else np.minimum(y, np.quantile(y, quantile))
        key = "none" if quantile is None else str(quantile)
        winsorization[key] = {
            "cap": None if quantile is None else float(np.quantile(y, quantile)),
            "raw_net": _welch(capped, treatment).point - PRIMARY_COST,
            "ancova_net": _ols_hc3(capped, treatment, x).point - PRIMARY_COST,
            "cuped_net": _cuped(capped, treatment, pair["history"].to_numpy(dtype=float)).point
            - PRIMARY_COST,
            "aipw_net": _aipw(capped, treatment, x, fold)[0].point - PRIMARY_COST,
        }

    analytic_bootstrap_ratio = raw.standard_error / bootstrap.standard_error
    assignment_pass = bool(chi2.sf(srm_statistic, 2) > 0.001)
    balance_pass = max_abs_smd <= 0.10 and max_cramers_v <= 0.10
    bootstrap_pass = bool(
        0.80 <= analytic_bootstrap_ratio <= 1.25
        and bootstrap.lower_95 <= bootstrap.point <= bootstrap.upper_95
        and len(bootstrap_values) == raw_bootstraps
    )
    overlap_pass = bool(np.all(np.bincount(treatment) > 0))
    leakage_pass = bool(
        split_integrity["development_matches_manifest"]
        and split_integrity["development_validation_disjoint"]
        and split_integrity["development_sealed_disjoint"]
        and not split_integrity["validation_outcomes_read"]
        and not split_integrity["sealed_outcomes_read"]
        and set(pair.columns) <= allowed
    )
    conservative_lower = min(estimates[name].lower_95 - PRIMARY_COST for name in CORE_ADJUSTED)
    selected_mens_count = sum(estimates[name].point - PRIMARY_COST > 0 for name in estimates)
    stability_pass = all(
        detail["positive_fold_count"] >= 4
        and detail["all_leave_one_fold_out_positive"]
        and detail["minimum_fold_net"] >= -0.05
        for detail in stability.values()
    )
    winsor_pass = all(
        min(value[name] for name in ("raw_net", "ancova_net", "cuped_net", "aipw_net")) > 0
        for value in winsorization.values()
    )
    gate_checks = {
        "positive_primary_net_point": raw.point - PRIMARY_COST > 0,
        "conservative_adjusted_lower_bound_positive": conservative_lower > 0,
        "three_estimators_select_mens": selected_mens_count >= 3,
        "fold_stability": stability_pass,
        "positive_at_locked_email_cost": raw.point - PRIMARY_COST > 0,
        "assignment": assignment_pass,
        "leakage": leakage_pass,
        "overlap": overlap_pass,
        "bootstrap_implementation": bootstrap_pass,
        "pretreatment_balance": balance_pass,
        "winsorization_sensitivity": winsor_pass,
    }
    static_pass = all(gate_checks.values())
    prior = json.loads(PRIOR_TOURNAMENT.read_text())
    policy = _policy_hierarchy(static_pass, prior)
    metadata = _git_metadata()

    result: dict[str, Any] = {
        "status": (
            "DEVELOPMENT_GATE_PASS_READY_TO_FREEZE"
            if static_pass
            else "HILLSTROM_INCONCLUSIVE_VALIDATION_REMAINS_CLOSED"
        ),
        "scope": "HILLSTROM_DEVELOPMENT_ONLY",
        "validation_opened": False,
        "sealed_test_used_as_authority": False,
        "estimand": "ITT mean two-week spend: Mens E-Mail minus No E-Mail per eligible customer",
        "locked_primary_cost": PRIMARY_COST,
        "cost_grid": list(COST_GRID),
        "seed": SEED,
        "folds": FOLDS,
        "bootstrap_replicates": {"raw": raw_bootstraps, "robust": robust_bootstraps},
        "provenance": {
            **metadata,
            "audit_code_sha256": _sha256(Path(__file__)),
            "dataset_sha256": manifest["dataset_sha256"],
            "development_parquet_sha256": _sha256(DEVELOPMENT),
            "split_manifest_sha256": _sha256(MANIFEST),
            "preregistration_sha256": _sha256(PREREGISTRATION),
        },
        "forensic_audit": {
            "arm_mapping": {"No E-Mail": 0, "Mens E-Mail": 1, "Womens E-Mail": 2},
            "randomization_unit": (
                "one source row/customer; source has no original stable customer ID"
            ),
            "sample_size": len(frame),
            "arm_counts": counts,
            "missingness": missingness,
            "unique_unit_hashes": int(frame["unit_hash"].nunique()),
            "duplicate_unit_hashes": int(frame["unit_hash"].duplicated().sum()),
            "exact_duplicate_nonidentifying_profiles": exact_duplicate_profiles,
            "duplicate_customer_limitation": (
                "cannot test repeated people because the public source omits a stable customer ID"
            ),
            "outcome_distributions": outcome_distributions,
            "assignment_srm": {
                "chi_square": srm_statistic,
                "p_value": float(chi2.sf(srm_statistic, 2)),
                "pass": assignment_pass,
            },
            "pretreatment_balance": balance,
            "max_absolute_smd": max_abs_smd,
            "max_cramers_v": max_cramers_v,
            "balance_pass": balance_pass,
            "effective_sample_size": {
                "known_pair_propensity": 0.5,
                "No E-Mail": int(np.sum(treatment == 0)),
                "Mens E-Mail": int(np.sum(treatment == 1)),
                "maximum_inverse_probability_weight": 2.0,
            },
            "split_integrity": split_integrity,
            "previous_holdout_explanation": {
                "reported_net_point": 0.7350094247117838,
                "reported_lower_95": -0.2681004103750271,
                "reported_upper_95": 1.7381192597985946,
                "internal_holdout_n": prior["counts"]["inner_heldout"],
                "explanation": (
                    "same direction as full-development raw ITT, but a separate 25% internal "
                    "holdout with sparse heavy-tailed spend and much larger sampling error"
                ),
            },
        },
        "estimator_tournament": {
            "estimators": estimator_results,
            "estimator_disagreement_range": max(value.point for value in estimates.values())
            - min(value.point for value in estimates.values()),
            "huber_location_sensitivity_not_mean_estimand": _with_economics(huber_sensitivity),
            "fold_stability": stability,
            "winsorization_sensitivity": winsorization,
            "analytic_to_bootstrap_se_ratio": analytic_bootstrap_ratio,
        },
        "development_gate": {
            "candidate": "Mens E-Mail",
            "checks": gate_checks,
            "passed": static_pass,
            "conservative_covariate_adjusted_net_lower_95": conservative_lower,
            "estimators_selecting_mens_at_locked_cost": selected_mens_count,
            "freeze_written": False,
            "decision": "ready to write immutable freeze"
            if static_pass
            else "INCONCLUSIVE; no freeze",
        },
        "policy_hierarchy": policy,
        "runtime_seconds": time.perf_counter() - started,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    POLICY_OUTPUT.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n")
    FREEZE_OUTPUT.write_text(
        json.dumps(
            {
                "status": result["status"],
                "development_gate": result["development_gate"],
                "validation_opened": False,
                "sealed_test_authority": False,
                "freeze_artifact_created": False,
                "provenance": result["provenance"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    row_zero = stable_unit_hash("hillstrom", "row-0")
    QUARANTINE_OUTPUT.write_text(
        json.dumps(
            {
                "status": "QUARANTINED_INTEGRITY_INCIDENT",
                "affected_unit_hash": row_zero,
                "manifest_split": "SEALED_TEST",
                "hash_present_in_sealed_manifest": row_zero in sealed_hashes,
                "hash_present_in_development": row_zero in development_hashes,
                "hash_present_in_validation": row_zero in validation_hashes,
                "incident": "a full raw source row was displayed during a prior diagnostic",
                "used_for_modeling_or_scoring": False,
                "split_moved": False,
                "sealed_test_fully_untouched": False,
                "validation_is_only_possible_one_shot_confirmation": True,
                "validation_opened": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return result


if __name__ == "__main__":
    completed = run()
    print(
        json.dumps(
            {
                "status": completed["status"],
                "gate": completed["development_gate"],
                "runtime_seconds": completed["runtime_seconds"],
            },
            indent=2,
        )
    )
