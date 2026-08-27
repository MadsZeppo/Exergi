from __future__ import annotations

import numpy as np

from commercial_twin.population_v3 import (
    calibration_deciles,
    logit_intercept_reconcile,
    naive_probability_scale,
    reconcile_category_revenue,
    reconcile_expected_orders,
    reconcile_expected_revenue,
    simulate_reconciled_aggregates,
)


def test_logit_intercept_reconciliation_preserves_rank_bounds_and_total() -> None:
    probability = np.array([0.01, 0.1, 0.4, 0.8])
    reconciled, alpha = logit_intercept_reconcile(probability, 2.25)
    assert np.isfinite(alpha)
    assert np.all((reconciled >= 0) & (reconciled <= 1))
    assert np.all(np.argsort(probability) == np.argsort(reconciled))
    assert np.isclose(reconciled.sum(), 2.25, atol=1e-7)


def test_naive_scale_remains_valid() -> None:
    result = naive_probability_scale(np.array([0.1, 0.2, 0.3]), 0.9)
    assert np.all((result >= 0) & (result <= 1))


def test_order_and_revenue_reconciliation_obey_aggregate_constraints() -> None:
    buyers = np.array([0.2, 0.5, 0.8])
    orders = reconcile_expected_orders(buyers, np.array([1.0, 2.0, 3.0]), 3.5)
    assert np.isclose(orders.sum(), 3.5)
    assert orders.sum() >= buyers.sum()
    revenue = reconcile_expected_revenue(orders, np.array([10.0, 20.0, 40.0]), 100.0)
    assert np.all(revenue >= 0)
    assert np.isclose(revenue.sum(), 100.0)


def test_category_reconciliation_hits_supported_targets() -> None:
    revenue, factors = reconcile_category_revenue(
        np.array(["a", "a", "b"]), np.array([10.0, 20.0, 30.0]), {"a": 60, "b": 40}
    )
    assert np.isclose(revenue[:2].sum(), 60)
    assert np.isclose(revenue[2], 40)
    assert factors == {"a": 2.0, "b": 4 / 3}


def test_decile_calibration_exposes_aggregate_totals() -> None:
    actual = np.array([0, 0, 0, 1, 1] * 20)
    prediction = np.linspace(0.01, 0.9, len(actual))
    report = calibration_deciles(actual, prediction)
    assert len(report["deciles"]) == 10
    assert report["actual_buyers"] == 40
    assert report["mce"] >= report["ece"]


def test_reconciled_monte_carlo_is_deterministic_and_coherent() -> None:
    forecast = {"buyers": 100.0, "orders": 120.0, "revenue": 5000.0}
    residuals = {"buyers": [0.1, 0.2], "orders": [0.1], "revenue": [0.2]}
    first = simulate_reconciled_aggregates(forecast, residuals, draws=30, seed=4)
    second = simulate_reconciled_aggregates(forecast, residuals, draws=30, seed=4)
    assert first == second
    assert all(
        order >= buyer for buyer, order in zip(first["buyers"], first["orders"], strict=True)
    )
