from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import numpy as np
import polars as pl
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.preprocessing import OneHotEncoder

from commercial_twin.population_state import STATE_FEATURES

OutcomeName = Literal["purchase", "orders", "spend"]


def build_future_outcomes(
    events: pl.DataFrame, states: pl.DataFrame, start: datetime, end: datetime
) -> pl.DataFrame:
    future = events.filter((pl.col("event_time") > start) & (pl.col("event_time") <= end))
    purchase = future.filter(pl.col("event_type") == "purchase")
    outcomes = purchase.group_by("customer_id").agg(
        pl.lit(1.0).alias("purchase"),
        pl.col("session_id").n_unique().cast(pl.Float64).alias("orders"),
        pl.col("price").sum().alias("spend"),
    )
    return (
        states.select("customer_id")
        .join(outcomes, on="customer_id", how="left")
        .with_columns(pl.col("purchase", "orders", "spend").fill_null(0.0))
    )


@dataclass
class FeatureRepresentation:
    kind: str
    encoder: OneHotEncoder | None = None
    category_embedding: TruncatedSVD | None = None

    def fit_transform(self, states: pl.DataFrame) -> np.ndarray:
        basic = states.select(STATE_FEATURES).fill_null(181.0).to_numpy().astype(float)
        basic = np.log1p(np.clip(basic, 0, None))
        if self.kind == "RFM_STATE":
            return basic
        self.encoder = OneHotEncoder(handle_unknown="ignore", max_categories=32)
        category = self.encoder.fit_transform(states.select("dominant_category").to_numpy())
        components = max(1, min(4, category.shape[1] - 1))
        self.category_embedding = TruncatedSVD(n_components=components, random_state=42)
        learned_category = self.category_embedding.fit_transform(category)
        concentration = states.select("category_concentration").to_numpy()
        return np.column_stack([basic, concentration, learned_category])

    def transform(self, states: pl.DataFrame) -> np.ndarray:
        basic = states.select(STATE_FEATURES).fill_null(181.0).to_numpy().astype(float)
        basic = np.log1p(np.clip(basic, 0, None))
        if self.kind == "RFM_STATE":
            return basic
        if self.encoder is None or self.category_embedding is None:
            raise RuntimeError("representation has not been fitted")
        category = self.encoder.transform(states.select("dominant_category").to_numpy())
        learned_category = self.category_embedding.transform(category)
        concentration = states.select("category_concentration").to_numpy()
        return np.column_stack([basic, concentration, learned_category])


class PopulationOutcomeModel:
    def __init__(self, outcome: OutcomeName, representation: str, seed: int) -> None:
        self.outcome = outcome
        self.representation = FeatureRepresentation(representation)
        self.prediction_cap = 1.0
        if outcome == "purchase":
            self.model: HistGradientBoostingClassifier | HistGradientBoostingRegressor = (
                HistGradientBoostingClassifier(
                    max_iter=100, max_leaf_nodes=24, min_samples_leaf=50, random_state=seed
                )
            )
        else:
            self.model = HistGradientBoostingRegressor(
                loss="squared_error",
                max_iter=100,
                max_leaf_nodes=24,
                min_samples_leaf=50,
                random_state=seed,
            )

    def fit(self, states: pl.DataFrame, target: np.ndarray) -> PopulationOutcomeModel:
        matrix = self.representation.fit_transform(states)
        fitted_target = target
        if self.outcome != "purchase":
            self.prediction_cap = max(float(np.quantile(target, 0.999)), 1.0)
            fitted_target = np.log1p(np.clip(target, 0, self.prediction_cap))
        self.model.fit(matrix, fitted_target)
        return self

    def predict(self, states: pl.DataFrame) -> np.ndarray:
        matrix = self.representation.transform(states)
        if self.outcome == "purchase":
            classifier = self.model
            if not isinstance(classifier, HistGradientBoostingClassifier):
                raise TypeError("purchase model must be a classifier")
            return np.asarray(classifier.predict_proba(matrix)[:, 1], dtype=float)
        prediction = np.expm1(np.asarray(self.model.predict(matrix), dtype=float))
        return np.clip(prediction, 0, self.prediction_cap)


def baseline_predictions(
    states: pl.DataFrame,
    train_outcomes: pl.DataFrame,
    outcome: OutcomeName,
) -> dict[str, np.ndarray]:
    observed = train_outcomes[outcome].to_numpy().astype(float)
    population = np.full(states.height, float(np.mean(observed)))
    if outcome == "purchase":
        persistence = (states["purchases_30d"].to_numpy() > 0).astype(float)
        rfm = states["shrunk_purchase_propensity"].to_numpy().astype(float)
    elif outcome == "orders":
        persistence = states["purchases_30d"].to_numpy().astype(float)
        rfm = states["shrinkage_strength"].to_numpy() * persistence + (
            1 - states["shrinkage_strength"].to_numpy()
        ) * np.mean(observed)
    else:
        persistence = states["spend_30d"].to_numpy().astype(float)
        rfm = states["shrinkage_strength"].to_numpy() * persistence + (
            1 - states["shrinkage_strength"].to_numpy()
        ) * np.mean(observed)
    return {"population_average": population, "last_period": persistence, "rfm": rfm}


def simulate_population(
    purchase_probability: np.ndarray,
    expected_orders: np.ndarray,
    expected_spend: np.ndarray,
    *,
    draws: int = 300,
    seed: int = 42,
) -> dict[str, dict[str, float]]:
    rng = np.random.default_rng(seed)
    buyers = np.empty(draws)
    orders = np.empty(draws)
    revenue = np.empty(draws)
    for draw in range(draws):
        bought = rng.binomial(1, np.clip(purchase_probability, 0, 1))
        drawn_orders = rng.poisson(np.clip(expected_orders, 0, None))
        buyers[draw] = bought.sum()
        orders[draw] = drawn_orders.sum()
        revenue[draw] = rng.gamma(
            shape=2.0,
            scale=np.clip(expected_spend, 0, None) / 2.0,
        ).sum()

    def summary(values: np.ndarray) -> dict[str, float]:
        return {
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
            "lower_90": float(np.quantile(values, 0.05)),
            "upper_90": float(np.quantile(values, 0.95)),
        }

    return {"buyers": summary(buyers), "orders": summary(orders), "revenue": summary(revenue)}
