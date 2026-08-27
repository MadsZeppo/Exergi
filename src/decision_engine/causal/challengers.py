from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class OptionalIntegrationResult:
    library: str
    available: bool
    status: str
    details: dict[str, Any]


class DoWhyValidator:
    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("dowhy") is not None

    def validate_binary(
        self,
        frame: Any,
        *,
        treatment: str,
        outcome: str,
        common_causes: list[str],
    ) -> OptionalIntegrationResult:
        if not self.available():
            return OptionalIntegrationResult(
                "dowhy", False, "NOT_INSTALLED",
                {"install": "pip install -e '.[causal]'"},
            )
        from dowhy import CausalModel

        model = CausalModel(
            data=frame,
            treatment=treatment,
            outcome=outcome,
            common_causes=common_causes,
        )
        estimand = model.identify_effect(proceed_when_unidentifiable=False)
        estimate = model.estimate_effect(
            estimand, method_name="backdoor.linear_regression"
        )
        placebo = model.refute_estimate(
            estimand, estimate, method_name="placebo_treatment_refuter", random_seed=42
        )
        return OptionalIntegrationResult(
            "dowhy",
            True,
            "COMPLETED",
            {
                "estimand": str(estimand),
                "effect": float(estimate.value),
                "placebo": str(placebo),
            },
        )


class EconMLContinuousDMLChallenger:
    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("econml") is not None

    def fit_effect(
        self, x: np.ndarray, treatment: np.ndarray, outcome: np.ndarray
    ) -> OptionalIntegrationResult:
        if not self.available():
            return OptionalIntegrationResult(
                "econml", False, "NOT_INSTALLED",
                {"install": "pip install -e '.[causal]'"},
            )
        from econml.dml import LinearDML
        from sklearn.ensemble import RandomForestRegressor

        model = LinearDML(
            model_y=RandomForestRegressor(
                n_estimators=100, min_samples_leaf=20, random_state=42
            ),
            model_t=RandomForestRegressor(
                n_estimators=100, min_samples_leaf=20, random_state=42
            ),
            random_state=42,
        )
        model.fit(outcome, treatment, X=x)
        effect = np.asarray(model.effect(x), dtype=float)
        return OptionalIntegrationResult(
            "econml",
            True,
            "COMPLETED",
            {"mean_effect": float(np.mean(effect)), "effect_std": float(np.std(effect))},
        )
