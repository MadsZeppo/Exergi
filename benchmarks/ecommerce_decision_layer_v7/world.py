"""Independent V7 customer-level DGP; policy code never receives oracle effects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class WorldFamily(StrEnum):
    NULL = "NULL"
    HOMOGENEOUS_POSITIVE = "HOMOGENEOUS_POSITIVE"
    SPARSE_HETEROGENEITY = "SPARSE_HETEROGENEITY"
    QUALITATIVE_HETEROGENEITY = "QUALITATIVE_HETEROGENEITY"
    GLOBALLY_HARMFUL = "GLOBALLY_HARMFUL"
    DELAYED_REVERSAL = "DELAYED_REVERSAL"
    GRADUAL_DECAY = "GRADUAL_DECAY"
    COMMON_SHOCK = "COMMON_SHOCK"
    CAUSAL_SHIFT = "CAUSAL_SHIFT"
    HEAVY_TAILED_CP = "HEAVY_TAILED_CP"
    ZERO_INFLATED = "ZERO_INFLATED"
    MISSING_DELAYED_RETURNS = "MISSING_DELAYED_RETURNS"
    NONCOMPLIANCE = "NONCOMPLIANCE"
    ATTRITION = "ATTRITION"
    PROPENSITY_LOGGING_ERROR = "PROPENSITY_LOGGING_ERROR"
    INTERFERENCE = "INTERFERENCE"
    ACTION_FATIGUE = "ACTION_FATIGUE"
    NOVELTY_DECAY = "NOVELTY_DECAY"
    INSUFFICIENT_SUPPORT = "INSUFFICIENT_SUPPORT"


@dataclass(frozen=True)
class WorldSpec:
    world_id: str
    merchant_id: str
    action_family: str
    family: WorldFamily
    seed: int
    observations: int = 2400
    periods: int = 8


@dataclass(frozen=True)
class ObservedWorld:
    world_id: str
    features: np.ndarray
    feature_names: tuple[str, ...]
    treatment: np.ndarray
    logged_propensity: np.ndarray
    outcome: np.ndarray
    cluster: np.ndarray
    period: np.ndarray
    observed: np.ndarray
    costs_identified: bool
    opportunity_signal: np.ndarray


@dataclass(frozen=True)
class OracleWorld:
    """Evaluation-only potential-outcome quantities, constructed separately."""

    individual_effect: np.ndarray
    baseline: np.ndarray
    actual_propensity: float


def generate_world(spec: WorldSpec) -> tuple[ObservedWorld, OracleWorld]:
    """Generate observables and oracle arrays from independent RNG streams."""

    feature_seed, baseline_seed, effect_seed, assignment_seed, noise_seed, signal_seed = (
        np.random.SeedSequence(spec.seed).spawn(6)
    )
    feature_rng = np.random.default_rng(feature_seed)
    n = spec.observations
    recency = feature_rng.exponential(45, n)
    frequency = feature_rng.poisson(3, n).astype(float)
    monetary = feature_rng.lognormal(3.4, 0.7, n)
    intent = feature_rng.beta(2, 4, n)
    loyalty = feature_rng.normal(0, 1, n)
    category = feature_rng.integers(0, 4, n).astype(float)
    period = np.arange(n) % spec.periods
    x = np.column_stack(
        [
            np.log1p(recency) / 5,
            np.log1p(frequency),
            np.log1p(monetary) / 5,
            intent,
            loyalty,
            category / 3,
            period / max(1, spec.periods - 1),
        ]
    )
    names = ("recency", "frequency", "monetary", "intent", "loyalty", "category", "period")

    baseline_rng = np.random.default_rng(baseline_seed)
    beta = baseline_rng.normal(0, 0.25, x.shape[1])
    baseline = 8.0 + x @ beta + 0.8 * np.log1p(monetary)

    effect_rng = np.random.default_rng(effect_seed)
    scale = effect_rng.uniform(1.15, 1.45)
    effect = _effect(spec.family, x, period, scale)
    actual_propensity = 0.04 if spec.family is WorldFamily.INSUFFICIENT_SUPPORT else 0.5
    assignment_rng = np.random.default_rng(assignment_seed)
    assigned = assignment_rng.random(n) < actual_propensity
    received = assigned.copy()
    if spec.family is WorldFamily.NONCOMPLIANCE:
        received &= assignment_rng.random(n) < 0.55

    noise_rng = np.random.default_rng(noise_seed)
    noise = noise_rng.normal(0, 2.2, n)
    if spec.family is WorldFamily.HEAVY_TAILED_CP:
        noise = noise_rng.standard_t(2.5, n) * 2.2
    if spec.family is WorldFamily.ZERO_INFLATED:
        noise = np.where(noise_rng.random(n) < 0.65, -baseline, noise)
    if spec.family is WorldFamily.COMMON_SHOCK:
        noise += np.where(period >= spec.periods // 2, -2.0, 0.0)
    realized_effect = effect * received
    if spec.family is WorldFamily.INTERFERENCE:
        household = np.arange(n) // 2
        peer = np.roll(received, 1) & (np.roll(household, 1) == household)
        realized_effect = realized_effect + 0.25 * effect * peer
    outcome = baseline + realized_effect + noise

    observed = np.ones(n, dtype=bool)
    costs_identified = True
    if spec.family is WorldFamily.ATTRITION:
        observed = assignment_rng.random(n) > np.where(assigned, 0.22, 0.06)
    if spec.family is WorldFamily.MISSING_DELAYED_RETURNS:
        observed = period < spec.periods - 2
        costs_identified = False
    logged = np.full(n, actual_propensity)
    if spec.family is WorldFamily.PROPENSITY_LOGGING_ERROR:
        logged[:] = 0.72

    # Opportunity is intentionally not constructed from effect or effect parameters.
    signal_rng = np.random.default_rng(signal_seed)
    opportunity = 0.5 * intent + 0.15 * x[:, 2] + signal_rng.normal(0, 0.7, n)
    clusters = np.arange(n) // 20
    return (
        ObservedWorld(
            spec.world_id,
            x,
            names,
            assigned,
            logged,
            outcome,
            clusters,
            period,
            observed,
            costs_identified,
            opportunity,
        ),
        OracleWorld(effect, baseline, actual_propensity),
    )


def _effect(
    family: WorldFamily,
    x: np.ndarray,
    period: np.ndarray,
    scale: float,
) -> np.ndarray:
    n = len(x)
    if family in {WorldFamily.NULL, WorldFamily.COMMON_SHOCK, WorldFamily.ATTRITION}:
        return np.zeros(n)
    if family is WorldFamily.GLOBALLY_HARMFUL:
        return np.full(n, -scale)
    if family in {
        WorldFamily.HOMOGENEOUS_POSITIVE,
        WorldFamily.HEAVY_TAILED_CP,
        WorldFamily.ZERO_INFLATED,
        WorldFamily.MISSING_DELAYED_RETURNS,
        WorldFamily.NONCOMPLIANCE,
        WorldFamily.PROPENSITY_LOGGING_ERROR,
        WorldFamily.INSUFFICIENT_SUPPORT,
    }:
        return np.full(n, scale)
    if family is WorldFamily.SPARSE_HETEROGENEITY:
        return np.where((x[:, 3] > 0.55) & (x[:, 4] > 0), 4.0 * scale, 0.0)
    if family is WorldFamily.QUALITATIVE_HETEROGENEITY:
        return np.where(x[:, 4] + x[:, 3] > 0.45, 2.0 * scale, -1.2 * scale)
    if family is WorldFamily.DELAYED_REVERSAL:
        return np.where(period < 4, -1.3 * scale, 2.0 * scale)
    if family in {WorldFamily.GRADUAL_DECAY, WorldFamily.NOVELTY_DECAY}:
        return scale * (1.8 - 1.6 * period / max(1, period.max()))
    if family is WorldFamily.CAUSAL_SHIFT:
        return np.where(period < 4, scale, -0.7 * scale)
    if family is WorldFamily.ACTION_FATIGUE:
        return scale * np.exp(-period / 3)
    if family is WorldFamily.INTERFERENCE:
        return np.full(n, scale)
    raise AssertionError(f"unhandled world family: {family}")

