from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import polars as pl

POST_TREATMENT_COLUMNS = frozenset({"website_traffic_after_promo", "observed_sales"})


@dataclass(frozen=True)
class RetailWorldConfig:
    stores: int = 3
    categories: int = 3
    skus: int = 18
    days: int = 180
    support: str = "good"
    hidden_confounding: bool = False
    noise_scale: float = 0.15
    cannibalization: float = 0.08
    pull_forward: float = 0.35
    seed: int = 42


@dataclass(frozen=True)
class RetailWorld:
    frame: pl.DataFrame
    baseline_demand: np.ndarray
    beta: np.ndarray
    gamma: np.ndarray
    hidden_u: np.ndarray
    config: RetailWorldConfig
    interaction_matrix: np.ndarray

    def expected_demand(self, row_indices: np.ndarray, doses: np.ndarray) -> np.ndarray:
        rows = np.asarray(row_indices, dtype=int)
        dose = np.asarray(doses, dtype=float).reshape(1, -1)
        multiplier = np.exp(self.beta[rows, None] * dose - self.gamma[rows, None] * dose**2)
        return self.baseline_demand[rows, None] * multiplier

    def observed_demand(self, row_indices: np.ndarray, doses: np.ndarray) -> np.ndarray:
        latent = self.expected_demand(row_indices, doses)
        inventory = self.frame[row_indices]["inventory"].to_numpy()[:, None]
        return np.minimum(latent, inventory)

    def profit_curve(self, row_indices: np.ndarray, doses: np.ndarray) -> np.ndarray:
        demand = self.observed_demand(row_indices, doses)
        frame = self.frame[row_indices]
        price = frame["regular_price"].to_numpy()[:, None] * (1 - np.asarray(doses)[None, :])
        cost = frame["unit_cost"].to_numpy()[:, None]
        return (price - cost) * demand

    def dynamic_multiplier(self, dose: float, horizons: int = 29) -> np.ndarray:
        immediate = self.beta.mean() * dose
        kernel = np.zeros(horizons)
        kernel[:7] = immediate * np.exp(-np.arange(7) / 3)
        kernel[7:21] = -self.config.pull_forward * immediate * np.exp(-np.arange(14) / 6)
        kernel[21:] = 0.05 * immediate * np.exp(-np.arange(horizons - 21) / 4)
        return kernel

    def category_profit_effect(
        self, target_sku: int, dose: float, base_profit: np.ndarray
    ) -> float:
        own = base_profit[target_sku] * (
            np.exp(self.beta[target_sku] * dose - self.gamma[target_sku] * dose**2) - 1
        )
        spillover = float(np.sum(base_profit * self.interaction_matrix[target_sku] * dose))
        return float(own + spillover)


def generate_retail_world(config: RetailWorldConfig | None = None) -> RetailWorld:
    config = config or RetailWorldConfig()
    if config.support not in {"good", "weak", "bad"}:
        raise ValueError("support must be good, weak, or bad")
    rng = np.random.default_rng(config.seed)
    sku_category = np.arange(config.skus) % config.categories
    category_beta = rng.normal(2.8, 0.5, config.categories)
    sku_beta = np.clip(category_beta[sku_category] + rng.normal(0, 0.45, config.skus), 0.1, 5)
    sku_gamma = np.clip(rng.normal(3.2, 1.0, config.skus), -1.0, 7.0)
    sku_base = rng.lognormal(2.0, 0.45, config.skus)
    prices = rng.uniform(8, 40, config.skus)
    costs = prices * rng.uniform(0.35, 0.7, config.skus)
    interaction = np.zeros((config.skus, config.skus))
    for category in range(config.categories):
        members = np.flatnonzero(sku_category == category)
        for source in members:
            candidates = members[members != source]
            if candidates.size:
                chosen = rng.choice(candidates, min(2, candidates.size), replace=False)
                interaction[source, chosen[0]] = -config.cannibalization
                if chosen.size > 1:
                    interaction[source, chosen[1]] = config.cannibalization / 2

    records: list[dict[str, object]] = []
    truth_base: list[float] = []
    truth_beta: list[float] = []
    truth_gamma: list[float] = []
    truth_u: list[float] = []
    recent = np.full((config.stores, config.skus), sku_base)
    start = date(2024, 1, 1)
    for day in range(config.days):
        weekday = day % 7
        yearly = np.sin(2 * np.pi * day / 365)
        holiday = int(day % 90 in {0, 1, 2})
        marketing = rng.normal(0, 0.25)
        competitor = rng.normal(0, 0.2)
        for store in range(config.stores):
            store_effect = rng.normal(0, 0.08)
            for sku in range(config.skus):
                age = day / 365 + sku / config.skus
                hidden_u = rng.normal(0, 0.35)
                baseline_log = (
                    np.log(sku_base[sku])
                    + store_effect
                    + 0.18 * np.sin(2 * np.pi * weekday / 7)
                    + 0.12 * yearly
                    - 0.08 * age
                    + 0.12 * marketing
                    - 0.1 * competitor
                    + (0.18 * hidden_u if config.hidden_confounding else 0)
                )
                baseline = float(np.exp(baseline_log))
                inventory = max(1.0, baseline * rng.uniform(0.7, 2.2))
                weak_growth = max(0.0, 1 - recent[store, sku] / max(sku_base[sku], 0.1))
                score = (
                    -1.4
                    + 1.2 * weak_growth
                    + 2.5 * max(0, inventory / baseline - 1)
                    + 0.8 * holiday
                    + 0.2 * age
                    + 0.3 * marketing
                )
                if config.hidden_confounding:
                    score += 0.8 * hidden_u
                maximum = {"good": 0.30, "weak": 0.15, "bad": 0.04}[config.support]
                active = rng.random() < 1 / (1 + np.exp(-score))
                discount = float(rng.beta(2, 3) * maximum if active else 0.0)
                mean_demand = baseline * np.exp(
                    sku_beta[sku] * discount - sku_gamma[sku] * discount**2
                )
                latent = max(0.0, mean_demand * np.exp(rng.normal(0, config.noise_scale)))
                sales = min(latent, inventory)
                traffic_after = 50 + 30 * discount + 0.8 * latent + rng.normal(0, 3)
                records.append(
                    {
                        "date": start + timedelta(days=day),
                        "store_id": f"store_{store}",
                        "category_id": f"category_{sku_category[sku]}",
                        "sku_id": f"sku_{sku}",
                        "regular_price": prices[sku],
                        "price": prices[sku] * (1 - discount),
                        "discount": discount,
                        "inventory": inventory,
                        "near_stockout": inventory < mean_demand * 1.1,
                        "weekday": weekday,
                        "holiday": holiday,
                        "marketing": marketing,
                        "competitor_signal": competitor,
                        "product_age": age,
                        "lagged_demand": recent[store, sku],
                        "unit_cost": costs[sku],
                        "website_traffic_after_promo": traffic_after,
                        "observed_sales": sales,
                    }
                )
                truth_base.append(baseline)
                truth_beta.append(sku_beta[sku])
                truth_gamma.append(sku_gamma[sku])
                truth_u.append(hidden_u)
                recent[store, sku] = sales
    return RetailWorld(
        pl.DataFrame(records),
        np.asarray(truth_base),
        np.asarray(truth_beta),
        np.asarray(truth_gamma),
        np.asarray(truth_u),
        config,
        interaction,
    )
