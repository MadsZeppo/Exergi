from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from decision_engine.causal.continuous import ContinuousTreatmentEstimator
from decision_engine.decision.continuous_support import (
    ConditionalSupportGate,
    ConditionalSupportReport,
    DoseSupport,
    continuous_dose_support,
)
from decision_engine.decision.experiment import ExperimentCandidate, propose_experiment
from decision_engine.uncertainty.continuous_bootstrap import CounterfactualBootstrapResult


@dataclass(frozen=True)
class ContinuousRecommendation:
    dose: float | None
    robust_range: tuple[float, float] | None
    status: str
    expected_profit: tuple[float, ...]
    support: tuple[DoseSupport | ConditionalSupportReport, ...]
    lower_profit: tuple[float, ...] = ()
    upper_profit: tuple[float, ...] = ()
    evidence_status: str = "UNASSESSED"
    reasons: tuple[str, ...] = ()
    experiment: ExperimentCandidate | None = None
    support_reasons: tuple[str, ...] = ()
    evidence_reasons: tuple[str, ...] = ()
    withholding_layer: str | None = None
    unconstrained_dose: float | None = None
    constrained_dose: float | None = None


class ContinuousDecisionEngine:
    def __init__(self, estimator: ContinuousTreatmentEstimator) -> None:
        self.estimator = estimator

    def fit(self, history: pl.DataFrame, features: list[str]) -> ContinuousDecisionEngine:
        self.history_ = history
        self.features_ = list(features)
        self.estimator.fit(history, features)
        density_model = getattr(self.estimator, "density_model_", None)
        self.support_gate_ = (
            ConditionalSupportGate(density_model).fit(history, features)
            if density_model is not None
            else None
        )
        return self

    def recommend(
        self,
        state: pl.DataFrame,
        doses: np.ndarray,
        *,
        near_optimal_fraction: float = 0.01,
        uncertainty: CounterfactualBootstrapResult | None = None,
        hard_falsification_failure: bool = False,
        sensitivity_warning: bool = False,
        maximum_projection_distance: float = 0.04,
    ) -> ContinuousRecommendation:
        demand = self.estimator.dose_response(state, doses)
        price = state["regular_price"].to_numpy()[:, None] * (1 - doses[None, :])
        cost = state["unit_cost"].to_numpy()[:, None]
        profit = np.mean((price - cost) * demand, axis=0)
        gate = getattr(self, "support_gate_", None)
        if gate is not None:
            conditional_support = tuple(
                gate.report(state, float(dose)) for dose in doses
            )
            support: tuple[DoseSupport | ConditionalSupportReport, ...] = conditional_support
            levels = np.array([item.support_level for item in conditional_support])
            feasible = levels != "UNSUPPORTED"
        else:
            dose_support = tuple(
                continuous_dose_support(self.history_["discount"].to_numpy(), float(dose))
                for dose in doses
            )
            support = dose_support
            levels = np.array([item.status for item in dose_support])
            feasible = levels != "OUT_OF_SUPPORT"
        if uncertainty is None:
            lower_profit = profit.copy()
            upper_profit = profit.copy()
        else:
            lower_profit = np.quantile(uncertainty.profit_samples, 0.05, axis=0)
            upper_profit = np.quantile(uncertainty.profit_samples, 0.95, axis=0)
        unconstrained_optimum = int(np.argmax(profit))
        support_reasons: list[str] = []
        if not feasible[unconstrained_optimum]:
            if not feasible.any():
                return ContinuousRecommendation(
                    None, None, "ABSTAIN", tuple(map(float, profit)), support,
                    tuple(map(float, lower_profit)), tuple(map(float, upper_profit)),
                    "INSUFFICIENT",
                    ("no candidate dose has conditional support",),
                    support_reasons=("no candidate dose has conditional support",),
                    withholding_layer="SUPPORT",
                    unconstrained_dose=float(doses[unconstrained_optimum]),
                )
            supported_optimum = int(np.argmax(np.where(feasible, profit, -np.inf)))
            projection_loss = float(profit[unconstrained_optimum] - profit[supported_optimum])
            projection_tolerance = max(
                abs(float(profit[unconstrained_optimum])) * near_optimal_fraction, 0.01
            )
            projection_distance = abs(
                float(doses[unconstrained_optimum] - doses[supported_optimum])
            )
            if (
                projection_loss <= projection_tolerance
                and projection_distance <= maximum_projection_distance
            ):
                support_reasons.append(
                    "unsupported optimum projected to a nearby supported near-optimal dose"
                )
            else:
                projection_reasons = [
                    "unconstrained economic optimum is outside conditional support"
                ]
                if projection_loss > projection_tolerance:
                    projection_reasons.append(
                        "nearest supported optimum is not economically near-optimal"
                    )
                if projection_distance > maximum_projection_distance:
                    projection_reasons.append(
                        "supported optimum is too distant for safe projection"
                    )
                return ContinuousRecommendation(
                    None, None, "ABSTAIN", tuple(map(float, profit)), support,
                    tuple(map(float, lower_profit)), tuple(map(float, upper_profit)),
                    "INSUFFICIENT", tuple(projection_reasons),
                    support_reasons=tuple(projection_reasons),
                    withholding_layer="SUPPORT",
                    unconstrained_dose=float(doses[unconstrained_optimum]),
                    constrained_dose=float(doses[supported_optimum]),
                )
        if not feasible.any():
            return ContinuousRecommendation(
                None,
                None,
                "ABSTAIN",
                tuple(map(float, profit)),
                support,
                tuple(map(float, lower_profit)),
                tuple(map(float, upper_profit)),
                "INSUFFICIENT",
                ("no candidate dose has conditional support",),
                support_reasons=("no candidate dose has conditional support",),
                withholding_layer="SUPPORT",
                unconstrained_dose=float(doses[unconstrained_optimum]),
            )
        if hard_falsification_failure:
            return ContinuousRecommendation(
                None,
                None,
                "ABSTAIN",
                tuple(map(float, profit)),
                support,
                tuple(map(float, lower_profit)),
                tuple(map(float, upper_profit)),
                "INSUFFICIENT",
                ("hard falsification failure",),
                evidence_reasons=("hard falsification failure",),
                withholding_layer="EVIDENCE",
                unconstrained_dose=float(doses[unconstrained_optimum]),
            )
        penalized = np.where(feasible, profit, -np.inf)
        optimum = int(np.argmax(penalized))
        threshold = max(abs(profit[optimum]) * near_optimal_fraction, 0.01)
        if uncertainty is None:
            near_optimal = profit >= profit[optimum] - threshold
        else:
            draw_best = np.max(
                np.where(feasible[None, :], uncertainty.profit_samples, -np.inf), axis=1
            )
            probability_near = np.mean(
                uncertainty.profit_samples >= draw_best[:, None] - threshold, axis=0
            )
            near_optimal = probability_near >= 0.5
        robust = doses[near_optimal & feasible]
        limited = levels[optimum] in {"LIMITED", "WEAK_SUPPORT", "MODERATE_SUPPORT"}
        selected_soft_warnings: tuple[str, ...] = ()
        selected_support = support[optimum]
        if isinstance(selected_support, ConditionalSupportReport):
            selected_soft_warnings = selected_support.soft_warnings
        uncertain = uncertainty is not None and robust.size > 1
        promising = profit[optimum] > profit[0] + threshold
        interesting = profit[optimum] > profit[0]
        evidence_reasons: list[str] = []
        experiment = None
        if limited:
            support_reasons.append("best candidate has limited conditional support")
        if uncertain:
            evidence_reasons.append(
                "profit intervals do not identify a unique economic optimum"
            )
        if sensitivity_warning:
            evidence_reasons.append(
                "unmeasured-confounding sensitivity downgraded evidence"
            )
        multiple_soft_warnings = len(selected_soft_warnings) > 1
        if (multiple_soft_warnings or uncertain or sensitivity_warning) and (
            promising or interesting
        ):
            status = "EXPERIMENT"
            candidate_indices = np.flatnonzero(near_optimal & feasible)
            if candidate_indices.size < 2:
                candidate_indices = np.argsort(penalized)[-2:]
            first, second = int(candidate_indices[0]), int(candidate_indices[-1])
            observed_sd = max(float(np.std(self.history_["observed_sales"].to_numpy())), 1e-6)
            effect = max(
                abs(float(demand[:, second].mean() - demand[:, first].mean())),
                observed_sd * 0.1,
            )
            experiment = propose_experiment(
                (f"{doses[first]:.0%}", f"{doses[second]:.0%}"),
                target_population="decision-context comparable retail units",
                outcome_standard_deviation=observed_sd,
                minimum_detectable_effect=effect,
            )
        elif interesting and not promising:
            status = "EXPERIMENT"
            evidence_reasons.append(
                "estimated advantage is positive but below the action threshold"
            )
            candidate_indices = np.flatnonzero(near_optimal & feasible)
            if candidate_indices.size < 2:
                candidate_indices = np.argsort(penalized)[-2:]
            first, second = int(candidate_indices[0]), int(candidate_indices[-1])
            observed_sd = max(float(np.std(self.history_["observed_sales"].to_numpy())), 1e-6)
            effect = max(
                abs(float(demand[:, second].mean() - demand[:, first].mean())),
                observed_sd * 0.1,
            )
            experiment = propose_experiment(
                (f"{doses[first]:.0%}", f"{doses[second]:.0%}"),
                target_population="decision-context comparable retail units",
                outcome_standard_deviation=observed_sd,
                minimum_detectable_effect=effect,
            )
        elif not promising:
            status = "ABSTAIN"
            evidence_reasons.append(
                "no economically meaningful advantage over the baseline dose"
            )
        else:
            status = "ACT"
        return ContinuousRecommendation(
            None if status == "ABSTAIN" else float(doses[optimum]),
            None if status == "ABSTAIN" else (float(robust.min()), float(robust.max())),
            status,
            tuple(map(float, profit)),
            support,
            tuple(map(float, lower_profit)),
            tuple(map(float, upper_profit)),
            "STRONG" if status == "ACT" else "LIMITED",
            tuple(support_reasons + evidence_reasons),
            experiment,
            tuple(support_reasons),
            tuple(evidence_reasons),
            (
                "SUPPORT"
                if status != "ACT" and support_reasons and not evidence_reasons
                else "EVIDENCE" if status != "ACT" else None
            ),
            float(doses[unconstrained_optimum]),
            float(doses[optimum]),
        )
