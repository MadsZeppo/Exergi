"""Independent commerce DGP with evaluator-only potential-outcome truth."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray
from scipy.special import expit, logit

from .contracts import GateInput


class WorldFamily(StrEnum):
    NULL = "null"
    HARMFUL = "harmful"
    MATERIAL_POSITIVE = "material_positive"
    WEAK_POSITIVE = "weak_positive"
    QUALITATIVE_HETEROGENEITY = "qualitative_heterogeneity"
    SPARSE_RESPONDER = "sparse_responder"
    OUTLIER_DRIVEN = "outlier_driven"
    NEGATIVE_MARGIN = "negative_margin"
    EFFECT_REVERSAL = "effect_reversal"
    INTEGRITY_FAILURE = "integrity_failure"


@dataclass(frozen=True)
class WorldTruth:
    """Evaluator-only state; never accepted by a gate function."""

    family: WorldFamily
    true_net_value: float
    supported_action: bool
    budget_valid: bool
    early_release_safe: bool
    materially_positive: bool
    harmful: bool
    null: bool


@dataclass(frozen=True)
class SyntheticWorld:
    gate_input: GateInput
    evaluator_truth: WorldTruth
    generator_metadata: dict[str, float | int | str | bool]


def _positive_amount(
    rng: np.random.Generator, n: int, shape: str, mean: float
) -> NDArray[np.float64]:
    if shape == "lognormal":
        sigma = rng.uniform(0.8, 1.6)
        return rng.lognormal(np.log(mean) - sigma**2 / 2, sigma, n)
    if shape == "pareto":
        alpha = rng.uniform(2.2, 4.0)
        scale = mean * (alpha - 1) / alpha
        return scale * (rng.pareto(alpha, n) + 1)
    count = rng.poisson(rng.uniform(0.8, 1.8), n) + 1
    scale = mean / float(np.mean(count))
    return rng.gamma(shape=count, scale=scale)


def generate_world(family: WorldFamily, seed: int, world_index: int) -> SyntheticWorld:
    """Generate observed data and mechanically separate finite-population truth."""

    rng = np.random.default_rng(np.random.SeedSequence([seed, world_index]))
    n = int(rng.choice(np.asarray([600, 1_200, 2_400])))
    features = rng.normal(size=(n, 3))
    base_purchase = rng.uniform(0.005, 0.05)
    p0 = expit(logit(base_purchase) + 0.35 * features[:, 0] - 0.15 * features[:, 1])
    shape = str(rng.choice(np.asarray(["lognormal", "pareto", "compound"])))
    amount_mean = rng.uniform(25.0, 75.0)
    amount0 = _positive_amount(rng, n, shape, amount_mean)
    amount1 = amount0 * rng.lognormal(0.0, 0.08, n)
    purchase_draw = rng.random(n)
    p1 = p0.copy()
    action_cost = float(rng.uniform(0.02, 0.12))
    support_valid = True
    assignment_integrity = True
    contamination = False
    budget = float(rng.uniform(0.15, 0.50))
    mature = np.ones(n, dtype=bool)
    actual_propensity = float(rng.uniform(0.35, 0.65))
    logged_propensity = actual_propensity

    if family is WorldFamily.NULL:
        action_cost = 0.0
    elif family is WorldFamily.HARMFUL:
        p1 = np.clip(p0 - rng.uniform(0.004, 0.018), 0.0, 1.0)
    elif family is WorldFamily.MATERIAL_POSITIVE:
        p1 = np.clip(p0 + rng.uniform(0.012, 0.030), 0.0, 1.0)
    elif family is WorldFamily.WEAK_POSITIVE:
        p1 = np.clip(p0 + rng.uniform(0.0015, 0.005), 0.0, 1.0)
    elif family is WorldFamily.QUALITATIVE_HETEROGENEITY:
        shift = np.where(features[:, 0] > 0, rng.uniform(0.018, 0.035), -rng.uniform(0.006, 0.015))
        p1 = np.clip(p0 + shift, 0.0, 1.0)
    elif family is WorldFamily.SPARSE_RESPONDER:
        responder = features[:, 0] > np.quantile(features[:, 0], 0.90)
        p1 = np.clip(p0 + np.where(responder, rng.uniform(0.07, 0.12), -0.001), 0.0, 1.0)
    elif family is WorldFamily.OUTLIER_DRIVEN:
        p1 = np.clip(p0 + rng.uniform(0.0008, 0.002), 0.0, 1.0)
        jackpot = (rng.random(n) < 0.0015) & (purchase_draw < p1) & (purchase_draw >= p0)
        amount1[jackpot] *= rng.uniform(15.0, 40.0)
    elif family is WorldFamily.NEGATIVE_MARGIN:
        p1 = np.clip(p0 + rng.uniform(0.008, 0.020), 0.0, 1.0)
        amount1 = -np.abs(amount1) * rng.uniform(0.10, 0.35)
    elif family is WorldFamily.EFFECT_REVERSAL:
        common_shock = np.where(features[:, 2] > 0, 1.0, -1.0)
        p1 = np.clip(p0 + common_shock * rng.uniform(0.012, 0.028), 0.0, 1.0)
    elif family is WorldFamily.INTEGRITY_FAILURE:
        variant = world_index % 6
        if variant == 0:
            mature[(rng.random(n) < 0.12) & (rng.random(n) < expit(features[:, 0]))] = False
        elif variant == 1:
            logged_propensity = float(np.clip(actual_propensity + 0.20, 0.01, 0.99))
            assignment_integrity = False
        elif variant == 2:
            actual_propensity = 0.97
            logged_propensity = actual_propensity
            support_valid = False
        elif variant == 3:
            support_valid = False
        elif variant == 4:
            contamination = True
            assignment_integrity = False
        else:
            mature[rng.random(n) < 0.10] = False
        p1 = np.clip(p0 + rng.uniform(0.015, 0.030), 0.0, 1.0)

    y0 = (purchase_draw < p0) * amount0
    y1 = (purchase_draw < p1) * amount1
    if family is WorldFamily.NULL:
        y1 = y0.copy()
    treatment = (rng.random(n) < actual_propensity).astype(np.int64)
    observed = np.where(treatment == 1, y1, y0).astype(float)
    observed[~mature] = np.nan
    unit_id = np.asarray([f"w{world_index}-u{index}" for index in range(n)])
    split_key = rng.integers(0, np.iinfo(np.uint64).max, size=n, dtype=np.uint64)
    propensity = np.full(n, logged_propensity, dtype=float)

    true_net = float(np.mean(y1 - y0) - action_cost)
    supported = bool(support_valid and assignment_integrity and not contamination)
    truth = WorldTruth(
        family=family,
        true_net_value=true_net,
        supported_action=supported,
        budget_valid=action_cost <= budget,
        early_release_safe=float(mature.mean()) >= 0.95,
        materially_positive=true_net >= 0.20,
        harmful=true_net < -0.02,
        null=abs(true_net) <= 0.02,
    )
    gate_input = GateInput(
        outcome=observed,
        treatment=treatment,
        features=features,
        unit_id=unit_id,
        split_key=split_key,
        logged_propensity=propensity,
        mature=mature,
        action_cost=action_cost,
        per_unit_budget=budget,
        assignment_integrity_valid=assignment_integrity,
        support_valid=support_valid,
        assignment_contamination=contamination,
    )
    return SyntheticWorld(
        gate_input=gate_input,
        evaluator_truth=truth,
        generator_metadata={
            "n": n,
            "base_purchase_probability": base_purchase,
            "positive_amount_shape": shape,
            "positive_amount_mean": amount_mean,
            "actual_propensity": actual_propensity,
            "logged_propensity": logged_propensity,
            "action_cost": action_cost,
        },
    )
