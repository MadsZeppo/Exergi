from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
import polars as pl

from decision_engine.causal.continuous_dr import ContinuousDRDoseResponseEstimator


@dataclass(frozen=True)
class CounterfactualBootstrapResult:
    doses: tuple[float, ...]
    point_estimate: tuple[float, ...]
    bootstrap_standard_error: tuple[float, ...]
    intervals: dict[float, tuple[tuple[float, ...], tuple[float, ...]]]
    valid_replicates: int
    requested_replicates: int
    demand_samples: np.ndarray
    profit_samples: np.ndarray


def _cluster_resample(
    frame: pl.DataFrame, cluster_columns: list[str], rng: np.random.Generator
) -> pl.DataFrame:
    cluster_key = "__bootstrap_cluster"
    keyed = frame.with_columns(
        pl.concat_str(cluster_columns, separator="|").alias(cluster_key)
    )
    clusters = keyed[cluster_key].unique(maintain_order=True).to_list()
    sampled = rng.choice(clusters, len(clusters), replace=True)
    pieces: list[pl.DataFrame] = []
    for draw, cluster in enumerate(sampled):
        pieces.append(
            keyed.filter(pl.col(cluster_key) == cluster)
            .drop(cluster_key)
            .with_columns(pl.lit(draw).alias("__bootstrap_draw"))
        )
    return pl.concat(pieces).drop("__bootstrap_draw").sort("date")


def bootstrap_counterfactual_curve(
    estimator: ContinuousDRDoseResponseEstimator,
    history: pl.DataFrame,
    state: pl.DataFrame,
    features: list[str],
    doses: np.ndarray,
    *,
    replicates: int = 50,
    seed: int = 42,
    cluster_columns: tuple[str, ...] = ("store_id", "sku_id"),
    levels: tuple[float, ...] = (0.5, 0.8, 0.9, 0.95),
    n_jobs: int = 1,
) -> CounterfactualBootstrapResult:
    if replicates < 2:
        raise ValueError("at least two bootstrap replicates are required")
    missing = set(cluster_columns) - set(history.columns)
    if missing:
        raise ValueError(f"bootstrap cluster columns missing: {sorted(missing)}")
    candidates = np.asarray(doses, dtype=float)
    point_rows = estimator.dose_response(state, candidates)
    point = np.mean(point_rows, axis=0)
    rng = np.random.default_rng(seed)
    samples = [
        _cluster_resample(history, list(cluster_columns), rng) for _ in range(replicates)
    ]

    def fit_replicate(item: tuple[int, pl.DataFrame]) -> tuple[np.ndarray, np.ndarray] | None:
        replicate, sample = item
        try:
            fitted = ContinuousDRDoseResponseEstimator(
                outcome_kind=estimator.outcome_kind,
                density_kind=estimator.density_kind,
                n_splits=estimator.n_splits,
                bandwidth=estimator.bandwidth,
                density_floor=estimator.density_floor,
                seed=seed + replicate + 1,
            ).fit(sample, features)
            response = fitted.dose_response(state, candidates)
            mean_response = np.mean(response, axis=0)
            price = state["regular_price"].to_numpy()[:, None] * (1 - candidates[None, :])
            cost = state["unit_cost"].to_numpy()[:, None]
            profit = np.mean((price - cost) * response, axis=0)
            if np.all(np.isfinite(mean_response)) and np.all(np.isfinite(profit)):
                return mean_response, profit
        except (ValueError, RuntimeError):
            return None
        return None

    if n_jobs < 1:
        raise ValueError("n_jobs must be positive")
    items = list(enumerate(samples))
    if n_jobs == 1:
        fitted = [fit_replicate(item) for item in items]
    else:
        with ThreadPoolExecutor(max_workers=n_jobs) as executor:
            fitted = list(executor.map(fit_replicate, items))
    demand_draws = [item[0] for item in fitted if item is not None]
    profit_draws = [item[1] for item in fitted if item is not None]
    if len(demand_draws) < 2:
        raise RuntimeError("fewer than two valid bootstrap replicates")
    bootstrap_samples = np.asarray(demand_draws)
    profit_samples = np.asarray(profit_draws)
    intervals: dict[float, tuple[tuple[float, ...], tuple[float, ...]]] = {}
    for level in levels:
        if not 0 < level < 1:
            raise ValueError("interval levels must lie in (0, 1)")
        alpha = 1 - level
        lower = np.quantile(bootstrap_samples, alpha / 2, axis=0)
        upper = np.quantile(bootstrap_samples, 1 - alpha / 2, axis=0)
        intervals[level] = (tuple(map(float, lower)), tuple(map(float, upper)))
    return CounterfactualBootstrapResult(
        tuple(map(float, candidates)),
        tuple(map(float, point)),
        tuple(map(float, np.std(bootstrap_samples, axis=0, ddof=1))),
        intervals,
        len(bootstrap_samples),
        replicates,
        bootstrap_samples,
        profit_samples,
    )
