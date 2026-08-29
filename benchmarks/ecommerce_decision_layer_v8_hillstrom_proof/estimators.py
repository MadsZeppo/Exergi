"""Frozen statistical estimators for the V8 randomized validation."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import Ridge

NUMERIC_FEATURES = ("recency", "history", "mens", "womens", "newbie")
CATEGORICAL_FEATURES = ("history_segment", "zip_code", "channel")


def encode_pretreatment_features(
    frame: pd.DataFrame, category_levels: dict[str, list[str]] | None = None
) -> tuple[np.ndarray, dict[str, list[str]], list[str]]:
    """Encode exactly the eight audited pretreatment fields with frozen levels."""
    required = set((*NUMERIC_FEATURES, *CATEGORICAL_FEATURES))
    if not required.issubset(frame.columns):
        raise ValueError(f"missing pretreatment features: {sorted(required - set(frame.columns))}")
    levels = category_levels or {
        column: sorted(frame[column].astype(str).unique().tolist())
        for column in CATEGORICAL_FEATURES
    }
    parts = [frame.loc[:, NUMERIC_FEATURES].to_numpy(dtype=float)]
    names = list(NUMERIC_FEATURES)
    for column in CATEGORICAL_FEATURES:
        observed = frame[column].astype(str)
        unknown = set(observed.unique()) - set(levels[column])
        if unknown:
            raise ValueError(f"unknown frozen levels in {column}: {sorted(unknown)}")
        for level in levels[column][1:]:
            parts.append((observed == level).to_numpy(dtype=float)[:, None])
            names.append(f"{column}={level}")
    matrix = np.column_stack(parts)
    if np.any(~np.isfinite(matrix)):
        raise ValueError("pretreatment feature matrix must be finite")
    return matrix, levels, names


@dataclass(frozen=True)
class Estimate:
    point: float
    standard_error: float
    lower_95: float
    upper_95: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def interval(point: float, standard_error: float) -> Estimate:
    critical = float(norm.ppf(0.975))
    return Estimate(
        point=float(point),
        standard_error=float(standard_error),
        lower_95=float(point - critical * standard_error),
        upper_95=float(point + critical * standard_error),
    )


def net_outcome(spend: np.ndarray, treatment: np.ndarray, email_cost: float) -> np.ndarray:
    spend_array = np.asarray(spend, dtype=float)
    treatment_array = np.asarray(treatment, dtype=np.int64)
    if spend_array.shape != treatment_array.shape:
        raise ValueError("spend and treatment must have equal shape")
    if np.any(~np.isfinite(spend_array)) or np.any(spend_array < 0):
        raise ValueError("spend must be finite and nonnegative; zero is valid")
    if set(np.unique(treatment_array)) - {0, 1}:
        raise ValueError("treatment must be binary randomized assignment")
    return spend_array - float(email_cost) * treatment_array


def difference_in_means(spend: np.ndarray, treatment: np.ndarray, email_cost: float) -> Estimate:
    outcome = net_outcome(spend, treatment, email_cost)
    treated, control = outcome[treatment == 1], outcome[treatment == 0]
    if len(treated) < 2 or len(control) < 2:
        raise ValueError("both randomized arms need at least two observations")
    point = float(treated.mean() - control.mean())
    standard_error = float(
        np.sqrt(treated.var(ddof=1) / len(treated) + control.var(ddof=1) / len(control))
    )
    return interval(point, standard_error)


def lin_ancova(
    spend: np.ndarray,
    treatment: np.ndarray,
    features: np.ndarray,
    email_cost: float,
) -> Estimate:
    """Lin regression with centered covariates, interactions, and HC3 uncertainty."""
    y = net_outcome(spend, treatment, email_cost)
    t = np.asarray(treatment, dtype=float)
    x = np.asarray(features, dtype=float)
    if x.ndim != 2 or len(x) != len(y) or np.any(~np.isfinite(x)):
        raise ValueError("features must be a finite two-dimensional matrix")
    centered = x - x.mean(axis=0)
    design = np.column_stack((np.ones(len(y)), t, centered, centered * t[:, None]))
    inverse = np.linalg.pinv(design.T @ design)
    beta = inverse @ design.T @ y
    residual = y - design @ beta
    leverage = np.einsum("ij,jk,ik->i", design, inverse, design)
    adjusted = residual / np.maximum(1.0 - leverage, 1e-10)
    meat = design.T @ (design * adjusted[:, None] ** 2)
    covariance = inverse @ meat @ inverse
    return interval(float(beta[1]), float(np.sqrt(max(covariance[1, 1], 0.0))))


def deterministic_folds(unit_hashes: np.ndarray, folds: int, seed: int) -> np.ndarray:
    if folds < 2:
        raise ValueError("cross-fitting requires at least two folds")
    return np.asarray(
        [
            int.from_bytes(hashlib.sha256(f"{seed}\0{value}".encode()).digest()[:8], "big") % folds
            for value in np.asarray(unit_hashes, dtype=str)
        ],
        dtype=np.int64,
    )


def cross_fitted_aipw(
    spend: np.ndarray,
    treatment: np.ndarray,
    features: np.ndarray,
    unit_hashes: np.ndarray,
    email_cost: float,
    *,
    folds: int,
    seed: int,
    ridge_alpha: float,
    propensity: float = 0.5,
) -> tuple[Estimate, np.ndarray, np.ndarray]:
    y = net_outcome(spend, treatment, email_cost)
    t = np.asarray(treatment, dtype=np.int64)
    x = np.asarray(features, dtype=float)
    hashes = np.asarray(unit_hashes, dtype=str)
    if not (0 < propensity < 1):
        raise ValueError("known propensity must lie strictly between zero and one")
    if len(np.unique(hashes)) != len(hashes):
        raise ValueError("randomized unit hashes must be unique")
    fold_id = deterministic_folds(hashes, folds, seed)
    m0, m1 = np.empty(len(y)), np.empty(len(y))
    for fold in range(folds):
        test = fold_id == fold
        train = ~test
        if not np.any(test):
            raise ValueError(f"empty cross-fitting fold {fold}")
        for arm, target in ((0, m0), (1, m1)):
            rows = train & (t == arm)
            if int(rows.sum()) < 2:
                raise ValueError(f"insufficient arm {arm} training rows in fold {fold}")
            model = Ridge(alpha=ridge_alpha).fit(x[rows], y[rows])
            target[test] = model.predict(x[test])
    score = m1 - m0 + t * (y - m1) / propensity - (1 - t) * (y - m0) / (1 - propensity)
    estimate = interval(float(score.mean()), float(score.std(ddof=1) / np.sqrt(len(score))))
    return estimate, score, fold_id


def permutation_p_value(
    spend: np.ndarray,
    treatment: np.ndarray,
    email_cost: float,
    *,
    replicates: int,
    seed: int,
) -> float:
    """Two-sided fixed-size assignment randomization p-value."""
    spend_array = np.asarray(spend, dtype=float)
    treatment_array = np.asarray(treatment, dtype=np.int64)
    n_treated = int(treatment_array.sum())
    n = len(treatment_array)
    observed = difference_in_means(spend_array, treatment_array, email_cost).point
    total = float(spend_array.sum())
    rng = np.random.default_rng(seed)
    extreme = 0
    for _ in range(replicates):
        treated_index = rng.choice(n, size=n_treated, replace=False)
        treated_sum = float(spend_array[treated_index].sum())
        permuted = treated_sum / n_treated - (total - treated_sum) / (n - n_treated) - email_cost
        extreme += int(abs(permuted) >= abs(observed))
    return float((extreme + 1) / (replicates + 1))


def arm_stratified_bootstrap(
    spend: np.ndarray,
    treatment: np.ndarray,
    email_cost: float,
    *,
    replicates: int,
    seed: int,
) -> tuple[Estimate, np.ndarray]:
    treated = np.asarray(spend, dtype=float)[treatment == 1]
    control = np.asarray(spend, dtype=float)[treatment == 0]
    rng = np.random.default_rng(seed)
    values = np.empty(replicates, dtype=float)
    chunk_size = 100
    for start in range(0, replicates, chunk_size):
        width = min(chunk_size, replicates - start)
        treated_index = rng.integers(0, len(treated), size=(width, len(treated)))
        control_index = rng.integers(0, len(control), size=(width, len(control)))
        values[start : start + width] = (
            treated[treated_index].mean(axis=1) - control[control_index].mean(axis=1) - email_cost
        )
    point = float(treated.mean() - control.mean() - email_cost)
    return (
        Estimate(
            point=point,
            standard_error=float(values.std(ddof=1)),
            lower_95=float(np.quantile(values, 0.025)),
            upper_95=float(np.quantile(values, 0.975)),
        ),
        values,
    )


def winsorized_difference(
    spend: np.ndarray, treatment: np.ndarray, email_cost: float, cap: float
) -> Estimate:
    if cap <= 0:
        raise ValueError("nonzero development cap must be positive")
    return difference_in_means(
        np.minimum(np.asarray(spend, dtype=float), cap), treatment, email_cost
    )
