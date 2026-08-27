from __future__ import annotations

import numpy as np


def mae(y: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y - pred)))


def rmse(y: np.ndarray, pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y - pred) ** 2)))


def wape(y: np.ndarray, pred: np.ndarray) -> float:
    denominator = np.sum(np.abs(y))
    return float(np.sum(np.abs(y - pred)) / denominator) if denominator else float("nan")


def mase(y: np.ndarray, pred: np.ndarray, train_y: np.ndarray, seasonality: int = 7) -> float:
    if train_y.size <= seasonality:
        return float("nan")
    scale = np.mean(np.abs(train_y[seasonality:] - train_y[:-seasonality]))
    return float(np.mean(np.abs(y - pred)) / scale) if scale else float("nan")


def pinball_loss(y: np.ndarray, q: np.ndarray, tau: float) -> float:
    residual = y - q
    return float(np.mean(np.maximum(tau * residual, (tau - 1) * residual)))


def forecast_metrics(y: np.ndarray, pred: np.ndarray, train_y: np.ndarray) -> dict[str, float]:
    return {
        "mae": mae(y, pred),
        "rmse": rmse(y, pred),
        "wape": wape(y, pred),
        "mase": mase(y, pred, train_y),
    }
