"""Bounded economic experiment design and exact propensity logging."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from decision_engine.decision.value_of_information import NormalActionEvidence, monte_carlo_evsi


class EnrollmentStrategy(StrEnum):
    RANDOM = "RANDOM"
    STRATIFIED = "STRATIFIED"
    MATCHED_BLOCK = "MATCHED_BLOCK"
    NEYMAN = "NEYMAN"


@dataclass(frozen=True)
class ExperimentDesign:
    sample_size: int
    treatment_allocation: float
    enrollment: EnrollmentStrategy
    predicted_evsi: float
    predicted_regret: float
    direct_cost: float
    net_value: float
    conservative_net_value: float
    test_allowed: bool


def optimize_experiment(
    evidence: NormalActionEvidence,
    *,
    future_population: int,
    relevance: float,
    outcome_standard_deviation: float,
    direct_cost_per_unit: float,
    sample_sizes: tuple[int, ...],
    allocations: tuple[float, ...],
    enrollments: tuple[EnrollmentStrategy, ...],
    seed: int,
) -> ExperimentDesign:
    candidates: list[ExperimentDesign] = []
    for index, n in enumerate(sample_sizes):
        for q in allocations:
            if not 0.05 <= q <= 0.95:
                raise ValueError("allocation violates support floor")
            effective_n = max(2, int(n * 4 * q * (1 - q)))
            for enrollment in enrollments:
                if enrollment is EnrollmentStrategy.MATCHED_BLOCK and not np.isclose(q, 0.5):
                    continue
                variance_factor = {
                    EnrollmentStrategy.RANDOM: 1.0,
                    EnrollmentStrategy.STRATIFIED: 0.85,
                    EnrollmentStrategy.MATCHED_BLOCK: 0.75,
                    EnrollmentStrategy.NEYMAN: 0.80,
                }[enrollment]
                result = monte_carlo_evsi(
                    (evidence,),
                    future_population=future_population,
                    relevance=relevance,
                    sample_size=effective_n,
                    outcome_standard_deviation=outcome_standard_deviation
                    * np.sqrt(variance_factor),
                    experiment_cost=n * direct_cost_per_unit,
                    draws=800,
                    seed=seed + index,
                )
                candidates.append(
                    ExperimentDesign(
                        sample_size=n,
                        treatment_allocation=q,
                        enrollment=enrollment,
                        predicted_evsi=result.population_evsi,
                        predicted_regret=result.expected_experiment_regret,
                        direct_cost=result.experiment_cost,
                        net_value=result.enbs,
                        conservative_net_value=result.conservative_enbs,
                        test_allowed=result.test_allowed,
                    )
                )
    if not candidates:
        raise ValueError("experiment design grid is empty")
    return max(candidates, key=lambda item: item.conservative_net_value)


def logged_assignment(
    random_uniform: np.ndarray,
    *,
    treatment_allocation: float,
    support_floor: float = 0.05,
) -> tuple[np.ndarray, np.ndarray]:
    if not support_floor <= treatment_allocation <= 1 - support_floor:
        raise ValueError("assignment probability violates support floor")
    action = np.asarray(random_uniform, dtype=float) < treatment_allocation
    propensity = np.where(action, treatment_allocation, 1 - treatment_allocation)
    return action.astype(np.int8), propensity


def neyman_allocation(
    treatment_standard_deviation: float,
    control_standard_deviation: float,
    *,
    support_floor: float = 0.10,
) -> float:
    if treatment_standard_deviation <= 0 or control_standard_deviation <= 0:
        raise ValueError("Neyman allocation requires positive standard deviations")
    raw = treatment_standard_deviation / (treatment_standard_deviation + control_standard_deviation)
    return float(np.clip(raw, support_floor, 1 - support_floor))
