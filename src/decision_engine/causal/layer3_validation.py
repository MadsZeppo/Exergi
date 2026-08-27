"""Layer 3 ground-truth generator and cross-fitted binary-treatment AIPW."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class SyntheticUpliftData:
    customer_id: np.ndarray
    features: np.ndarray
    segment: np.ndarray
    treatment: np.ndarray
    outcome: np.ndarray
    true_effect: np.ndarray
    true_propensity: np.ndarray
    scenario: str
    seed: int


@dataclass(frozen=True)
class AIPWResult:
    ate: float
    lower: float
    upper: float
    standard_error: float
    naive_ate: float
    segment_effects: dict[int, float]
    individual_effect: np.ndarray
    pseudo_outcome: np.ndarray
    propensity: np.ndarray
    fraction_clipped: float
    overlap_fraction: float
    treated_ess: float
    control_ess: float


def _sigmoid(value: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(value, -30, 30)))


def generate_synthetic_uplift(
    *, seed: int, n_customers: int = 20_000, scenario: str = "randomized"
) -> SyntheticUpliftData:
    if scenario not in {"randomized", "confounded", "placebo"}:
        raise ValueError(f"unsupported scenario: {scenario}")
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n_customers)
    x2 = rng.normal(size=n_customers)
    segment = rng.integers(0, 3, size=n_customers)
    segment_one = (segment == 1).astype(float)
    segment_two = (segment == 2).astype(float)
    features = np.column_stack([x1, x2, x1 * x2, x1**2, x2**2, segment_one, segment_two])
    baseline = _sigmoid(-1.8 + 0.75 * x1 - 0.45 * x2 + 0.25 * x1 * x2 + 0.25 * segment_one)
    true_effect = np.array([0.02, 0.05, 0.08], dtype=float)[segment]
    if scenario == "placebo":
        true_effect = np.zeros(n_customers, dtype=float)
    if scenario == "confounded":
        propensity = _sigmoid(-0.25 + 1.1 * x1 - 0.5 * x2 + 0.45 * segment_two)
    else:
        propensity = np.full(n_customers, 0.5)
    treatment = rng.binomial(1, propensity).astype(int)
    probability = np.clip(baseline + treatment * true_effect, 0.01, 0.99)
    outcome = rng.binomial(1, probability).astype(int)
    return SyntheticUpliftData(
        customer_id=np.array([f"synthetic-{seed}-{index}" for index in range(n_customers)]),
        features=features,
        segment=segment,
        treatment=treatment,
        outcome=outcome,
        true_effect=true_effect,
        true_propensity=propensity,
        scenario=scenario,
        seed=seed,
    )


def _ess(weights: np.ndarray) -> float:
    return float(weights.sum() ** 2 / max(float(np.square(weights).sum()), 1e-12))


def cross_fitted_aipw(
    features: np.ndarray,
    treatment: np.ndarray,
    outcome: np.ndarray,
    segment: np.ndarray,
    *,
    seed: int,
    folds: int = 5,
    propensity_floor: float = 0.02,
) -> AIPWResult:
    x = np.asarray(features, dtype=float)
    t = np.asarray(treatment, dtype=int)
    y = np.asarray(outcome, dtype=int)
    if len(x) != len(t) or len(t) != len(y):
        raise ValueError("features, treatment, and outcome lengths differ")
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    propensity = np.zeros(len(y))
    m0 = np.zeros(len(y))
    m1 = np.zeros(len(y))
    for train, validation in splitter.split(x, t):
        propensity_model = make_pipeline(
            StandardScaler(), LogisticRegression(C=1, max_iter=1_000, random_state=seed)
        ).fit(x[train], t[train])
        propensity[validation] = propensity_model.predict_proba(x[validation])[:, 1]
        for arm, target in ((0, m0), (1, m1)):
            selected = train[t[train] == arm]
            outcome_model = make_pipeline(
                StandardScaler(), LogisticRegression(C=1, max_iter=1_000, random_state=seed)
            ).fit(x[selected], y[selected])
            target[validation] = outcome_model.predict_proba(x[validation])[:, 1]
    clipped = np.clip(propensity, propensity_floor, 1 - propensity_floor)
    pseudo = m1 - m0 + t * (y - m1) / clipped - (1 - t) * (y - m0) / (1 - clipped)
    ate = float(pseudo.mean())
    standard_error = float(pseudo.std(ddof=1) / np.sqrt(len(pseudo)))
    segment_effects = {
        int(value): float(pseudo[segment == value].mean()) for value in np.unique(segment)
    }
    individual_effect = np.array([segment_effects[int(value)] for value in segment])
    treated_weights = t / clipped
    control_weights = (1 - t) / (1 - clipped)
    return AIPWResult(
        ate=ate,
        lower=ate - 1.96 * standard_error,
        upper=ate + 1.96 * standard_error,
        standard_error=standard_error,
        naive_ate=float(y[t == 1].mean() - y[t == 0].mean()),
        segment_effects=segment_effects,
        individual_effect=individual_effect,
        pseudo_outcome=pseudo,
        propensity=propensity,
        fraction_clipped=float(np.mean(propensity != clipped)),
        overlap_fraction=float(np.mean((propensity >= 0.05) & (propensity <= 0.95))),
        treated_ess=_ess(treated_weights[t == 1]),
        control_ess=_ess(control_weights[t == 0]),
    )
