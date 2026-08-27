from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import NormalDist
from typing import Any

import numpy as np
import polars as pl

from commercial_twin.behavior import BehaviorPrediction
from commercial_twin.schemas import CommercialAction, CommercialState
from decision_engine.causal.continuous_dr import ContinuousDRDoseResponseEstimator
from decision_engine.core import DecisionDisposition, OutcomeDistribution
from decision_engine.decision.continuous_support import ConditionalSupportGate
from decision_engine.economics.profit import contribution_profit
from domains.commerce.actions import DiscountAction

DEFAULT_FEATURES = [
    "store_id",
    "category_id",
    "sku_id",
    "regular_price",
    "inventory",
    "near_stockout",
    "weekday",
    "holiday",
    "marketing",
    "competitor_signal",
    "product_age",
    "lagged_demand",
    "unit_cost",
]

MINIMAL_FEATURES = [
    "store_id",
    "category_id",
    "sku_id",
    "regular_price",
    "weekday",
    "product_age",
    "lagged_demand",
]


@dataclass
class ContinuousDiscountBehaviorModel:
    features: list[str] | None = None
    seed: int = 42
    action_type: str = "discount"
    model_version: str = "continuous-dr-commercial-v1"

    def fit(self, history: pl.DataFrame) -> ContinuousDiscountBehaviorModel:
        requested = list(self.features or DEFAULT_FEATURES)
        self.features_ = [name for name in requested if name in history.columns]
        if self.features is None:
            self.features_ = list(
                dict.fromkeys(
                    self.features_ + [name for name in MINIMAL_FEATURES if name in history.columns]
                )
            )
        if not self.features_:
            raise ValueError("no valid pre-treatment features are available")
        self._validate_history(history)
        self.history_ = history.sort("date")
        dates = self.history_["date"].unique(maintain_order=True).tail(14).to_list()
        self.decision_frame_ = self.history_.filter(pl.col("date").is_in(dates))
        self.estimator_ = ContinuousDRDoseResponseEstimator(seed=self.seed).fit(
            self.history_, self.features_
        )
        self.support_gate_ = ConditionalSupportGate(self.estimator_.density_model_).fit(
            self.history_, self.features_
        )
        residual = np.asarray(self.estimator_.crossfit_residual_, dtype=float)
        self.residual_scale_ = max(float(np.std(residual, ddof=1)), 1e-6)
        return self

    @staticmethod
    def _validate_history(history: pl.DataFrame) -> None:
        forbidden = {"baseline_demand", "beta", "gamma", "hidden_u", "oracle_truth"}
        leaked = forbidden & set(history.columns)
        if leaked:
            raise ValueError(f"oracle fields cannot enter behavior model: {sorted(leaked)}")

    @staticmethod
    def _distribution(
        name: str,
        mean: float,
        standard_error: float,
        support: dict[str, Any],
    ) -> OutcomeDistribution:
        normal = NormalDist()
        quantiles = {
            key: max(0.0, mean + normal.inv_cdf(probability) * standard_error)
            for key, probability in {
                "p05": 0.05,
                "p10": 0.10,
                "p25": 0.25,
                "p50": 0.50,
                "p75": 0.75,
                "p90": 0.90,
                "p95": 0.95,
            }.items()
        }
        return OutcomeDistribution(
            outcome_name=name,
            mean=max(mean, 0.0),
            variance=standard_error**2,
            calibration_metadata={
                "method": "cross_fitted_residual_normal_approximation",
                "status": "requires prospective calibration",
            },
            support_metadata=support,
            **quantiles,
        )

    def predict_outcomes(
        self, state: CommercialState, action: CommercialAction
    ) -> BehaviorPrediction:
        if not isinstance(action, DiscountAction):
            raise TypeError("continuous discount model only accepts DiscountAction")
        dose = action.discount_depth
        frame = self.decision_frame_
        if action.product_ids:
            frame = frame.filter(pl.col("sku_id").is_in(action.product_ids))
        if action.category_ids:
            frame = frame.filter(pl.col("category_id").is_in(action.category_ids))
        if frame.is_empty():
            raise ValueError("action scope has no matching decision rows")
        learned_world_features: list[str] = []
        for signal in state.world_state.signals:
            if signal.signal_name in self.features_ and isinstance(signal.value, (float, int)):
                frame = frame.with_columns(pl.lit(float(signal.value)).alias(signal.signal_name))
                learned_world_features.append(signal.signal_name)
        support_report = self.support_gate_.report(frame, dose)
        support = asdict(support_report)
        demand = self.estimator_.dose_response(frame, np.array([dose]))[:, 0]
        total_demand = float(np.sum(demand))
        prices = frame["regular_price"].to_numpy() * (1 - dose)
        total_revenue = float(np.sum(prices * demand))
        support_penalty = 2.0 if support_report.support_level == "LIMITED" else 1.0
        support_penalty = 4.0 if support_report.support_level == "UNSUPPORTED" else support_penalty
        demand_se = self.residual_scale_ * np.sqrt(frame.height) * support_penalty
        if support_report.support_level == "UNSUPPORTED":
            disposition = DecisionDisposition.ABSTAIN
        elif support_report.support_level == "LIMITED":
            disposition = DecisionDisposition.EXPERIMENT
        else:
            disposition = DecisionDisposition.ACT
        experiment = None
        if disposition == DecisionDisposition.EXPERIMENT:
            experiment = {
                "candidate_discount_depths": [max(0.0, dose - 0.05), dose],
                "reason": "local support or uncertainty is insufficient for direct action",
            }
        distributions = [
            self._distribution("units", total_demand, demand_se, support),
            self._distribution(
                "revenue", total_revenue, demand_se * float(np.mean(prices)), support
            ),
        ]
        if "unit_cost" in frame.columns and frame["unit_cost"].null_count() < frame.height:
            cost_mask = frame["unit_cost"].is_not_null().to_numpy()
            costs = frame.filter(pl.Series(cost_mask))["unit_cost"].to_numpy()
            profit = contribution_profit(prices[cost_mask], costs, demand[cost_mask])
            margin_scale = float(np.mean(np.maximum(prices[cost_mask] - costs, 0)))
            profit_support = {
                **support,
                "cost_complete_fraction": float(np.mean(cost_mask)),
                "economic_scope": "cost-complete decision rows only",
            }
            distributions.append(
                self._distribution(
                    "contribution_profit",
                    float(np.sum(profit)),
                    demand_se * margin_scale * np.sqrt(float(np.mean(cost_mask))),
                    profit_support,
                )
            )
        return BehaviorPrediction(
            distributions=tuple(distributions),
            disposition=disposition,
            evidence={
                "estimator": "cross_fitted_continuous_doubly_robust",
                "world_state_features_used": sorted(learned_world_features),
                "world_state_effect": "learned from pre-treatment training features only",
                "identification_claim": "conditional on measured pre-treatment controls only",
            },
            support=support,
            uncertainty={"method": "cross_fitted_residual_normal_approximation"},
            assumptions=self.estimator_.assumptions,
            model_versions={"discount": self.model_version},
            experiment=experiment,
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "density": asdict(self.estimator_.density_diagnostics_),
            "crossfit_folds": [asdict(fold) for fold in self.estimator_.crossfit_folds_],
            "decision_rows": self.decision_frame_.height,
        }

    def calibration_report(self) -> dict[str, Any]:
        return {
            "method": "cross_fitted_residual_normal_approximation",
            "prospective_records": 0,
            "warning": "intervals require prospective outcome calibration",
        }
