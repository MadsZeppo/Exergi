"""Independent V7.1 DGP with explicit net action and switching costs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class V71WorldFamily(StrEnum):
    NULL = "NULL"
    HOMOGENEOUS_POSITIVE = "HOMOGENEOUS_POSITIVE"
    GLOBALLY_HARMFUL = "GLOBALLY_HARMFUL"
    MATERIAL_OBSERVABLE_LINEAR = "MATERIAL_OBSERVABLE_LINEAR"
    MATERIAL_OBSERVABLE_INTERACTION = "MATERIAL_OBSERVABLE_INTERACTION"
    NONMATERIAL_SPARSE = "NONMATERIAL_SPARSE"
    UNOBSERVABLE_HETEROGENEITY = "UNOBSERVABLE_HETEROGENEITY"
    DELAYED_REVERSAL = "DELAYED_REVERSAL"
    GRADUAL_DECAY = "GRADUAL_DECAY"
    COMMON_SHOCK = "COMMON_SHOCK"
    CAUSAL_SHIFT = "CAUSAL_SHIFT"
    HEAVY_TAILED_CP = "HEAVY_TAILED_CP"
    MISSING_RETURNS = "MISSING_RETURNS"
    ATTRITION = "ATTRITION"
    NONCOMPLIANCE = "NONCOMPLIANCE"
    PROPENSITY_CORRUPTION = "PROPENSITY_CORRUPTION"
    ACTION_FATIGUE = "ACTION_FATIGUE"
    REACTIVATION = "REACTIVATION"
    INSUFFICIENT_SUPPORT = "INSUFFICIENT_SUPPORT"


@dataclass(frozen=True)
class V71WorldSpec:
    world_id: str
    merchant_id: str
    action_family: str
    family: V71WorldFamily
    seed: int
    observations: int
    periods: int
    treatment_cost: float
    switching_cost: float
    subgroup_prevalence: float
    maturity_delay: int
    change_period: int
    noise_family: str


@dataclass(frozen=True)
class V71ObservedWorld:
    world_id: str
    features: np.ndarray
    feature_names: tuple[str, ...]
    assignment: np.ndarray
    received_treatment: np.ndarray
    logged_propensity: np.ndarray
    contribution_profit: np.ndarray
    observed: np.ndarray
    costs_identified: bool
    cluster: np.ndarray
    period: np.ndarray
    opportunity_signal: np.ndarray


@dataclass(frozen=True)
class V71OracleWorld:
    individual_net_effect: np.ndarray
    baseline_contribution_profit: np.ndarray
    actual_propensity: float
    treatment_cost: float
    switching_cost: float
    hidden_modifier: np.ndarray


def generate_v71_world(spec: V71WorldSpec) -> tuple[V71ObservedWorld, V71OracleWorld]:
    streams = np.random.SeedSequence(spec.seed).spawn(7)
    feature_rng, baseline_rng, effect_rng, assignment_rng, noise_rng, signal_rng, hidden_rng = (
        np.random.default_rng(stream) for stream in streams
    )
    n = spec.observations
    recency = feature_rng.exponential(50, n)
    frequency = feature_rng.poisson(3.5, n).astype(float)
    monetary = feature_rng.lognormal(3.5, 0.75, n)
    intent = feature_rng.beta(2.2, 3.8, n)
    loyalty = feature_rng.normal(0, 1, n)
    category = feature_rng.integers(0, 5, n).astype(float)
    tenure = feature_rng.exponential(400, n)
    period = np.arange(n) % spec.periods
    features = np.column_stack(
        [
            np.log1p(recency) / 5,
            np.log1p(frequency),
            np.log1p(monetary) / 5,
            intent,
            loyalty,
            category / 4,
            np.log1p(tenure) / 7,
            period / max(1, spec.periods - 1),
        ]
    )
    names = (
        "recency",
        "frequency",
        "monetary",
        "intent",
        "loyalty",
        "category",
        "tenure",
        "period",
    )
    beta = baseline_rng.normal(0, 0.22, features.shape[1])
    baseline = 7.5 + features @ beta + 0.75 * np.log1p(monetary)
    hidden = hidden_rng.normal(0, 1, n)
    scale = effect_rng.uniform(0.92, 1.08)
    gross_effect = _gross_effect(spec, features, hidden, period, scale)
    net_effect = gross_effect - spec.treatment_cost - spec.switching_cost

    propensity = 0.035 if spec.family is V71WorldFamily.INSUFFICIENT_SUPPORT else 0.5
    assignment = assignment_rng.random(n) < propensity
    received = assignment.copy()
    if spec.family is V71WorldFamily.NONCOMPLIANCE:
        received &= assignment_rng.random(n) < 0.58

    noise = noise_rng.normal(0, 2.0, n)
    if spec.noise_family == "student_t" or spec.family is V71WorldFamily.HEAVY_TAILED_CP:
        noise = noise_rng.standard_t(2.7, n) * 1.8
    if spec.noise_family == "zero_inflated":
        noise = np.where(noise_rng.random(n) < 0.45, -0.6 * baseline, noise)
    if spec.family is V71WorldFamily.COMMON_SHOCK:
        noise += np.where(period >= spec.change_period, -2.5, 0.0)
    realized = net_effect * received
    outcome = baseline + realized + noise

    observed = np.ones(n, dtype=bool)
    costs_identified = True
    if spec.family is V71WorldFamily.ATTRITION:
        observed = assignment_rng.random(n) > np.where(assignment, 0.20, 0.05)
    if spec.family is V71WorldFamily.MISSING_RETURNS:
        observed = period <= spec.periods - spec.maturity_delay - 1
        costs_identified = False
    logged = np.full(n, propensity)
    if spec.family is V71WorldFamily.PROPENSITY_CORRUPTION:
        logged[:] = 0.70
    opportunity = (
        0.45 * intent
        + 0.12 * features[:, 2]
        + 0.08 * features[:, 0]
        + signal_rng.normal(0, 0.75, n)
    )
    cluster = np.arange(n) // 4
    return (
        V71ObservedWorld(
            spec.world_id,
            features,
            names,
            assignment,
            received,
            logged,
            outcome,
            observed,
            costs_identified,
            cluster,
            period,
            opportunity,
        ),
        V71OracleWorld(
            net_effect,
            baseline,
            propensity,
            spec.treatment_cost,
            spec.switching_cost,
            hidden,
        ),
    )


def _gross_effect(
    spec: V71WorldSpec,
    x: np.ndarray,
    hidden: np.ndarray,
    period: np.ndarray,
    scale: float,
) -> np.ndarray:
    family = spec.family
    n = len(x)
    if family in {V71WorldFamily.NULL, V71WorldFamily.COMMON_SHOCK}:
        return np.zeros(n)
    if family is V71WorldFamily.GLOBALLY_HARMFUL:
        return np.full(n, -1.0 * scale)
    if family in {
        V71WorldFamily.HOMOGENEOUS_POSITIVE,
        V71WorldFamily.HEAVY_TAILED_CP,
        V71WorldFamily.MISSING_RETURNS,
        V71WorldFamily.ATTRITION,
        V71WorldFamily.NONCOMPLIANCE,
        V71WorldFamily.PROPENSITY_CORRUPTION,
        V71WorldFamily.INSUFFICIENT_SUPPORT,
    }:
        return np.full(n, 1.25 * scale)
    if family is V71WorldFamily.MATERIAL_OBSERVABLE_LINEAR:
        score = 1.4 * x[:, 3] + 0.7 * x[:, 4] - 0.35 * x[:, 0]
        threshold = float(np.quantile(score, 0.55))
        return np.where(score > threshold, 2.2 * scale, 0.05)
    if family is V71WorldFamily.MATERIAL_OBSERVABLE_INTERACTION:
        score = x[:, 3] * (x[:, 4] > 0) + 0.35 * (x[:, 5] < 0.3)
        threshold = float(np.quantile(score, 0.78))
        return np.where(score > threshold, 3.3 * scale, 0.02)
    if family is V71WorldFamily.NONMATERIAL_SPARSE:
        score = x[:, 3] + 0.25 * x[:, 4]
        threshold = float(np.quantile(score, 1 - spec.subgroup_prevalence))
        return np.where(score > threshold, 2.0 * scale, 0.0)
    if family is V71WorldFamily.UNOBSERVABLE_HETEROGENEITY:
        threshold = float(np.quantile(hidden, 1 - spec.subgroup_prevalence))
        return np.where(hidden > threshold, 2.6 * scale, 0.0)
    if family is V71WorldFamily.DELAYED_REVERSAL:
        return np.where(period < spec.change_period, -0.9 * scale, 1.8 * scale)
    if family is V71WorldFamily.GRADUAL_DECAY:
        return 1.8 * scale * np.exp(-period / max(1, spec.periods / 2))
    if family is V71WorldFamily.CAUSAL_SHIFT:
        return np.where(period < spec.change_period, 1.5 * scale, -0.6 * scale)
    if family is V71WorldFamily.ACTION_FATIGUE:
        return 1.7 * scale * np.exp(-period / 2.8)
    if family is V71WorldFamily.REACTIVATION:
        return np.where(
            period < spec.change_period,
            1.2 * scale,
            np.where(period < spec.change_period + 2, -1.1 * scale, 1.4 * scale),
        )
    raise AssertionError(f"unhandled V7.1 family: {family}")
