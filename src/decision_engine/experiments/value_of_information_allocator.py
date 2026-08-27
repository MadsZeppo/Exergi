"""Finite-horizon conservative ENBS allocator measured against the current best policy."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ExperimentOption:
    action_family: str
    action: str
    posterior_mean: float
    posterior_standard_error: float
    outcome_standard_deviation: float
    sample_size: int
    treatment_probability: float
    future_population: int
    reuse_horizon: int
    relevance: float
    direct_cost_per_assignment: float
    reserved_downside_cost: float
    operational_switching_cost: float
    evidence_age_periods: int = 0


@dataclass(frozen=True)
class ValueOfInformationDecision:
    action_family: str
    action: str
    conservative_enbs: float
    expected_future_decision_value: float
    direct_experiment_cost: float
    expected_experiment_regret: float
    reserved_downside_cost: float
    operational_switching_cost: float
    information_value_per_reserved_risk: float
    test_allowed: bool
    reason: str


class ValueOfInformationAllocator:
    def __init__(
        self,
        *,
        draws: int = 4_000,
        conservative_z: float = 1.645,
        stale_discount_per_period: float = 0.92,
        seed: int = 73_001,
    ) -> None:
        self.draws = draws
        self.conservative_z = conservative_z
        self.stale_discount_per_period = stale_discount_per_period
        self.seed = seed

    def evaluate(
        self,
        option: ExperimentOption,
        *,
        current_best_incremental_value: float,
    ) -> ValueOfInformationDecision:
        if option.sample_size <= 0 or option.future_population < 0 or option.reuse_horizon <= 0:
            raise ValueError("experiment horizon and sample sizes must be finite and positive")
        if not 0 < option.treatment_probability < 1 or not 0 <= option.relevance <= 1:
            raise ValueError("invalid randomization or relevance")
        if min(
            option.posterior_standard_error,
            option.outcome_standard_deviation,
            option.direct_cost_per_assignment,
            option.reserved_downside_cost,
            option.operational_switching_cost,
        ) < 0:
            raise ValueError("uncertainty and cost inputs cannot be negative")
        rng = np.random.default_rng(self.seed)
        truth = rng.normal(option.posterior_mean, option.posterior_standard_error, self.draws)
        effective_n = max(
            2.0,
            option.sample_size
            * 4
            * option.treatment_probability
            * (1 - option.treatment_probability),
        )
        observation_se = option.outcome_standard_deviation / np.sqrt(effective_n)
        observed = rng.normal(truth, observation_se)
        prior_precision = (
            0.0 if option.posterior_standard_error == 0 else 1 / option.posterior_standard_error**2
        )
        data_precision = 1 / max(observation_se**2, 1e-12)
        if prior_precision == 0:
            posterior = np.full(self.draws, option.posterior_mean)
        else:
            posterior = (
                option.posterior_mean * prior_precision + observed * data_precision
            ) / (prior_precision + data_precision)
        current = max(0.0, current_best_incremental_value)
        after = np.maximum(current, posterior)
        stale_weight = self.stale_discount_per_period**option.evidence_age_periods
        population = (
            option.future_population * option.reuse_horizon * option.relevance * stale_weight
        )
        future_value_draws = np.maximum(after - current, 0.0) * population
        chosen_action = posterior > current
        experiment_regret_draws = np.where(
            chosen_action,
            np.maximum(current - truth, 0.0),
            np.maximum(truth - current, 0.0),
        ) * option.sample_size
        direct = option.sample_size * option.direct_cost_per_assignment
        net = (
            future_value_draws
            - experiment_regret_draws
            - direct
            - option.reserved_downside_cost
            - option.operational_switching_cost
        )
        conservative = float(
            np.mean(net) - self.conservative_z * np.std(net, ddof=1) / np.sqrt(self.draws)
        )
        reserved = max(option.reserved_downside_cost, 1e-12)
        allowed = conservative > 0
        return ValueOfInformationDecision(
            option.action_family,
            option.action,
            conservative,
            float(np.mean(future_value_draws)),
            direct,
            float(np.mean(experiment_regret_draws)),
            option.reserved_downside_cost,
            option.operational_switching_cost,
            conservative / reserved,
            allowed,
            (
                "conservative finite-horizon ENBS is positive"
                if allowed
                else "BAU: ENBS is non-positive"
            ),
        )

    def prioritize(
        self,
        options: tuple[ExperimentOption, ...],
        *,
        current_best_incremental_value: float,
    ) -> tuple[ValueOfInformationDecision, ...]:
        decisions = tuple(
            self.evaluate(option, current_best_incremental_value=current_best_incremental_value)
            for option in options
        )
        return tuple(
            sorted(
                decisions,
                key=lambda item: item.information_value_per_reserved_risk,
                reverse=True,
            )
        )
