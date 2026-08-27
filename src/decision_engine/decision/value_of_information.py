"""Transparent Monte-Carlo expected value of sample information."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NormalActionEvidence:
    mean: float
    standard_error: float


@dataclass(frozen=True)
class EVSIResult:
    evsi_per_future_decision: float
    population_evsi: float
    experiment_cost: float
    expected_experiment_regret: float
    enbs: float
    conservative_enbs: float
    test_allowed: bool


def monte_carlo_evsi(
    evidence: tuple[NormalActionEvidence, ...],
    *,
    future_population: int,
    relevance: float,
    sample_size: int,
    outcome_standard_deviation: float,
    experiment_cost: float,
    draws: int = 4000,
    seed: int = 91,
    conservative_z: float = 1.64,
) -> EVSIResult:
    """Normal-normal EVSI with Control fixed at incremental utility zero."""
    if not evidence or future_population < 0 or not 0 <= relevance <= 1:
        raise ValueError("invalid EVSI population/evidence")
    if sample_size <= 0 or outcome_standard_deviation <= 0 or experiment_cost < 0:
        raise ValueError("invalid experiment design")
    rng = np.random.default_rng(seed)
    means = np.array([0.0, *(item.mean for item in evidence)])
    ses = np.array([0.0, *(item.standard_error for item in evidence)])
    current = float(np.max(means))
    improvements = np.empty(draws)
    regrets = np.empty(draws)
    observation_se = outcome_standard_deviation / np.sqrt(sample_size)
    for draw in range(draws):
        truth = rng.normal(means, ses)
        observed = rng.normal(truth, observation_se)
        posterior_precision = np.divide(1, ses**2, out=np.zeros_like(ses), where=ses > 0)
        data_precision = 1 / observation_se**2
        posterior = means.copy()
        mask = ses > 0
        posterior[mask] = (
            means[mask] * posterior_precision[mask] + observed[mask] * data_precision
        ) / (posterior_precision[mask] + data_precision)
        improvements[draw] = max(0.0, float(np.max(posterior)) - current)
        chosen = int(np.argmax(posterior))
        regrets[draw] = float(np.max(truth) - truth[chosen])
    per_decision = float(np.mean(improvements))
    population_evsi = per_decision * future_population * relevance
    experiment_regret = float(np.mean(regrets)) * sample_size
    net_draws = (
        improvements * future_population * relevance - experiment_cost - regrets * sample_size
    )
    enbs = population_evsi - experiment_cost - experiment_regret
    conservative = float(
        np.mean(net_draws) - conservative_z * np.std(net_draws, ddof=1) / np.sqrt(draws)
    )
    return EVSIResult(
        evsi_per_future_decision=per_decision,
        population_evsi=population_evsi,
        experiment_cost=experiment_cost,
        expected_experiment_regret=experiment_regret,
        enbs=enbs,
        conservative_enbs=conservative,
        test_allowed=conservative > 0,
    )
