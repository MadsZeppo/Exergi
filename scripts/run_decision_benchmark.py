#!/usr/bin/env python3
"""Deterministic smoke benchmark for economic decision mechanics."""

import numpy as np

from decision_engine.simulation.monte_carlo import MonteCarloEngine


def main() -> None:
    rng = np.random.default_rng(42)
    engine = MonteCarloEngine()
    samples = engine.simulate_profit(
        baseline_quantity_samples=rng.normal(100, 10, 1000),
        treatment_effect_samples={"promo": rng.normal(20, 6, 1000)},
        prices={"none": 10.0, "promo": 8.5},
        unit_cost=5.0,
    )
    print({name: engine.summarize(value, samples["none"]) for name, value in samples.items()})


if __name__ == "__main__":
    main()
