from __future__ import annotations

import numpy as np


def dose_response_metrics(
    truth: np.ndarray, estimate: np.ndarray, doses: np.ndarray
) -> dict[str, float]:
    error = np.asarray(estimate) - np.asarray(truth)
    return {
        "rmse": float(np.sqrt(np.mean(error**2))),
        "integrated_absolute_error": float(np.mean(np.trapezoid(np.abs(error), doses, axis=1))),
        "integrated_squared_error": float(np.mean(np.trapezoid(error**2, doses, axis=1))),
    }


def optimal_discount_metrics(
    true_profit: np.ndarray, estimated_profit: np.ndarray, doses: np.ndarray
) -> dict[str, float]:
    true_index = true_profit.argmax(axis=1)
    estimated_index = estimated_profit.argmax(axis=1)
    rows = np.arange(true_profit.shape[0])
    regret = true_profit[rows, true_index] - true_profit[rows, estimated_index]
    return {
        "optimal_discount_mae": float(np.mean(np.abs(doses[true_index] - doses[estimated_index]))),
        "economic_regret": float(np.mean(regret)),
    }


def spillover_recovery_metrics(
    truth: np.ndarray, estimate: np.ndarray, top_k: int = 10
) -> dict[str, float]:
    mask = ~np.eye(truth.shape[0], dtype=bool)
    sign_accuracy = float(np.mean(np.sign(truth[mask]) == np.sign(estimate[mask])))
    true_top = set(np.argsort(np.abs(truth[mask]))[-top_k:])
    estimate_top = set(np.argsort(np.abs(estimate[mask]))[-top_k:])
    overlap = len(true_top & estimate_top)
    return {
        "sign_accuracy": sign_accuracy,
        "magnitude_mae": float(np.mean(np.abs(truth[mask] - estimate[mask]))),
        "top_k_precision": overlap / top_k,
        "top_k_recall": overlap / top_k,
    }


def counterfactual_calibration_metrics(
    truth: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    *,
    nominal: float,
) -> dict[str, float]:
    truth_values = np.asarray(truth, dtype=float)
    low = np.asarray(lower, dtype=float)
    high = np.asarray(upper, dtype=float)
    if not (truth_values.shape == low.shape == high.shape):
        raise ValueError("truth and interval arrays must have equal shapes")
    if not 0 < nominal < 1:
        raise ValueError("nominal coverage must lie in (0, 1)")
    alpha = 1 - nominal
    covered = (truth_values >= low) & (truth_values <= high)
    width = high - low
    interval_score = width.copy()
    interval_score += 2 / alpha * (low - truth_values) * (truth_values < low)
    interval_score += 2 / alpha * (truth_values - high) * (truth_values > high)
    coverage = float(np.mean(covered))
    return {
        "nominal": nominal,
        "coverage": coverage,
        "average_width": float(np.mean(width)),
        "calibration_error": abs(coverage - nominal),
        "interval_score": float(np.mean(interval_score)),
    }
