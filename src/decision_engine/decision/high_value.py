"""Conservative high-value decision screening for V6."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PotentialDecisionValueReport:
    optimistic_effect: float
    gross_reusable_upside: float
    downside_penalty: float
    action_cost: float
    conservative_upper_value: float
    materiality_threshold: float
    passes: bool


def potential_decision_value(
    *,
    eligible_exposures: int,
    action_frequency: float,
    contribution_profit_scale: float,
    plausible_effect_mean: float,
    plausible_effect_standard_error: float,
    remaining_horizon: int,
    expected_reuse: float,
    freshness_weight: float,
    reversibility: float,
    downside: float,
    action_cost: float,
    materiality_threshold: float,
    optimistic_z: float = 1.28,
) -> PotentialDecisionValueReport:
    if eligible_exposures < 0 or remaining_horizon < 0:
        raise ValueError("exposure and horizon cannot be negative")
    bounded = (action_frequency, freshness_weight, reversibility)
    if any(value < 0 or value > 1 for value in bounded):
        raise ValueError("frequency/freshness/reversibility must lie in [0,1]")
    optimistic_effect = max(
        0.0, plausible_effect_mean + optimistic_z * plausible_effect_standard_error
    )
    reusable_exposures = (
        eligible_exposures * action_frequency * remaining_horizon * max(0.0, expected_reuse)
    )
    gross = (
        reusable_exposures
        * max(0.0, contribution_profit_scale)
        * optimistic_effect
        * freshness_weight
    )
    downside_penalty = max(0.0, downside) * (1 - reversibility) * reusable_exposures
    total_cost = max(0.0, action_cost) * reusable_exposures
    upper = gross - downside_penalty - total_cost
    return PotentialDecisionValueReport(
        optimistic_effect=optimistic_effect,
        gross_reusable_upside=gross,
        downside_penalty=downside_penalty,
        action_cost=total_cost,
        conservative_upper_value=upper,
        materiality_threshold=materiality_threshold,
        passes=upper > materiality_threshold,
    )
