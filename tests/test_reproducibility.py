import numpy as np

from decision_engine.simulation.monte_carlo import MonteCarloEngine


def test_simulation_is_deterministic() -> None:
    args = dict(
        baseline_quantity_samples=np.arange(10),
        treatment_effect_samples={"promo": np.arange(5)},
        prices={"none": 10.0, "promo": 8.0},
        unit_cost=4.0,
    )
    first = MonteCarloEngine(draws=100, seed=7).simulate_profit(**args)
    second = MonteCarloEngine(draws=100, seed=7).simulate_profit(**args)
    assert all(np.array_equal(first[key], second[key]) for key in first)
