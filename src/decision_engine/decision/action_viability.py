"""Population-level randomized action viability, independent of personalization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from scipy.stats import norm
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold

from decision_engine.core.authority import ClaimAuthority


class ViabilityStatus(StrEnum):
    VIABLE = "VIABLE"
    HARMFUL = "HARMFUL"
    UNCERTAIN = "UNCERTAIN"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class RandomizedEconomicEvidence:
    outcome: np.ndarray
    treatment: np.ndarray
    propensity: np.ndarray
    pre_treatment_features: np.ndarray
    cluster: np.ndarray
    feature_names: tuple[str, ...]
    authority: ClaimAuthority
    assignment_provenance: str
    costs_identified: bool


@dataclass(frozen=True)
class ActionViabilityConfig:
    folds: int = 3
    alpha: float = 0.05
    minimum_effect: float = 0.0
    minimum_observations: int = 120
    minimum_arm_observations: int = 40
    minimum_clusters: int = 8
    propensity_floor: float = 0.05
    ridge_alpha: float = 1.0
    seed: int = 7_001


@dataclass(frozen=True)
class ActionViabilityReport:
    status: ViabilityStatus
    estimate: float
    standard_error: float
    lower: float
    upper: float
    probability_positive: float
    observations: int
    clusters: int
    treated: int
    control: int
    effective_sample_size: float
    method: str
    authority: ClaimAuthority
    support_passed: bool
    reasons: tuple[str, ...]
    influence_scores: np.ndarray


def _cluster_standard_error(scores: np.ndarray, cluster: np.ndarray) -> float:
    centered = scores - np.mean(scores)
    labels, inverse = np.unique(cluster, return_inverse=True)
    if len(labels) < 2:
        return float("inf")
    sums = np.bincount(inverse, weights=centered)
    correction = len(labels) / (len(labels) - 1)
    return float(np.sqrt(correction * np.sum(sums**2) / len(scores) ** 2))


def _effective_sample_size(treatment: np.ndarray, propensity: np.ndarray) -> float:
    weights = np.where(treatment, 1 / propensity, 1 / (1 - propensity))
    return float(np.sum(weights) ** 2 / np.sum(weights**2))


class ActionViabilityEngine:
    """Estimate average incremental contribution profit against BAU with strict OOF nuisances."""

    def __init__(self, config: ActionViabilityConfig | None = None) -> None:
        self.config = config or ActionViabilityConfig()

    def evaluate(self, evidence: RandomizedEconomicEvidence) -> ActionViabilityReport:
        config = self.config
        y = np.asarray(evidence.outcome, dtype=float)
        a = np.asarray(evidence.treatment, dtype=bool)
        p = np.asarray(evidence.propensity, dtype=float)
        x = np.asarray(evidence.pre_treatment_features, dtype=float)
        cluster = np.asarray(evidence.cluster)
        if y.ndim != 1 or x.ndim != 2 or not (len(y) == len(a) == len(p) == len(x) == len(cluster)):
            raise ValueError("randomized evidence arrays must be aligned")
        if x.shape[1] != len(evidence.feature_names):
            raise ValueError("feature names do not match the pre-treatment matrix")
        forbidden = {"treatment", "exposure", "outcome", "conversion", "visit", "profit"}
        if forbidden.intersection(name.lower() for name in evidence.feature_names):
            raise ValueError("post-treatment or outcome field entered viability features")
        if np.any(~np.isfinite(y)) or np.any(~np.isfinite(x)) or np.any(~np.isfinite(p)):
            raise ValueError("viability inputs must be finite")
        if np.any((p < config.propensity_floor) | (p > 1 - config.propensity_floor)):
            raise ValueError("known propensity violates support floor")
        n = len(y)
        treated = int(np.sum(a))
        control = n - treated
        clusters = len(np.unique(cluster))
        ess = _effective_sample_size(a, p)
        reasons: list[str] = []
        if "RANDOM" not in evidence.assignment_provenance.upper():
            reasons.append("randomized assignment provenance is not established")
        if not evidence.costs_identified:
            reasons.append("contribution-profit costs are not identified")
        if n < config.minimum_observations:
            reasons.append("insufficient total observations")
        if min(treated, control) < config.minimum_arm_observations:
            reasons.append("insufficient treatment-arm support")
        if clusters < config.minimum_clusters:
            reasons.append("insufficient independent clusters")
        support = not reasons
        if not support:
            return ActionViabilityReport(
                ViabilityStatus.INSUFFICIENT,
                0.0,
                float("inf"),
                -float("inf"),
                float("inf"),
                0.5,
                n,
                clusters,
                treated,
                control,
                ess,
                "CROSS_FITTED_AIPW_CUPED",
                evidence.authority,
                False,
                tuple(reasons),
                np.asarray([], dtype=float),
            )
        folds = min(config.folds, treated, control)
        splitter = KFold(n_splits=folds, shuffle=True, random_state=config.seed)
        m0 = np.zeros(n)
        m1 = np.zeros(n)
        for _fold, (train, test) in enumerate(splitter.split(x)):
            for arm, target in ((False, m0), (True, m1)):
                arm_train = train[a[train] == arm]
                if len(arm_train) < 2:
                    raise ValueError("cross-fitting fold lacks an assignment arm")
                model = Ridge(alpha=config.ridge_alpha)
                model.fit(x[arm_train], y[arm_train])
                target[test] = model.predict(x[test])
        scores = m1 - m0 + a * (y - m1) / p - (~a) * (y - m0) / (1 - p)
        estimate = float(np.mean(scores))
        se = _cluster_standard_error(scores, cluster)
        critical = float(norm.ppf(1 - config.alpha / 2))
        lower = estimate - critical * se
        upper = estimate + critical * se
        probability = float(norm.cdf(estimate / max(se, 1e-12)))
        status = ViabilityStatus.UNCERTAIN
        if lower > config.minimum_effect:
            status = ViabilityStatus.VIABLE
        elif upper < 0:
            status = ViabilityStatus.HARMFUL
        return ActionViabilityReport(
            status,
            estimate,
            se,
            lower,
            upper,
            probability,
            n,
            clusters,
            treated,
            control,
            ess,
            "CROSS_FITTED_AIPW_CUPED",
            evidence.authority,
            True,
            tuple(reasons),
            scores,
        )
