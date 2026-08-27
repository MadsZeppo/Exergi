"""Outer-holdout economic policy evaluation and identifiability taxonomy for V7.1."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np
from scipy.stats import norm
from sklearn.ensemble import RandomForestRegressor

from decision_engine.core.authority import ClaimAuthority
from decision_engine.decision.action_viability import (
    ActionViabilityConfig,
    ActionViabilityEngine,
    RandomizedEconomicEvidence,
    ViabilityStatus,
)

from .models import EffectModel
from .world import V71ObservedWorld, V71WorldFamily, V71WorldSpec, generate_v71_world

MATERIALITY = 0.10


@dataclass(frozen=True)
class V71WorldEvaluation:
    world_id: str
    family: str
    model: str
    oracle_taxonomy: str
    performance_classification: str
    decision: str
    selected_policy: str
    viability: str
    support_valid: bool
    unsupported_act: bool
    personalization_promoted: bool
    reason_codes: tuple[str, ...]
    heldout_policy_value: float
    heldout_policy_lower: float
    heldout_increment_over_static: float
    heldout_increment_lower: float
    best_static_value: float
    rfm_value: float
    full_oracle_increment: float
    observable_oracle_increment: float
    segment_oracle_increment: float
    oracle_policy_increment: float
    observable_oracle_capture: float
    calibration_rmse: float
    rate: float
    rate_lower: float
    shuffle_p_value: float
    fold_positive_fraction: float
    sample_size: int
    effective_sample_size: float
    propensity_min: float
    propensity_max: float
    treatment_cost: float
    switching_cost: float
    runtime_error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _outcome_nuisance(
    observed: V71ObservedWorld,
    train: np.ndarray,
    target: np.ndarray,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    a = observed.assignment
    model0 = RandomForestRegressor(
        n_estimators=60,
        max_depth=7,
        min_samples_leaf=30,
        random_state=seed + 1,
        n_jobs=1,
    ).fit(observed.features[train][~a[train]], observed.contribution_profit[train][~a[train]])
    model1 = RandomForestRegressor(
        n_estimators=60,
        max_depth=7,
        min_samples_leaf=30,
        random_state=seed + 2,
        n_jobs=1,
    ).fit(observed.features[train][a[train]], observed.contribution_profit[train][a[train]])
    return model0.predict(observed.features[target]), model1.predict(observed.features[target])


def _dr_scores(
    observed: V71ObservedWorld,
    train: np.ndarray,
    target: np.ndarray,
    seed: int,
) -> np.ndarray:
    m0, m1 = _outcome_nuisance(observed, train, target, seed)
    a = observed.assignment[target]
    y = observed.contribution_profit[target]
    p = np.clip(observed.logged_propensity[target], 0.05, 0.95)
    return np.asarray(m1 - m0 + a * (y - m1) / p - (~a) * (y - m0) / (1 - p))


def _cluster_lower(values: np.ndarray, clusters: np.ndarray, alpha: float = 0.05) -> float:
    estimate = float(np.mean(values))
    labels, inverse = np.unique(clusters, return_inverse=True)
    if len(labels) < 2:
        return -float("inf")
    sums = np.bincount(inverse, weights=values - estimate)
    se = float(np.sqrt(len(labels) / (len(labels) - 1) * np.sum(sums**2) / len(values) ** 2))
    return estimate - float(norm.ppf(1 - alpha)) * se


def _shuffle_p(prediction: np.ndarray, scores: np.ndarray, seed: int) -> float:
    observed = float(np.corrcoef(prediction, scores)[0, 1])
    if not np.isfinite(observed):
        return 1.0
    rng = np.random.default_rng(seed)
    null = [float(np.corrcoef(rng.permutation(prediction), scores)[0, 1]) for _ in range(99)]
    return float((1 + sum(value >= observed for value in null)) / 100)


def _observable_oracle(
    spec: V71WorldSpec,
    target_features: np.ndarray,
) -> np.ndarray:
    return np.asarray(_observable_oracle_model(spec).predict(target_features), dtype=float)


@lru_cache(maxsize=128)
def _observable_oracle_model(spec: V71WorldSpec) -> RandomForestRegressor:
    evaluator_spec = V71WorldSpec(
        world_id=f"evaluator-{spec.world_id}",
        merchant_id=f"evaluator-{spec.merchant_id}",
        action_family=spec.action_family,
        family=spec.family,
        seed=spec.seed + 7_000_019,
        observations=20_000,
        periods=spec.periods,
        treatment_cost=spec.treatment_cost,
        switching_cost=spec.switching_cost,
        subgroup_prevalence=spec.subgroup_prevalence,
        maturity_delay=spec.maturity_delay,
        change_period=spec.change_period,
        noise_family=spec.noise_family,
    )
    evaluator_observed, evaluator_oracle = generate_v71_world(evaluator_spec)
    model = RandomForestRegressor(
        n_estimators=80,
        max_depth=9,
        min_samples_leaf=40,
        random_state=spec.seed + 700,
        n_jobs=1,
    ).fit(evaluator_observed.features, evaluator_oracle.individual_net_effect)
    return model


def _segment_masks(x: np.ndarray) -> tuple[np.ndarray, ...]:
    return (
        np.ones(len(x), dtype=bool),
        (x[:, 0] > 0.7) & (x[:, 3] > 0.3),
        x[:, 3] > 0.55,
        x[:, 4] > 0,
        (x[:, 3] + x[:, 4]) > 0.45,
        (x[:, 3] > 0.45) & (x[:, 4] > 0),
    )


def _oracle_taxonomy(
    effect: np.ndarray,
    observable_prediction: np.ndarray,
    segments: tuple[np.ndarray, ...],
    *,
    support_valid: bool,
) -> tuple[str, float, float, float, float]:
    static = max(0.0, float(np.mean(effect)))
    full = float(np.mean(effect * (effect > 0))) - static
    observable = float(np.mean(effect * (observable_prediction > 0))) - static
    segment = max(0.0, *(float(np.mean(effect * mask)) for mask in segments)) - static
    if not support_valid:
        taxonomy = "UNSUPPORTED_PERSONALIZATION"
    elif observable > MATERIALITY:
        taxonomy = "MATERIAL_OBSERVABLE_PERSONALIZATION"
    elif full > MATERIALITY:
        taxonomy = "MATERIAL_UNOBSERVABLE_PERSONALIZATION"
    else:
        taxonomy = "NONMATERIAL_PERSONALIZATION"
    return taxonomy, static, full, observable, segment


def evaluate_candidate(spec: V71WorldSpec, model: EffectModel) -> V71WorldEvaluation:
    observed, oracle = generate_v71_world(spec)
    n = len(observed.contribution_profit)
    base_end, gate_end = int(0.40 * n), int(0.70 * n)
    base = np.arange(base_end)
    gate = np.arange(base_end, gate_end)
    test = np.arange(gate_end, n)
    base = base[observed.observed[base]]
    gate = gate[observed.observed[gate]]
    test = test[observed.observed[test]]

    assigned_rate = float(np.mean(observed.assignment[base]))
    logged_rate = float(np.mean(observed.logged_propensity[base]))
    balance_se = np.sqrt(max(logged_rate * (1 - logged_rate), 1e-9) / len(base))
    propensity_valid = abs(assigned_rate - logged_rate) <= 5 * balance_se
    attrition_gap = abs(
        float(np.mean(observed.observed[observed.assignment]))
        - float(np.mean(observed.observed[~observed.assignment]))
    )
    support_valid = bool(
        propensity_valid
        and attrition_gap <= 0.10
        and observed.costs_identified
        and np.all(observed.logged_propensity >= 0.05)
        and np.all(observed.logged_propensity <= 0.95)
    )
    viability_status = ViabilityStatus.INSUFFICIENT
    viability = None
    if support_valid:
        viability = ActionViabilityEngine(
            ActionViabilityConfig(
                minimum_effect=MATERIALITY,
                minimum_observations=400,
                minimum_arm_observations=150,
                minimum_clusters=50,
                seed=spec.seed,
            )
        ).evaluate(
            RandomizedEconomicEvidence(
                observed.contribution_profit[base],
                observed.assignment[base],
                observed.logged_propensity[base],
                observed.features[base],
                observed.cluster[base],
                observed.feature_names,
                ClaimAuthority.SYNTHETIC_ECONOMIC,
                "SIMULATED_RANDOMIZED",
                True,
            )
        )
        viability_status = viability.status

    model.fit(
        observed.features[base],
        observed.assignment[base],
        observed.contribution_profit[base],
        observed.logged_propensity[base],
    )
    gate_prediction = np.asarray(model.effect(observed.features[gate]), dtype=float)
    gate_scores = _dr_scores(observed, base, gate, spec.seed + 100)
    static_treat = viability_status is ViabilityStatus.VIABLE
    gate_static = np.full(len(gate), static_treat)
    gate_personal = gate_prediction > 0
    gate_difference = gate_scores * (gate_personal.astype(float) - gate_static.astype(float))
    increment_lower = _cluster_lower(gate_difference, observed.cluster[gate], alpha=0.025)
    rate = float(np.corrcoef(gate_prediction, gate_scores)[0, 1])
    rate = rate if np.isfinite(rate) else 0.0
    rate_se = float(np.sqrt(max((1 - rate**2) / max(1, len(gate) - 2), 0.0)))
    rate_lower = rate - float(norm.ppf(0.975)) * rate_se
    shuffle = _shuffle_p(gate_prediction, gate_scores, spec.seed + 200)
    fold_values = [float(np.mean(chunk)) for chunk in np.array_split(gate_difference, 4)]
    fold_positive = float(np.mean(np.asarray(fold_values) > 0))
    reasons: list[str] = []
    checks = {
        "support": support_valid,
        "increment_lower": increment_lower > 0,
        "rate_lower": rate_lower > 0,
        "shuffle": shuffle <= 0.025,
        "fold_stability": fold_positive >= 0.75,
        "ess": len(gate) >= 200,
    }
    promoted = all(checks.values())
    reasons.extend(name.upper() for name, passed in checks.items() if not passed)
    if promoted:
        reasons.append("PERSONALIZATION_INCREMENT_SUPPORTED")

    test_prediction = np.asarray(model.effect(observed.features[test]), dtype=float)
    test_scores = _dr_scores(observed, base, test, spec.seed + 300)
    if not support_valid:
        selected = np.zeros(len(test), dtype=bool)
        selected_policy = "BAU"
        decision = "BAU_OR_TEST"
        reasons.append("FAIL_CLOSED_SUPPORT")
    elif viability_status is ViabilityStatus.HARMFUL:
        selected = np.zeros(len(test), dtype=bool)
        selected_policy = "AVOID"
        decision = "AVOID"
    elif promoted:
        selected = test_prediction > 0
        selected_policy = "PERSONALIZED"
        decision = "ACT"
    elif static_treat:
        selected = np.ones(len(test), dtype=bool)
        selected_policy = "TREAT_ALL"
        decision = "ACT"
    else:
        selected = np.zeros(len(test), dtype=bool)
        selected_policy = "BAU"
        decision = "BAU_OR_TEST"

    static_policy = np.full(len(test), static_treat)
    policy_values = test_scores * selected
    static_values = test_scores * static_policy
    difference = policy_values - static_values
    policy_value = float(np.mean(policy_values))
    policy_lower = _cluster_lower(policy_values, observed.cluster[test])
    heldout_increment = float(np.mean(difference))
    heldout_increment_lower = _cluster_lower(difference, observed.cluster[test])
    rfm = _segment_masks(observed.features[test])[1]
    rfm_value = float(np.mean(test_scores * rfm))

    effect = oracle.individual_net_effect[test]
    observable_prediction = _observable_oracle(spec, observed.features[test])
    taxonomy, oracle_static, full_increment, observable_increment, segment_increment = (
        _oracle_taxonomy(
            effect,
            observable_prediction,
            _segment_masks(observed.features[test]),
            support_valid=support_valid,
        )
    )
    oracle_selected = float(np.mean(effect * selected))
    oracle_policy_increment = oracle_selected - oracle_static
    performance = taxonomy
    if taxonomy == "MATERIAL_OBSERVABLE_PERSONALIZATION" and (
        not promoted or heldout_increment_lower <= 0
    ):
        performance = "ESTIMATION_OR_POLICY_FAILURE"
    denominator = max(observable_increment, 1e-12)
    capture = oracle_policy_increment / denominator if observable_increment > 0 else 0.0
    calibration = float(np.sqrt(np.mean((test_prediction - test_scores) ** 2)))
    p = observed.logged_propensity[test]
    weights = np.where(observed.assignment[test], 1 / p, 1 / (1 - p))
    ess = float(np.sum(weights) ** 2 / np.sum(weights**2))
    return V71WorldEvaluation(
        spec.world_id,
        spec.family.value,
        model.name,
        taxonomy,
        performance,
        decision,
        selected_policy,
        viability_status.value,
        support_valid,
        bool(np.any(selected) and not support_valid),
        promoted,
        tuple(reasons),
        policy_value,
        policy_lower,
        heldout_increment,
        heldout_increment_lower,
        oracle_static,
        rfm_value,
        full_increment,
        observable_increment,
        segment_increment,
        oracle_policy_increment,
        capture,
        calibration,
        rate,
        rate_lower,
        shuffle,
        fold_positive,
        len(test),
        ess,
        float(np.min(p)),
        float(np.max(p)),
        spec.treatment_cost,
        spec.switching_cost,
    )


def family_group(family: str) -> str:
    mapping = {
        V71WorldFamily.HOMOGENEOUS_POSITIVE.value: "HOMOGENEOUS_POSITIVE",
        V71WorldFamily.GLOBALLY_HARMFUL.value: "NULL_HARMFUL",
        V71WorldFamily.NULL.value: "NULL_HARMFUL",
    }
    return mapping.get(family, "OTHER")
