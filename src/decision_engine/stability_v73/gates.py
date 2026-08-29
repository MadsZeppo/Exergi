"""Preregistered V7.3 stability gates over observable randomized evidence only."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.stats import norm

from .contracts import GateDecision, GateInput

CANDIDATE_GATES = (
    "existing_v72_fold_veto",
    "repeated_stratified",
    "repeated_arm_balanced",
    "median_of_means",
    "influence_bounded",
    "bootstrap_positive_probability",
    "simultaneous_lcb",
    "cross_fitted_aipw_lcb",
    "bayesian_positive_probability",
    "distributionally_robust",
    "combined_economic",
)


@dataclass(frozen=True)
class _Estimate:
    point: float
    standard_error: float
    lower_95: float


@dataclass(frozen=True)
class EvidenceBundle:
    common_pass: bool
    common_reasons: tuple[str, ...]
    point: float
    standard_error: float
    lower_95: float
    fold_net: tuple[float, ...]
    leave_one_fold_out_net: tuple[float, ...]
    repeated_stratified_positive_fraction: float
    repeated_balanced_positive_fraction: float
    median_of_means_lower: float
    capped_995_lower: float
    largest_influence_share: float
    bootstrap_positive_probability: float
    bootstrap_lower_95: float
    simultaneous_lower: float
    aipw_point: float
    aipw_standard_error: float
    aipw_lower_95: float
    bayesian_positive_probability: float
    distributionally_robust_lower: float
    ess_control: float
    ess_treatment: float
    mature_fraction: float
    attrition_difference: float


def _estimate(y: NDArray[np.float64], treatment: NDArray[np.int64], cost: float) -> _Estimate:
    treated, control = y[treatment == 1], y[treatment == 0]
    if len(treated) < 2 or len(control) < 2:
        return _Estimate(float("nan"), float("inf"), float("-inf"))
    point = float(treated.mean() - control.mean() - cost)
    se = float(np.sqrt(treated.var(ddof=1) / len(treated) + control.var(ddof=1) / len(control)))
    return _Estimate(point, se, point - float(norm.ppf(0.975)) * se)


def _strata(features: NDArray[np.float64]) -> NDArray[np.int64]:
    cuts = np.quantile(features[:, 0], (0.25, 0.50, 0.75))
    return np.digitize(features[:, 0], cuts).astype(np.int64)


def _stratified_estimate(
    y: NDArray[np.float64],
    treatment: NDArray[np.int64],
    strata: NDArray[np.int64],
    cost: float,
) -> _Estimate:
    n = len(y)
    point = -cost
    influence = np.zeros(n, dtype=float)
    for level in np.unique(strata):
        member = strata == level
        treated, control = member & (treatment == 1), member & (treatment == 0)
        if int(treated.sum()) < 2 or int(control.sum()) < 2:
            return _Estimate(float("nan"), float("inf"), float("-inf"))
        weight = float(member.mean())
        mean_t, mean_c = float(y[treated].mean()), float(y[control].mean())
        point += weight * (mean_t - mean_c)
        influence[treated] = n * weight * (y[treated] - mean_t) / int(treated.sum())
        influence[control] = -n * weight * (y[control] - mean_c) / int(control.sum())
    se = float(influence.std(ddof=1) / np.sqrt(n))
    return _Estimate(point, se, point - float(norm.ppf(0.975)) * se)


def _balanced_fold(
    treatment: NDArray[np.int64],
    split_key: NDArray[np.uint64],
    folds: int,
    repetition: int,
    strata: NDArray[np.int64] | None = None,
) -> NDArray[np.int64]:
    assignment = np.empty(len(treatment), dtype=np.int64)
    levels = np.zeros(len(treatment), dtype=np.int64) if strata is None else strata
    constant = np.uint64((repetition + 1) * 0x9E3779B1)
    for arm in (0, 1):
        for level in np.unique(levels):
            rows = np.flatnonzero((treatment == arm) & (levels == level))
            order = np.argsort(np.bitwise_xor(split_key[rows], constant))
            assignment[rows[order]] = np.arange(len(rows), dtype=np.int64) % folds
    return assignment


def _fold_effects(
    y: NDArray[np.float64],
    treatment: NDArray[np.int64],
    split_key: NDArray[np.uint64],
    cost: float,
    folds: int,
    repetition: int = 0,
    strata: NDArray[np.int64] | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    fold = _balanced_fold(treatment, split_key, folds, repetition, strata)
    within = np.asarray(
        [
            _estimate(y[fold == value], treatment[fold == value], cost).point
            for value in range(folds)
        ]
    )
    leave_one_out = np.asarray(
        [
            _estimate(y[fold != value], treatment[fold != value], cost).point
            for value in range(folds)
        ]
    )
    return within, leave_one_out


def _cuped(
    y: NDArray[np.float64],
    treatment: NDArray[np.int64],
    feature: NDArray[np.float64],
    cost: float,
) -> _Estimate:
    variance = float(np.var(feature, ddof=1))
    theta = 0.0 if variance == 0 else float(np.cov(y, feature, ddof=1)[0, 1] / variance)
    adjusted = y - theta * (feature - feature.mean())
    return _estimate(adjusted, treatment, cost)


def _cross_fitted_aipw(
    y: NDArray[np.float64],
    treatment: NDArray[np.int64],
    features: NDArray[np.float64],
    split_key: NDArray[np.uint64],
    propensity: NDArray[np.float64],
    cost: float,
    folds: int,
) -> tuple[_Estimate, NDArray[np.float64]]:
    fold = np.asarray(split_key % np.uint64(folds), dtype=np.int64)
    m0, m1 = np.zeros(len(y)), np.zeros(len(y))
    design = np.column_stack((np.ones(len(y)), features))
    for value in range(folds):
        train, test = fold != value, fold == value
        for arm, target in ((0, m0), (1, m1)):
            rows = train & (treatment == arm)
            gram = design[rows].T @ design[rows] + np.eye(design.shape[1]) * 1e-3
            beta = np.linalg.solve(gram, design[rows].T @ y[rows])
            target[test] = design[test] @ beta
    p = propensity
    score = m1 - m0 + treatment * (y - m1) / p - (1 - treatment) * (y - m0) / (1 - p) - cost
    point = float(score.mean())
    se = float(score.std(ddof=1) / np.sqrt(len(score)))
    return _Estimate(point, se, point - float(norm.ppf(0.975)) * se), score


def _bootstrap(
    y: NDArray[np.float64],
    treatment: NDArray[np.int64],
    cost: float,
    seed: int,
    replicates: int,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    control, treated = y[treatment == 0], y[treatment == 1]
    values = np.empty(replicates, dtype=float)
    for start in range(0, replicates, 25):
        width = min(25, replicates - start)
        c_index = rng.integers(0, len(control), size=(width, len(control)))
        t_index = rng.integers(0, len(treated), size=(width, len(treated)))
        values[start : start + width] = (
            treated[t_index].mean(axis=1) - control[c_index].mean(axis=1) - cost
        )
    return float(np.mean(values > 0)), float(np.quantile(values, 0.025))


def _common_support(data: GateInput) -> tuple[bool, tuple[str, ...], dict[str, float]]:
    treatment = data.treatment
    mature_fraction = float(data.mature.mean())
    mature_by_arm = [float(data.mature[treatment == arm].mean()) for arm in (0, 1)]
    attrition_difference = abs(mature_by_arm[1] - mature_by_arm[0])
    p = data.logged_propensity
    observed = data.mature
    treated_n, control_n = (
        int(np.sum(observed & (treatment == 1))),
        int(np.sum(observed & (treatment == 0))),
    )
    ess_t = float(treated_n)
    ess_c = float(control_n)
    reasons: list[str] = []
    if not data.support_valid:
        reasons.append("unsupported_action")
    if not data.assignment_integrity_valid or data.assignment_contamination:
        reasons.append("assignment_integrity")
    if data.post_treatment_feature_present:
        reasons.append("post_treatment_feature")
    if mature_fraction < 0.95:
        reasons.append("immature_outcomes")
    if attrition_difference > 0.05:
        reasons.append("differential_attrition")
    if np.min(p) < 0.10 or np.max(p) > 0.90:
        reasons.append("insufficient_overlap")
    if ess_t < 100 or ess_c < 100:
        reasons.append("insufficient_ess")
    if data.action_cost > data.per_unit_budget:
        reasons.append("budget")
    return (
        not reasons,
        tuple(reasons),
        {
            "mature_fraction": mature_fraction,
            "attrition_difference": attrition_difference,
            "ess_treatment": ess_t,
            "ess_control": ess_c,
        },
    )


def compute_evidence(
    data: GateInput,
    *,
    seed: int,
    folds: int = 5,
    bootstrap_replicates: int = 200,
) -> EvidenceBundle:
    """Compute observable evidence; evaluator truth is absent by construction."""

    common_pass, common_reasons, diagnostics = _common_support(data)
    observed = data.mature
    y = data.outcome[observed]
    treatment = data.treatment[observed]
    features = data.features[observed]
    split_key = np.bitwise_xor(data.split_key[observed], np.uint64(seed))
    propensity = data.logged_propensity[observed]
    raw = _estimate(y, treatment, data.action_cost)
    strata = _strata(features)
    stratified = _stratified_estimate(y, treatment, strata, data.action_cost)
    cuped = _cuped(y, treatment, features[:, 0], data.action_cost)
    aipw, aipw_score = _cross_fitted_aipw(
        y, treatment, features, split_key, propensity, data.action_cost, folds
    )
    fold_net, leave_one_out = _fold_effects(y, treatment, split_key, data.action_cost, folds)
    repeated_balanced: list[float] = []
    repeated_stratified: list[float] = []
    for repetition in range(10):
        balanced, _ = _fold_effects(y, treatment, split_key, data.action_cost, folds, repetition)
        stratified_fold, _ = _fold_effects(
            y, treatment, split_key, data.action_cost, folds, repetition, strata
        )
        repeated_balanced.extend(balanced.tolist())
        repeated_stratified.extend(stratified_fold.tolist())

    blocks, _ = _fold_effects(y, treatment, split_key, data.action_cost, 10)
    median = float(np.median(blocks))
    mad = float(np.median(np.abs(blocks - median)))
    mom_lower = median - float(norm.ppf(0.975)) * 1.4826 * mad / np.sqrt(len(blocks))

    cap_995 = float(np.quantile(y, 0.995))
    cap_999 = float(np.quantile(y, 0.999))
    capped_995 = _estimate(np.minimum(y, cap_995), treatment, data.action_cost)
    capped_999 = _estimate(np.minimum(y, cap_999), treatment, data.action_cost)
    centered = aipw_score - aipw_score.mean()
    influence_share = float(np.max(np.abs(centered)) / max(np.sum(np.abs(centered)), 1e-12))
    bootstrap_probability, bootstrap_lower = _bootstrap(
        y, treatment, data.action_cost, seed, bootstrap_replicates
    )
    critical = float(norm.ppf(1 - 0.025 / 3))
    simultaneous = min(
        raw.point - critical * raw.standard_error,
        cuped.point - critical * cuped.standard_error,
        stratified.point - critical * stratified.standard_error,
    )
    posterior = float(norm.cdf(raw.point / max(raw.standard_error, 1e-12)))
    dro_lower = min(raw.lower_95, capped_999.lower_95, capped_995.lower_95)
    return EvidenceBundle(
        common_pass=common_pass,
        common_reasons=common_reasons,
        point=raw.point,
        standard_error=raw.standard_error,
        lower_95=raw.lower_95,
        fold_net=tuple(float(value) for value in fold_net),
        leave_one_fold_out_net=tuple(float(value) for value in leave_one_out),
        repeated_stratified_positive_fraction=float(np.mean(np.asarray(repeated_stratified) > 0)),
        repeated_balanced_positive_fraction=float(np.mean(np.asarray(repeated_balanced) > 0)),
        median_of_means_lower=mom_lower,
        capped_995_lower=capped_995.lower_95,
        largest_influence_share=influence_share,
        bootstrap_positive_probability=bootstrap_probability,
        bootstrap_lower_95=bootstrap_lower,
        simultaneous_lower=simultaneous,
        aipw_point=aipw.point,
        aipw_standard_error=aipw.standard_error,
        aipw_lower_95=aipw.lower_95,
        bayesian_positive_probability=posterior,
        distributionally_robust_lower=dro_lower,
        ess_control=diagnostics["ess_control"],
        ess_treatment=diagnostics["ess_treatment"],
        mature_fraction=diagnostics["mature_fraction"],
        attrition_difference=diagnostics["attrition_difference"],
    )


def assess_candidates(evidence: EvidenceBundle) -> dict[str, GateDecision]:
    support = evidence.common_pass
    positive_folds = int(np.sum(np.asarray(evidence.fold_net) > 0))
    existing = bool(
        support
        and evidence.lower_95 > 0
        and positive_folds >= max(len(evidence.fold_net) - 1, 1)
        and min(evidence.fold_net) >= -0.05
        and all(value > 0 for value in evidence.leave_one_fold_out_net)
    )
    conditions = {
        "existing_v72_fold_veto": existing,
        "repeated_stratified": bool(
            support
            and evidence.lower_95 > 0
            and evidence.repeated_stratified_positive_fraction >= 0.80
        ),
        "repeated_arm_balanced": bool(
            support
            and evidence.lower_95 > 0
            and evidence.repeated_balanced_positive_fraction >= 0.80
        ),
        "median_of_means": bool(support and evidence.median_of_means_lower > 0),
        "influence_bounded": bool(
            support and evidence.capped_995_lower > 0 and evidence.largest_influence_share <= 0.35
        ),
        "bootstrap_positive_probability": bool(
            support
            and evidence.bootstrap_positive_probability >= 0.975
            and evidence.bootstrap_lower_95 > 0
        ),
        "simultaneous_lcb": bool(support and evidence.simultaneous_lower > 0),
        "cross_fitted_aipw_lcb": bool(support and evidence.aipw_lower_95 > 0),
        "bayesian_positive_probability": bool(
            support and evidence.bayesian_positive_probability > 0.99
        ),
        "distributionally_robust": bool(support and evidence.distributionally_robust_lower > 0),
        "combined_economic": bool(
            support
            and evidence.aipw_lower_95 > 0
            and evidence.bootstrap_positive_probability >= 0.975
            and evidence.repeated_balanced_positive_fraction >= 0.75
            and evidence.largest_influence_share <= 0.35
        ),
    }
    lower = {
        "existing_v72_fold_veto": min(evidence.lower_95, min(evidence.fold_net)),
        "repeated_stratified": evidence.lower_95,
        "repeated_arm_balanced": evidence.lower_95,
        "median_of_means": evidence.median_of_means_lower,
        "influence_bounded": evidence.capped_995_lower,
        "bootstrap_positive_probability": evidence.bootstrap_lower_95,
        "simultaneous_lcb": evidence.simultaneous_lower,
        "cross_fitted_aipw_lcb": evidence.aipw_lower_95,
        "bayesian_positive_probability": evidence.lower_95,
        "distributionally_robust": evidence.distributionally_robust_lower,
        "combined_economic": min(evidence.aipw_lower_95, evidence.bootstrap_lower_95),
    }
    confidence = max(
        evidence.bootstrap_positive_probability, evidence.bayesian_positive_probability
    )
    return {
        name: GateDecision(
            gate=name,
            act=act,
            point_net_value=evidence.aipw_point
            if "aipw" in name or name == "combined_economic"
            else evidence.point,
            lower_bound=lower[name],
            confidence=confidence,
            supported=support,
            reasons=() if act else evidence.common_reasons or ("stability_threshold",),
        )
        for name, act in conditions.items()
    }
