"""Honest comparison of a small preregistered segment-policy set."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm


@dataclass(frozen=True)
class SegmentDefinition:
    name: str
    eligible: np.ndarray
    preregistered: bool = True


@dataclass(frozen=True)
class SegmentPolicyValue:
    name: str
    acted_fraction: float
    incremental_value: float
    standard_error: float
    lower: float
    upper: float
    supported: bool


@dataclass(frozen=True)
class SegmentPolicyDecision:
    selected: SegmentPolicyValue
    candidates: tuple[SegmentPolicyValue, ...]
    fallback_to_bau: bool
    reason: str


def _cluster_se(values: np.ndarray, clusters: np.ndarray) -> float:
    centered = values - np.mean(values)
    labels, inverse = np.unique(clusters, return_inverse=True)
    if len(labels) < 2:
        return float("inf")
    sums = np.bincount(inverse, weights=centered)
    return float(np.sqrt(len(labels) / (len(labels) - 1) * np.sum(sums**2) / len(values) ** 2))


class SegmentPolicyEngine:
    def __init__(self, *, alpha: float = 0.05, minimum_segment_n: int = 40) -> None:
        self.alpha = alpha
        self.minimum_segment_n = minimum_segment_n

    def select(
        self,
        influence_scores: np.ndarray,
        clusters: np.ndarray,
        segments: tuple[SegmentDefinition, ...],
    ) -> SegmentPolicyDecision:
        scores = np.asarray(influence_scores, dtype=float)
        group = np.asarray(clusters)
        if scores.ndim != 1 or len(scores) != len(group):
            raise ValueError("policy scores and clusters must align")
        if any(not segment.preregistered for segment in segments):
            raise ValueError("segment mining is not allowed in policy evaluation")
        definitions = (SegmentDefinition("BAU", np.zeros(len(scores), dtype=bool)), *segments)
        critical = float(norm.ppf(1 - self.alpha))
        rows: list[SegmentPolicyValue] = []
        for segment in definitions:
            mask = np.asarray(segment.eligible, dtype=bool)
            if mask.shape != scores.shape:
                raise ValueError("segment masks must align with scores")
            values = np.where(mask, scores, 0.0)
            estimate = float(np.mean(values))
            se = _cluster_se(values, group) if np.any(mask) else 0.0
            supported = segment.name == "BAU" or int(np.sum(mask)) >= self.minimum_segment_n
            rows.append(
                SegmentPolicyValue(
                    segment.name,
                    float(np.mean(mask)),
                    estimate,
                    se,
                    estimate - critical * se,
                    estimate + critical * se,
                    supported,
                )
            )
        eligible = [row for row in rows if row.supported and row.lower > 0]
        selected = max(eligible, key=lambda row: row.incremental_value) if eligible else rows[0]
        return SegmentPolicyDecision(
            selected,
            tuple(rows),
            selected.name == "BAU",
            (
                "selected supported segment with positive one-sided lower bound"
                if selected.name != "BAU"
                else "no preregistered segment beat BAU with a positive lower bound"
            ),
        )
