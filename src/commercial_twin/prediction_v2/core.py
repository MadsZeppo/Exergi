"""Scientific core for the decomposed Prediction Engine V2.

No function in this module reads official final labels.  Final access is controlled by
``FinalRunGuard`` and benchmark orchestration.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class SupportClass(StrEnum):
    VERY_SPARSE = "VERY_SPARSE"
    SPARSE = "SPARSE"
    ESTABLISHED = "ESTABLISHED"
    RICH = "RICH"


@dataclass(frozen=True)
class SupportThresholds:
    established_active_days: int = 3
    rich_active_days: int = 8
    established_tenure_days: int = 60
    rich_lines: int = 20


DEFAULT_SUPPORT_THRESHOLDS = SupportThresholds()


@dataclass(frozen=True)
class PredictionV2Output:
    customer_key: str
    rank_score: float
    initial_probability: float
    final_probability: float
    route: str
    support_class: SupportClass
    reliability: str
    lifecycle: str
    calibration_version: str

    def __post_init__(self) -> None:
        for value in (self.initial_probability, self.final_probability):
            if not 0 <= value <= 1:
                raise ValueError("probabilities must be in [0,1]")


def classify_support(
    active_days: np.ndarray,
    transaction_lines: np.ndarray,
    tenure_days: np.ndarray,
    thresholds: SupportThresholds = DEFAULT_SUPPORT_THRESHOLDS,
) -> np.ndarray:
    """Deterministic evidence-depth classification selected on development only."""
    active = np.asarray(active_days, int)
    lines = np.asarray(transaction_lines, int)
    tenure = np.asarray(tenure_days, float)
    output = np.full(len(active), SupportClass.VERY_SPARSE.value, dtype=object)
    sparse = (active >= 2) | (lines >= 3) | (tenure >= 30)
    established = (
        (active >= thresholds.established_active_days)
        & (tenure >= thresholds.established_tenure_days)
    )
    rich = (active >= thresholds.rich_active_days) & (lines >= thresholds.rich_lines)
    output[sparse] = SupportClass.SPARSE.value
    output[established] = SupportClass.ESTABLISHED.value
    output[rich] = SupportClass.RICH.value
    return output


@dataclass
class HierarchicalRateModel:
    """Beta-binomial partial pooling over a small, interpretable hierarchy."""

    prior_strength: float = 100.0
    minimum_group_support: int = 200
    global_rate: float = 0.0
    rates: dict[tuple[str, ...], tuple[float, int]] | None = None
    hierarchy: tuple[str, ...] = ("support_class", "lifecycle", "dominant_channel")

    def fit(self, frame: pd.DataFrame, target: str = "label_repeat") -> HierarchicalRateModel:
        y = frame[target].to_numpy(float)
        self.global_rate = float(y.mean())
        self.rates = {}
        for depth in range(1, len(self.hierarchy) + 1):
            columns = list(self.hierarchy[:depth])
            grouped = frame.groupby(columns, dropna=False)[target].agg(["sum", "count"])
            for key, row in grouped.iterrows():
                keys = key if isinstance(key, tuple) else (key,)
                count = int(row["count"])
                parent_key = tuple(str(item) for item in keys[:-1])
                parent = self.rates.get(parent_key, (self.global_rate, 0))[0]
                rate = float(
                    (row["sum"] + self.prior_strength * parent)
                    / (count + self.prior_strength)
                )
                self.rates[tuple(str(item) for item in keys)] = (rate, count)
        return self

    def predict(self, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        if self.rates is None:
            raise RuntimeError("hierarchical rate model is not fitted")
        probability, support = [], []
        for _, row in frame.iterrows():
            keys = tuple(str(row[column]) for column in self.hierarchy)
            selected = (self.global_rate, 0)
            for depth in range(1, len(keys) + 1):
                candidate = self.rates.get(keys[:depth])
                if candidate is not None and candidate[1] >= self.minimum_group_support:
                    selected = candidate
            probability.append(selected[0])
            support.append(selected[1])
        return np.asarray(probability), np.asarray(support)


@dataclass
class SparseRouter:
    sparse_classes: tuple[str, ...] = (
        SupportClass.VERY_SPARSE.value,
        SupportClass.SPARSE.value,
    )

    def route(
        self,
        support_class: Iterable[str],
        ranker_probability: np.ndarray,
        hierarchical_probability: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        support = np.asarray(list(support_class), object)
        sparse = np.isin(support, self.sparse_classes)
        output = np.where(sparse, hierarchical_probability, ranker_probability)
        route = np.where(sparse, "HIERARCHICAL_PRIOR", "ESTABLISHED_RANKER")
        return np.clip(output, 0, 1), route


def _logit(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(probability, float), 1e-8, 1 - 1e-8)
    return np.log(clipped / (1 - clipped))


def _sigmoid(value: np.ndarray | float) -> np.ndarray:
    return 1 / (1 + np.exp(-np.asarray(value)))


def logit_shift_reconcile(
    probability: np.ndarray,
    target_buyers: float,
    *,
    tolerance: float = 1e-6,
    max_iterations: int = 100,
) -> tuple[np.ndarray, float]:
    """Preserve ranking while matching an independently selected aggregate forecast."""
    probability = np.asarray(probability, float)
    if not 0 <= target_buyers <= len(probability):
        raise ValueError("target buyers must be between zero and population size")
    if len(probability) == 0:
        return probability, 0.0
    logits = _logit(probability)
    lower, upper = -40.0, 40.0
    for _ in range(max_iterations):
        delta = (lower + upper) / 2
        reconciled = _sigmoid(logits + delta)
        difference = float(reconciled.sum() - target_buyers)
        if abs(difference) <= tolerance:
            return reconciled, delta
        if difference > 0:
            upper = delta
        else:
            lower = delta
    reconciled = _sigmoid(logits + (lower + upper) / 2)
    if abs(float(reconciled.sum()) - target_buyers) > max(tolerance, 1e-4):
        raise RuntimeError("reconciliation did not converge")
    return reconciled, (lower + upper) / 2


def apply_group_logit_adjustments(
    probability: np.ndarray,
    groups: Iterable[str],
    adjustments: dict[str, tuple[float, int]],
    *,
    minimum_support: int,
) -> np.ndarray:
    """Apply only development-fitted, sufficiently supported subgroup intercept shifts."""
    logits = _logit(probability)
    deltas = np.asarray(
        [
            adjustments.get(str(group), (0.0, 0))[0]
            if adjustments.get(str(group), (0.0, 0))[1] >= minimum_support
            else 0.0
            for group in groups
        ]
    )
    return _sigmoid(logits + deltas)


@dataclass(frozen=True)
class AggregateCandidate:
    name: str
    errors: tuple[float, ...]
    biases: tuple[float, ...]

    @property
    def mean_error(self) -> float:
        return float(np.mean(self.errors))

    @property
    def worst_error(self) -> float:
        return float(max(self.errors))

    @property
    def absolute_bias(self) -> float:
        return float(abs(np.mean(self.biases)))


def select_aggregate_candidate(candidates: Iterable[AggregateCandidate]) -> AggregateCandidate:
    items = list(candidates)
    if not items:
        raise ValueError("at least one aggregate candidate is required")
    return min(items, key=lambda item: (item.mean_error, item.worst_error, item.absolute_bias))


PRIOR_EXPOSED_TARGETS = (
    (date(2020, 6, 8), date(2020, 7, 8)),
    (date(2020, 7, 1), date(2020, 7, 31)),
    (date(2020, 7, 25), date(2020, 8, 24)),
    (date(2020, 8, 24), date(2020, 9, 23)),
)


def _overlaps(start: date, end: date, other_start: date, other_end: date) -> bool:
    return start < other_end and other_start < end


def select_safe_v2_cutoffs(
    data_min: date,
    data_max: date,
    *,
    lookback_days: int = 365,
    horizon_days: int = 30,
    development_count: int = 5,
) -> dict[str, Any]:
    """Enumerate clean cutoffs without consulting any target outcomes."""
    first = data_min + timedelta(days=lookback_days)
    last = data_max + timedelta(days=1 - horizon_days)
    candidates: list[date] = []
    current = first
    while current <= last:
        end = current + timedelta(days=horizon_days)
        if not any(
            _overlaps(current, end, old_start, old_end)
            for old_start, old_end in PRIOR_EXPOSED_TARGETS
        ):
            candidates.append(current)
        current += timedelta(days=1)
    if not candidates:
        return {
            "candidates": [],
            "development": [],
            "official_final": None,
            "status": "NO_SAFE_CUTOFF",
        }
    official = candidates[-1]
    earlier = [item for item in candidates if item + timedelta(days=horizon_days) <= official]
    # Walk backwards in non-overlapping horizon steps. Consecutive daily cutoffs would
    # masquerade as five temporal replications while sharing almost every label.
    development_reversed: list[date] = []
    latest_allowed = official - timedelta(days=horizon_days)
    for item in reversed(earlier):
        if item <= latest_allowed:
            development_reversed.append(item)
            latest_allowed = item - timedelta(days=horizon_days)
            if len(development_reversed) == development_count:
                break
    development = list(reversed(development_reversed))
    return {
        "candidates": [item.isoformat() for item in candidates],
        "development": [item.isoformat() for item in development],
        "official_final": official.isoformat(),
        "status": "FROZEN_FROM_DATES_ONLY",
    }


@dataclass
class FinalRunGuard:
    directory: Path

    @property
    def freeze_path(self) -> Path:
        return self.directory / "benchmark_freeze.json"

    @property
    def predictions_path(self) -> Path:
        return self.directory / "official_final_predictions.parquet"

    @property
    def evaluated_path(self) -> Path:
        return self.directory / "official_final_evaluated.json"

    def require_development_mode(self) -> None:
        if self.evaluated_path.exists():
            raise RuntimeError("official V2 final has already been evaluated")

    def freeze(self, config: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.evaluated_path.exists():
            raise RuntimeError("cannot replace freeze after official evaluation")
        self.freeze_path.write_text(json.dumps(config, indent=2, default=str) + "\n")

    def require_predictions_before_reveal(self) -> None:
        if not self.freeze_path.exists():
            raise RuntimeError("benchmark freeze missing")
        if not self.predictions_path.exists():
            raise RuntimeError("official predictions must exist before reveal")
        if self.evaluated_path.exists():
            raise RuntimeError("official V2 final can be evaluated only once")

    def mark_evaluated(self, payload: dict[str, Any]) -> None:
        self.require_predictions_before_reveal()
        self.evaluated_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def empirical_reliability(
    support: Iterable[str], subgroup_ece: Iterable[float], temporal_std: float
) -> np.ndarray:
    result = []
    for support_class, ece in zip(support, subgroup_ece, strict=True):
        if str(support_class) in {SupportClass.VERY_SPARSE.value, SupportClass.SPARSE.value}:
            result.append("LOW")
        elif float(ece) > 0.075 or temporal_std > 0.05:
            result.append("LOW")
        elif float(ece) <= 0.03 and temporal_std <= 0.02:
            result.append("HIGH")
        else:
            result.append("MEDIUM")
    return np.asarray(result)


def calibration_in_the_large(y: np.ndarray, probability: np.ndarray) -> float:
    observed = float(np.asarray(y).mean())
    expected = float(np.asarray(probability).mean())
    return math.log((observed + 1e-8) / (1 - observed + 1e-8)) - math.log(
        (expected + 1e-8) / (1 - expected + 1e-8)
    )
