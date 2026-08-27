from __future__ import annotations

from decision_engine.schemas import RegretType


def regret(
    best_value: float, chosen_value: float, regret_type: RegretType
) -> tuple[RegretType, float]:
    """Require classification; observational counterfactuals are model-estimated."""
    return regret_type, max(0.0, best_value - chosen_value)
