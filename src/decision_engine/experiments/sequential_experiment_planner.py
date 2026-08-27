"""Fixed-randomization V7 experiment plans sized to an economic effect."""

from __future__ import annotations

from dataclasses import dataclass

from decision_engine.decision.experiment import two_arm_sample_size


@dataclass(frozen=True)
class FixedRCTPlan:
    experiment_id: str
    action_family: str
    control_action: str
    treatment_action: str
    sample_size_per_arm: int
    total_sample_size: int
    treatment_probability: float
    minimum_economically_relevant_effect: float
    outcome_standard_deviation: float
    outcome_maturity_periods: int
    permanent_control_fraction: float
    adaptive_allocation: bool
    reason: str


class SequentialExperimentPlanner:
    def plan_fixed_rct(
        self,
        *,
        experiment_id: str,
        action_family: str,
        treatment_action: str,
        minimum_economically_relevant_effect: float,
        outcome_standard_deviation: float,
        available_population: int,
        outcome_maturity_periods: int,
        permanent_control_fraction: float = 0.10,
        alpha: float = 0.05,
        power: float = 0.80,
    ) -> FixedRCTPlan:
        if available_population < 4 or outcome_maturity_periods <= 0:
            raise ValueError("insufficient population or invalid feedback clock")
        if not 0 < permanent_control_fraction < 1:
            raise ValueError("permanent control must be in (0, 1)")
        per_arm = two_arm_sample_size(
            outcome_standard_deviation=outcome_standard_deviation,
            minimum_detectable_effect=minimum_economically_relevant_effect,
            alpha=alpha,
            power=power,
        )
        per_arm = min(per_arm, available_population // 2)
        if per_arm < 2:
            raise ValueError("available population cannot support both randomized arms")
        return FixedRCTPlan(
            experiment_id,
            action_family,
            "BAU",
            treatment_action,
            per_arm,
            per_arm * 2,
            0.5,
            minimum_economically_relevant_effect,
            outcome_standard_deviation,
            outcome_maturity_periods,
            permanent_control_fraction,
            False,
            "fixed RCT sized to the minimum economically relevant effect",
        )
