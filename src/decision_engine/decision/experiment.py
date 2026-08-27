from __future__ import annotations

from dataclasses import dataclass

from scipy.stats import norm


@dataclass(frozen=True)
class ExperimentCandidate:
    actions_to_compare: tuple[str, str]
    target_population: str
    estimated_sample_size_per_arm: int
    expected_business_cost: float | None
    estimated_information_gain: float | None
    rationale: str


def two_arm_sample_size(
    *,
    outcome_standard_deviation: float,
    minimum_detectable_effect: float,
    alpha: float = 0.05,
    power: float = 0.8,
) -> int:
    """Normal-approximation sample size for equal-sized independent continuous-outcome arms."""
    if outcome_standard_deviation <= 0 or minimum_detectable_effect <= 0:
        raise ValueError("standard deviation and detectable effect must be positive")
    if not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError("alpha and power must lie in (0, 1)")
    z_alpha = norm.ppf(1 - alpha / 2)
    z_power = norm.ppf(power)
    estimate = (
        2 * (z_alpha + z_power) ** 2 * outcome_standard_deviation**2 / minimum_detectable_effect**2
    )
    return int(estimate.__ceil__())


def propose_experiment(
    actions: tuple[str, str],
    *,
    target_population: str,
    outcome_standard_deviation: float,
    minimum_detectable_effect: float,
    cost_per_unit: float | None = None,
) -> ExperimentCandidate:
    sample = two_arm_sample_size(
        outcome_standard_deviation=outcome_standard_deviation,
        minimum_detectable_effect=minimum_detectable_effect,
    )
    cost = 2 * sample * cost_per_unit if cost_per_unit is not None else None
    return ExperimentCandidate(
        actions,
        target_population,
        sample,
        cost,
        None,
        "Actions are close relative to uncertainty; controlled randomization can resolve ranking.",
    )
