from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SimulationSummary:
    mean: float
    std: float
    p05: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    p95: float
    probability_positive: float
    probability_beat_baseline: float


@dataclass
class MonteCarloEngine:
    draws: int = 5000
    seed: int = 42

    def simulate_profit(
        self,
        *,
        baseline_quantity_samples: np.ndarray,
        treatment_effect_samples: dict[str, np.ndarray],
        prices: dict[str, float],
        unit_cost: float,
        promo_costs: dict[str, float] | None = None,
        baseline_action: str = "none",
    ) -> dict[str, np.ndarray]:
        """Resample empirical/model draws; no arbitrary percentage noise is introduced."""
        rng = np.random.default_rng(self.seed)
        baseline = rng.choice(np.asarray(baseline_quantity_samples), size=self.draws, replace=True)
        costs = promo_costs or {}
        results: dict[str, np.ndarray] = {}
        for action, effect_source in treatment_effect_samples.items():
            effect = rng.choice(np.asarray(effect_source), size=self.draws, replace=True)
            quantity = np.maximum(0, baseline + effect)
            results[action] = (prices[action] - unit_cost) * quantity - costs.get(action, 0.0)
        if baseline_action not in results:
            results[baseline_action] = (prices[baseline_action] - unit_cost) * baseline
        return results

    @staticmethod
    def summarize(samples: np.ndarray, baseline: np.ndarray) -> SimulationSummary:
        quantiles = np.quantile(samples, [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95])
        return SimulationSummary(
            mean=float(np.mean(samples)),
            std=float(np.std(samples)),
            p05=float(quantiles[0]),
            p10=float(quantiles[1]),
            p25=float(quantiles[2]),
            p50=float(quantiles[3]),
            p75=float(quantiles[4]),
            p90=float(quantiles[5]),
            p95=float(quantiles[6]),
            probability_positive=float(np.mean(samples > 0)),
            probability_beat_baseline=float(np.mean(samples > baseline)),
        )
