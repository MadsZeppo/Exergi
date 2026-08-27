"""Honest outer-holdout policy evaluation for V7 synthetic packs."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.stats import norm
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge

from decision_engine.core.authority import ClaimAuthority
from decision_engine.decision.action_viability import (
    ActionViabilityConfig,
    ActionViabilityEngine,
    RandomizedEconomicEvidence,
    ViabilityStatus,
)
from decision_engine.decision.heterogeneity import HeterogeneityEvidence, HeterogeneityGate

from .world import WorldFamily, WorldSpec, generate_world


@dataclass(frozen=True)
class WorldResult:
    world_id: str
    family: str
    model: str
    decision: str
    selected_policy: str
    viability: str
    estimate: float
    lower: float | None
    policy_value: float
    policy_lower: float
    treat_all_value: float
    rfm_value: float
    oracle_value: float
    value_capture: float
    personalized_minus_static: float
    unsupported_act: bool
    personalization_supported: bool
    propensity_valid: bool
    attrition_valid: bool
    costs_identified: bool
    claim_authority: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class UpliftModel:
    def __init__(self, name: str, seed: int) -> None:
        self.name = name
        self.seed = seed
        self._m0: Ridge | RandomForestRegressor | None = None
        self._m1: Ridge | RandomForestRegressor | None = None

    def fit(self, x: np.ndarray, a: np.ndarray, y: np.ndarray) -> UpliftModel:
        if self.name == "ridge_t_learner":
            self._m0 = Ridge(alpha=2.0).fit(x[~a], y[~a])
            self._m1 = Ridge(alpha=2.0).fit(x[a], y[a])
        elif self.name == "forest_t_learner":
            parameters = {
                "n_estimators": 120,
                "min_samples_leaf": 35,
                "max_depth": 5,
                "random_state": self.seed,
                "n_jobs": 1,
            }
            self._m0 = RandomForestRegressor(**parameters).fit(x[~a], y[~a])
            self._m1 = RandomForestRegressor(**parameters).fit(x[a], y[a])
        else:
            raise ValueError(f"unknown uplift model: {self.name}")
        return self

    def potential_predictions(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self._m0 is None or self._m1 is None:
            raise RuntimeError("model is not fitted")
        return self._m0.predict(x), self._m1.predict(x)

    def effect(self, x: np.ndarray) -> np.ndarray:
        m0, m1 = self.potential_predictions(x)
        return np.asarray(m1 - m0, dtype=float)


def _dr_scores(
    model: UpliftModel,
    x: np.ndarray,
    a: np.ndarray,
    y: np.ndarray,
    p: np.ndarray,
) -> np.ndarray:
    m0, m1 = model.potential_predictions(x)
    return m1 - m0 + a * (y - m1) / p - (~a) * (y - m0) / (1 - p)


def _value(scores: np.ndarray, policy: np.ndarray, clusters: np.ndarray) -> tuple[float, float]:
    values = np.asarray(scores) * np.asarray(policy, dtype=bool)
    estimate = float(np.mean(values))
    labels, inverse = np.unique(clusters, return_inverse=True)
    if len(labels) < 2:
        return estimate, -float("inf")
    sums = np.bincount(inverse, weights=values - estimate)
    se = float(np.sqrt(len(labels) / (len(labels) - 1) * np.sum(sums**2) / len(values) ** 2))
    return estimate, estimate - float(norm.ppf(0.95)) * se


def _shuffle_p_value(
    predicted: np.ndarray,
    scores: np.ndarray,
    *,
    seed: int,
    repetitions: int = 99,
) -> float:
    observed = float(np.corrcoef(predicted, scores)[0, 1])
    if not np.isfinite(observed):
        return 1.0
    rng = np.random.default_rng(seed)
    null = [
        float(np.corrcoef(rng.permutation(predicted), scores)[0, 1])
        for _ in range(repetitions)
    ]
    return (1 + sum(value >= observed for value in null)) / (repetitions + 1)


def evaluate_world(spec: WorldSpec, model_name: str) -> WorldResult:
    observed, oracle = generate_world(spec)
    n = len(observed.outcome)
    base_end, gate_end = int(0.4 * n), int(0.65 * n)
    base = np.arange(base_end)
    gate = np.arange(base_end, gate_end)
    test = np.arange(gate_end, n)
    attrition_gap = abs(
        float(np.mean(observed.observed[observed.treatment]))
        - float(np.mean(observed.observed[~observed.treatment]))
    )
    attrition_valid = attrition_gap <= 0.10
    assigned_rate = float(np.mean(observed.treatment[base]))
    logged_rate = float(np.mean(observed.logged_propensity[base]))
    randomization_se = np.sqrt(max(logged_rate * (1 - logged_rate), 1e-9) / len(base))
    propensity_valid = abs(assigned_rate - logged_rate) <= 5 * randomization_se
    support_valid = bool(
        np.all(observed.logged_propensity >= 0.05)
        and np.all(observed.logged_propensity <= 0.95)
        and propensity_valid
        and attrition_valid
    )
    use = base[observed.observed[base]]
    viability = None
    if support_valid:
        viability = ActionViabilityEngine(
            ActionViabilityConfig(
                minimum_effect=0.10,
                minimum_clusters=12,
                minimum_observations=300,
                minimum_arm_observations=100,
                seed=spec.seed,
            )
        ).evaluate(
            RandomizedEconomicEvidence(
                observed.outcome[use],
                observed.treatment[use],
                observed.logged_propensity[use],
                observed.features[use],
                observed.cluster[use],
                observed.feature_names,
                ClaimAuthority.SYNTHETIC_ECONOMIC,
                "SIMULATED_RANDOMIZED",
                observed.costs_identified,
            )
        )
    viability_status = viability.status if viability is not None else ViabilityStatus.INSUFFICIENT

    model = UpliftModel(model_name, spec.seed).fit(
        observed.features[use], observed.treatment[use], observed.outcome[use]
    )
    gate_use = gate[observed.observed[gate]]
    test_use = test[observed.observed[test]]
    gate_scores = _dr_scores(
        model,
        observed.features[gate_use],
        observed.treatment[gate_use],
        observed.outcome[gate_use],
        observed.logged_propensity[gate_use],
    )
    gate_prediction = model.effect(observed.features[gate_use])
    static_treat = viability_status is ViabilityStatus.VIABLE
    personalized_gate = gate_prediction > 0
    static_gate = np.full(len(gate_use), static_treat)
    difference_scores = gate_scores * (personalized_gate.astype(float) - static_gate.astype(float))
    fold_effects = tuple(
        float(np.mean(chunk)) for chunk in np.array_split(difference_scores, 5) if len(chunk)
    )
    rate = float(np.corrcoef(gate_prediction, gate_scores)[0, 1])
    rate = rate if np.isfinite(rate) else 0.0
    rate_se = float(np.sqrt(max((1 - rate**2) / max(1, len(gate_use) - 2), 0.0)))
    heterogeneity = HeterogeneityGate(minimum_ess=200).evaluate(
        HeterogeneityEvidence(
            out_of_fold=True,
            rate_or_autoc=rate,
            rate_standard_error=rate_se,
            shuffle_p_value=_shuffle_p_value(
                gate_prediction, gate_scores, seed=spec.seed + 31
            ),
            fold_effects=fold_effects,
            personalized_minus_static_scores=difference_scores,
            clusters=observed.cluster[gate_use],
            effective_sample_size=float(len(gate_use)),
            treatment_regions_supported=support_valid,
            candidate_tests=2,
        ),
        best_static_policy="TREAT_ALL" if static_treat else "BAU",
    )

    test_scores = _dr_scores(
        model,
        observed.features[test_use],
        observed.treatment[test_use],
        observed.outcome[test_use],
        observed.logged_propensity[test_use],
    )
    prediction = model.effect(observed.features[test_use])
    rfm_policy = (observed.features[test_use, 0] > 0.7) & (observed.features[test_use, 3] > 0.3)
    if viability_status in {ViabilityStatus.INSUFFICIENT, ViabilityStatus.HARMFUL}:
        selected = np.zeros(len(test_use), dtype=bool)
        policy_name = "BAU" if viability_status is ViabilityStatus.INSUFFICIENT else "AVOID"
    elif heterogeneity.personalization_supported:
        selected = prediction > 0
        policy_name = "INDIVIDUALIZED"
    elif viability_status is ViabilityStatus.VIABLE:
        selected = np.ones(len(test_use), dtype=bool)
        policy_name = "TREAT_ALL"
    else:
        selected = np.zeros(len(test_use), dtype=bool)
        policy_name = "BAU"
    policy_value, policy_lower = _value(test_scores, selected, observed.cluster[test_use])
    treat_all_value, _ = _value(
        test_scores, np.ones(len(test_use), dtype=bool), observed.cluster[test_use]
    )
    rfm_value, _ = _value(test_scores, rfm_policy, observed.cluster[test_use])
    effect = oracle.individual_effect[test_use]
    oracle_policy = effect > 0
    oracle_value = float(np.mean(effect * oracle_policy))
    selected_oracle_value = float(np.mean(effect * selected))
    best_static = max(0.0, float(np.mean(effect)))
    return WorldResult(
        observed.world_id,
        spec.family.value,
        model_name,
        "ACT" if np.any(selected) else "AVOID" if policy_name == "AVOID" else "BAU_OR_TEST",
        policy_name,
        viability_status.value,
        viability.estimate if viability is not None else 0.0,
        viability.lower if viability is not None and np.isfinite(viability.lower) else None,
        policy_value,
        policy_lower,
        treat_all_value,
        rfm_value,
        oracle_value,
        selected_oracle_value / oracle_value if oracle_value > 1e-12 else 1.0,
        selected_oracle_value - best_static,
        bool(np.any(selected) and not support_valid),
        heterogeneity.personalization_supported,
        bool(propensity_valid),
        bool(attrition_valid),
        observed.costs_identified,
        ClaimAuthority.SYNTHETIC_ECONOMIC.value,
    )


def is_positive_family(family: str) -> bool:
    return family in {
        WorldFamily.HOMOGENEOUS_POSITIVE.value,
        WorldFamily.SPARSE_HETEROGENEITY.value,
        WorldFamily.QUALITATIVE_HETEROGENEITY.value,
        WorldFamily.HEAVY_TAILED_CP.value,
        WorldFamily.ZERO_INFLATED.value,
        WorldFamily.NONCOMPLIANCE.value,
        WorldFamily.INTERFERENCE.value,
        WorldFamily.ACTION_FATIGUE.value,
        WorldFamily.NOVELTY_DECAY.value,
    }
