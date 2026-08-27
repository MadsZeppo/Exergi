from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast

import numpy as np
import polars as pl
from sklearn.cluster import MiniBatchKMeans
from sklearn.preprocessing import StandardScaler

from commercial_twin.population_contracts import (
    BehavioralCohort,
    CustomerPopulationSnapshot,
    PopulationComparison,
)

STATE_FEATURES = (
    "last_view_days",
    "last_cart_days",
    "last_purchase_days",
    "views_7d",
    "views_30d",
    "views_90d",
    "carts_7d",
    "carts_30d",
    "carts_90d",
    "purchases_30d",
    "purchases_90d",
    "purchases_180d",
    "spend_30d",
    "spend_90d",
    "spend_180d",
    "aov",
    "median_item_price",
    "product_repeat_rate",
    "view_to_cart",
    "cart_to_purchase",
    "abandonment_rate",
    "purchase_frequency_change",
    "spend_change",
    "observation_count",
    "effective_history_days",
    "reliability",
    "shrinkage_strength",
)


def _days_since(column: str, event_type: str, as_of: datetime) -> pl.Expr:
    return (
        (pl.lit(as_of) - pl.col("event_time").filter(pl.col("event_type") == event_type).max())
        .dt.total_seconds()
        .truediv(86_400)
        .alias(column)
    )


def _window_count(event_type: str, days: int, as_of: datetime, alias: str) -> pl.Expr:
    start = as_of - timedelta(days=days)
    return (
        ((pl.col("event_type") == event_type) & (pl.col("event_time") > start)).sum().alias(alias)
    )


def _window_spend(days: int, as_of: datetime, alias: str) -> pl.Expr:
    start = as_of - timedelta(days=days)
    return (
        pl.when((pl.col("event_type") == "purchase") & (pl.col("event_time") > start))
        .then(pl.col("price"))
        .otherwise(0.0)
        .sum()
        .alias(alias)
    )


def build_customer_states(events: pl.DataFrame, as_of: datetime) -> pl.DataFrame:
    """Build states exclusively from events at or before ``as_of``."""
    history = events.filter(pl.col("event_time") <= as_of)
    if history.is_empty():
        raise ValueError("no customer history is available at as_of")
    summary = history.group_by("customer_id").agg(
        pl.col("event_time").min().alias("first_seen"),
        _days_since("last_view_days", "view", as_of),
        _days_since("last_cart_days", "cart", as_of),
        _days_since("last_purchase_days", "purchase", as_of),
        _window_count("view", 7, as_of, "views_7d"),
        _window_count("view", 30, as_of, "views_30d"),
        _window_count("view", 90, as_of, "views_90d"),
        _window_count("cart", 7, as_of, "carts_7d"),
        _window_count("cart", 30, as_of, "carts_30d"),
        _window_count("cart", 90, as_of, "carts_90d"),
        _window_count("purchase", 30, as_of, "purchases_30d"),
        _window_count("purchase", 90, as_of, "purchases_90d"),
        _window_count("purchase", 180, as_of, "purchases_180d"),
        _window_spend(30, as_of, "spend_30d"),
        _window_spend(90, as_of, "spend_90d"),
        _window_spend(180, as_of, "spend_180d"),
        pl.col("price").filter(pl.col("event_type") == "purchase").mean().fill_null(0).alias("aov"),
        pl.col("price").median().fill_null(0).alias("median_item_price"),
        pl.col("product_id")
        .filter(pl.col("event_type") == "purchase")
        .n_unique()
        .alias("purchase_products"),
        pl.col("product_id")
        .filter(pl.col("event_type") == "purchase")
        .count()
        .alias("purchase_events"),
        pl.len().alias("observation_count"),
    )
    summary = summary.with_columns(
        ((pl.lit(as_of) - pl.col("first_seen")).dt.total_seconds() / 86_400)
        .clip(0, 180)
        .alias("effective_history_days"),
        (1 - pl.col("purchase_products") / pl.col("purchase_events").clip(1, None))
        .clip(0, 1)
        .alias("product_repeat_rate"),
        (pl.col("carts_90d") / pl.col("views_90d").clip(1, None)).clip(0, 1).alias("view_to_cart"),
        (pl.col("purchases_90d") / pl.col("carts_90d").clip(1, None))
        .clip(0, 1)
        .alias("cart_to_purchase"),
        (1 - pl.col("purchases_90d") / pl.col("carts_90d").clip(1, None))
        .clip(0, 1)
        .alias("abandonment_rate"),
        (pl.col("purchases_30d") - (pl.col("purchases_90d") - pl.col("purchases_30d")) / 2).alias(
            "purchase_frequency_change"
        ),
        (pl.col("spend_30d") - (pl.col("spend_90d") - pl.col("spend_30d")) / 2).alias(
            "spend_change"
        ),
        (pl.col("observation_count") / (pl.col("observation_count") + 20)).alias(
            "shrinkage_strength"
        ),
        (pl.col("observation_count") / (pl.col("observation_count") + 20)).alias("reliability"),
        pl.col("observation_count").cast(pl.Float64).alias("effective_sample_size"),
    ).with_columns(
        pl.when(pl.col("effective_history_days") <= 30)
        .then(pl.lit("NEW"))
        .when(pl.col("last_purchase_days") <= 30)
        .then(pl.lit("ACTIVE"))
        .when((pl.col("last_purchase_days") <= 90) | (pl.col("views_30d") > 0))
        .then(pl.lit("COOLING"))
        .otherwise(pl.lit("DORMANT"))
        .alias("lifecycle"),
        pl.lit(as_of).alias("as_of"),
    )
    population_purchase_rate = float(cast(float, (summary["purchases_30d"] > 0).mean()))
    summary = summary.with_columns(
        (
            pl.col("shrinkage_strength") * (pl.col("purchases_30d") > 0).cast(pl.Float64)
            + (1 - pl.col("shrinkage_strength")) * population_purchase_rate
        ).alias("shrunk_purchase_propensity")
    )
    return summary.sort("customer_id")


def attach_affinities(events: pl.DataFrame, states: pl.DataFrame, as_of: datetime) -> pl.DataFrame:
    history = events.filter(pl.col("event_time") <= as_of)
    categories = (
        history.group_by("customer_id", "category_id")
        .len(name="category_events")
        .with_columns(
            (pl.col("category_events") / pl.col("category_events").sum().over("customer_id")).alias(
                "category_share"
            )
        )
        .sort(["customer_id", "category_events"], descending=[False, True])
        .group_by("customer_id", maintain_order=True)
        .agg(
            pl.col("category_id").first().alias("dominant_category"),
            pl.col("category_share").first().alias("category_concentration"),
        )
    )
    return states.join(categories, on="customer_id", how="left").with_columns(
        pl.col("dominant_category").fill_null("UNKNOWN"),
        pl.col("category_concentration").fill_null(0.0),
    )


def build_cohorts(
    states: pl.DataFrame, *, n_cohorts: int = 8, seed: int = 42
) -> tuple[pl.DataFrame, tuple[BehavioralCohort, ...]]:
    features = [
        "last_purchase_days",
        "views_30d",
        "carts_30d",
        "purchases_90d",
        "spend_90d",
        "aov",
        "view_to_cart",
        "product_repeat_rate",
    ]
    matrix = states.select(features).fill_null(181.0).to_numpy().astype(float)
    matrix = np.log1p(np.clip(matrix, 0, None))
    scaled = StandardScaler().fit_transform(matrix)
    count = min(n_cohorts, len(states))
    model = MiniBatchKMeans(n_clusters=count, random_state=seed, n_init=10, batch_size=4096).fit(
        scaled
    )
    labels = np.asarray(model.labels_, dtype=int)
    labeled = states.with_columns(
        pl.Series("cohort_id", [f"Cohort {value + 1:02d}" for value in labels])
    )
    cohorts: list[BehavioralCohort] = []
    for value in range(count):
        rows = labeled.filter(pl.col("cohort_id") == f"Cohort {value + 1:02d}")
        statistics = {
            "purchase_rate_30d": float(cast(float, (rows["purchases_30d"] > 0).mean())),
            "mean_spend_90d": float(cast(float, rows["spend_90d"].mean())),
            "mean_views_30d": float(cast(float, rows["views_30d"].mean())),
        }
        cohorts.append(
            BehavioralCohort(
                cohort_id=f"Cohort {value + 1:02d}",
                size=rows.height,
                centroid=tuple(float(item) for item in model.cluster_centers_[value]),
                statistics=statistics,
                stability=1.0,
                description=(
                    f"Observed state: {statistics['purchase_rate_30d']:.1%} purchased in 30d; "
                    f"mean 90d spend {statistics['mean_spend_90d']:.2f}."
                ),
            )
        )
    return labeled, tuple(cohorts)


def build_population_snapshot(
    states: pl.DataFrame,
    cohorts: tuple[BehavioralCohort, ...],
    *,
    as_of: datetime,
    model_versions: dict[str, str] | None = None,
) -> CustomerPopulationSnapshot:
    active = states.filter(
        (pl.col("views_30d") + pl.col("carts_30d") + pl.col("purchases_30d")) > 0
    )
    lifecycle_counts = states.group_by("lifecycle").len()
    lifecycle = {
        str(row["lifecycle"]): float(row["len"]) / states.height
        for row in lifecycle_counts.iter_rows(named=True)
    }
    category = states.group_by("dominant_category").len().sort("len", descending=True).head(20)
    category_mix = {
        str(row["dominant_category"]): float(row["len"]) / states.height
        for row in category.iter_rows(named=True)
    }
    purchases = float(states["purchases_30d"].sum())
    return CustomerPopulationSnapshot(
        as_of=as_of,
        active_customers=active.height,
        behavioral_cohorts=cohorts,
        purchase_rate=float(cast(float, (states["purchases_30d"] > 0).mean())),
        aov=float(cast(float, states["spend_30d"].sum())) / max(purchases, 1),
        category_mix=category_mix,
        customer_state_distribution=lifecycle,
        recent_behavior_shifts={
            "purchase_frequency": float(cast(float, states["purchase_frequency_change"].mean())),
            "spend": float(cast(float, states["spend_change"].mean())),
        },
        state_support={
            "customers": states.height,
            "median_observations": float(cast(float, states["observation_count"].median())),
            "mean_reliability": float(cast(float, states["reliability"].mean())),
        },
        model_versions=model_versions or {},
    )


def compare_population(
    earlier: CustomerPopulationSnapshot, later: CustomerPopulationSnapshot
) -> PopulationComparison:
    lifecycle_keys = set(earlier.customer_state_distribution) | set(
        later.customer_state_distribution
    )
    category_keys = set(earlier.category_mix) | set(later.category_mix)
    return PopulationComparison(
        earlier_as_of=earlier.as_of,
        later_as_of=later.as_of,
        active_customer_change=later.active_customers - earlier.active_customers,
        purchase_rate_change=later.purchase_rate - earlier.purchase_rate,
        aov_change=later.aov - earlier.aov,
        lifecycle_distribution_change={
            key: later.customer_state_distribution.get(key, 0)
            - earlier.customer_state_distribution.get(key, 0)
            for key in sorted(lifecycle_keys)
        },
        category_mix_change={
            key: later.category_mix.get(key, 0) - earlier.category_mix.get(key, 0)
            for key in sorted(category_keys)
        },
    )
