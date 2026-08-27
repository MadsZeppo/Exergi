from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl


def synthetic_research_dataset(seed: int = 42, days: int = 730, entities: int = 8) -> pl.DataFrame:
    """Panel demo with confounding, heterogeneity, seasonality, and a final regime shift."""
    rng = np.random.default_rng(seed)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for entity in range(entities):
        category = f"category_{entity % 3}"
        base = 80 + 8 * entity
        for day in range(days):
            timestamp = start + timedelta(days=day)
            season = 12 * np.sin(2 * np.pi * day / 7) + 8 * np.sin(2 * np.pi * day / 365)
            weak_demand = rng.normal() - season / 30
            discount = rng.choice(
                [0, 10, 15, 20],
                p=[0.58, 0.18, 0.16, 0.08] if weak_demand < 0.5 else [0.8, 0.1, 0.07, 0.03],
            )
            treatment_effect = discount * (0.55 + 0.05 * (entity % 3))
            regime = 15 if day >= int(days * 0.9) else 0
            outcome = max(
                0, base + season + regime + treatment_effect + 5 * weak_demand + rng.normal(0, 8)
            )
            rows.append(
                {
                    "timestamp": timestamp,
                    "observed_at": timestamp + timedelta(hours=6),
                    "effective_at": timestamp,
                    "entity_id": f"sku_{entity}",
                    "group_id": category,
                    "location_id": f"store_{entity % 2}",
                    "action": f"{discount}%",
                    "discount_pct": discount,
                    "outcome": outcome,
                    "price": 10 * (1 - discount / 100),
                    "unit_cost": 5.0,
                    "randomized": False,
                }
            )
    return pl.DataFrame(rows)


def data_health_summary(frame: pl.DataFrame) -> dict[str, object]:
    return {
        "date_start": frame["timestamp"].min(),
        "date_end": frame["timestamp"].max(),
        "entities": frame["entity_id"].n_unique(),
        "observations": frame.height,
        "actions": frame["action"].n_unique(),
        "missing_cells": int(sum(frame[column].null_count() for column in frame.columns)),
    }
