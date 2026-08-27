"""Leak-safe CUPED and out-of-fold CUPAC variance reduction."""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import KFold

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")


@dataclass(frozen=True)
class VarianceReductionReport:
    method: str
    beta: float
    raw_variance: float
    adjusted_variance: float
    variance_reduction: float
    oof: bool


def cuped_adjust(
    outcome: np.ndarray, pre_period_outcome: np.ndarray
) -> tuple[np.ndarray, VarianceReductionReport]:
    y = np.asarray(outcome, dtype=float)
    pre = np.asarray(pre_period_outcome, dtype=float)
    if y.shape != pre.shape or len(y) < 2:
        raise ValueError("CUPED arrays must align")
    variance = float(np.var(pre, ddof=1))
    beta = 0.0 if variance <= 0 else float(np.cov(y, pre, ddof=1)[0, 1] / variance)
    adjusted = y - beta * (pre - np.mean(pre))
    raw_variance = float(np.var(y, ddof=1))
    adjusted_variance = float(np.var(adjusted, ddof=1))
    reduction = 0.0 if raw_variance <= 0 else 1 - adjusted_variance / raw_variance
    return adjusted, VarianceReductionReport(
        method="CUPED",
        beta=beta,
        raw_variance=raw_variance,
        adjusted_variance=adjusted_variance,
        variance_reduction=reduction,
        oof=False,
    )


def cupac_adjust_oof(
    outcome: np.ndarray,
    pre_treatment_features: np.ndarray,
    historical_bau_outcome: np.ndarray,
    *,
    feature_names: tuple[str, ...],
    forbidden_post_treatment_features: frozenset[str],
    folds: int = 3,
    seed: int = 6601,
) -> tuple[np.ndarray, np.ndarray, VarianceReductionReport]:
    if forbidden_post_treatment_features.intersection(feature_names):
        raise ValueError("CUPAC received a post-treatment feature")
    y = np.asarray(outcome, dtype=float)
    x = np.asarray(pre_treatment_features, dtype=float)
    historical = np.asarray(historical_bau_outcome, dtype=float)
    if len(x) != len(y) or historical.shape != y.shape:
        raise ValueError("CUPAC inputs are not aligned")
    predictions = np.zeros(len(y))
    splitter = KFold(folds, shuffle=True, random_state=seed)
    for fold, (train, test) in enumerate(splitter.split(x)):
        model = HistGradientBoostingRegressor(
            max_iter=80, max_leaf_nodes=15, random_state=seed + fold
        )
        model.fit(x[train], historical[train])
        predictions[test] = model.predict(x[test])
    adjusted, raw_report = cuped_adjust(y, predictions)
    return (
        adjusted,
        predictions,
        VarianceReductionReport(
            method="CUPAC_OOF",
            beta=raw_report.beta,
            raw_variance=raw_report.raw_variance,
            adjusted_variance=raw_report.adjusted_variance,
            variance_reduction=raw_report.variance_reduction,
            oof=True,
        ),
    )
