from __future__ import annotations

import numpy as np

from commercial_twin.population_v2 import decompose_revenue, spend_quantiles
from commercial_twin.population_v2_benchmark import simulate_hurdle_population


def test_failure_decomposition_reconciles_exactly() -> None:
    report = decompose_revenue(
        predicted_buyers=80,
        predicted_orders=100,
        predicted_revenue=5_000,
        actual_buyers=100,
        actual_orders=150,
        actual_revenue=6_000,
    )
    contributions = (
        report.buyers.revenue_error_contribution
        + report.orders_per_buyer.revenue_error_contribution
        + report.revenue_per_order.revenue_error_contribution
    )
    assert np.isclose(contributions, report.total_revenue_error)


def test_hurdle_simulation_is_deterministic_and_orders_cannot_be_below_buyers() -> None:
    kwargs = {
        "purchase_probability": np.array([0.1, 0.5, 0.9]),
        "conditional_orders": np.array([1.0, 1.2, 2.0]),
        "conditional_value": np.array([10.0, 20.0, 30.0]),
        "new_buyers": 5.0,
        "new_orders": 7.0,
        "new_revenue": 140.0,
        "draws": 50,
        "seed": 7,
    }
    first = simulate_hurdle_population(**kwargs)
    second = simulate_hurdle_population(**kwargs)
    assert first == second
    assert first["orders"]["p05"] >= first["buyers"]["p05"]


def test_spend_quantiles_report_tail_concentration() -> None:
    result = spend_quantiles(np.array([1.0] * 99 + [100.0]))
    assert result["max"] == 100.0
    assert result["top_1pct_share"] > 0.5
