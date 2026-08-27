from __future__ import annotations

import numpy as np


def contribution_profit(
    price: np.ndarray | float,
    unit_cost: np.ndarray | float,
    quantity: np.ndarray | float,
    incremental_promo_cost: np.ndarray | float = 0.0,
) -> np.ndarray:
    return (np.asarray(price) - np.asarray(unit_cost)) * np.asarray(quantity) - np.asarray(
        incremental_promo_cost
    )


def incremental_profit(action_profit: np.ndarray, baseline_profit: np.ndarray) -> np.ndarray:
    return np.asarray(action_profit) - np.asarray(baseline_profit)
