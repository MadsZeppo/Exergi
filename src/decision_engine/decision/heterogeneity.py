"""Fail-closed gate for individualized treatment policies."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm


@dataclass(frozen=True)
class HeterogeneityEvidence:
    out_of_fold: bool
    rate_or_autoc: float
    rate_standard_error: float
    shuffle_p_value: float
    fold_effects: tuple[float, ...]
    personalized_minus_static_scores: np.ndarray
    clusters: np.ndarray
    effective_sample_size: float
    treatment_regions_supported: bool
    candidate_tests: int


@dataclass(frozen=True)
class HeterogeneityDecision:
    personalization_supported: bool
    selected_policy: str
    incremental_value: float
    lower: float
    multiplicity_adjusted_alpha: float
    checks: dict[str, bool]
    reason: str


def _cluster_se(values: np.ndarray, clusters: np.ndarray) -> float:
    centered = values - np.mean(values)
    labels, inverse = np.unique(clusters, return_inverse=True)
    if len(labels) < 2:
        return float("inf")
    sums = np.bincount(inverse, weights=centered)
    return float(np.sqrt(len(labels) / (len(labels) - 1) * np.sum(sums**2) / len(values) ** 2))


class HeterogeneityGate:
    def __init__(self, *, family_alpha: float = 0.05, minimum_ess: float = 200) -> None:
        self.family_alpha = family_alpha
        self.minimum_ess = minimum_ess

    def evaluate(
        self,
        evidence: HeterogeneityEvidence,
        *,
        best_static_policy: str,
    ) -> HeterogeneityDecision:
        values = np.asarray(evidence.personalized_minus_static_scores, dtype=float)
        clusters = np.asarray(evidence.clusters)
        if values.ndim != 1 or len(values) != len(clusters) or not len(values):
            raise ValueError("heterogeneity value scores must align and be non-empty")
        adjusted = self.family_alpha / max(1, evidence.candidate_tests)
        estimate = float(np.mean(values))
        se = _cluster_se(values, clusters)
        lower = estimate - float(norm.ppf(1 - adjusted)) * se
        rate_lower = evidence.rate_or_autoc - float(norm.ppf(1 - adjusted)) * max(
            evidence.rate_standard_error, 0.0
        )
        signs = np.sign(np.asarray(evidence.fold_effects, dtype=float))
        stable = len(signs) >= 2 and (np.mean(signs > 0) >= 0.8)
        checks = {
            "out_of_fold": evidence.out_of_fold,
            "rate_positive": bool(rate_lower > 0),
            "shuffle_calibrated": bool(evidence.shuffle_p_value <= adjusted),
            "fold_stable": bool(stable),
            "beats_best_static": bool(lower > 0),
            "effective_sample_size": bool(
                evidence.effective_sample_size >= self.minimum_ess
            ),
            "treatment_regions_supported": evidence.treatment_regions_supported,
        }
        passed = all(checks.values())
        return HeterogeneityDecision(
            passed,
            "INDIVIDUALIZED" if passed else best_static_policy,
            estimate,
            lower,
            adjusted,
            checks,
            (
                "personalization beat the best static supported policy"
                if passed
                else "PERSONALIZATION_NOT_SUPPORTED"
            ),
        )
