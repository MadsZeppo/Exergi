from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import polars as pl

from commercial_twin.schemas import (
    CapabilityReadiness,
    ReadinessStatus,
    TwinReadinessReport,
)


def _status(condition: bool, limited: bool = False) -> ReadinessStatus:
    if condition:
        return ReadinessStatus.READY
    return ReadinessStatus.LIMITED if limited else ReadinessStatus.NOT_READY


def assess_readiness(
    twin_id: str,
    history: pl.DataFrame,
    *,
    calibration_count: int = 0,
    world_signal_count: int = 0,
) -> TwinReadinessReport:
    dates = history["date"].n_unique() if "date" in history.columns else 0
    discounts = history["discount"].n_unique() if "discount" in history.columns else 0
    complete = (
        1.0 - history["observed_sales"].null_count() / max(history.height, 1)
        if "observed_sales" in history.columns
        else 0.0
    )
    cost_completeness = (
        1 - history["unit_cost"].null_count() / max(history.height, 1)
        if "unit_cost" in history.columns
        else 0.0
    )
    common = {
        "data_volume": _status(history.height >= 500, history.height >= 100),
        "history_length": _status(dates >= 90, dates >= 30),
        "outcome_completeness": _status(complete >= 0.98, complete >= 0.90),
        "cost_quality": _status(cost_completeness >= 0.95, cost_completeness > 0),
        "calibration_history": _status(calibration_count >= 10, calibration_count > 0),
        "world_context_coverage": _status(world_signal_count >= 2, world_signal_count > 0),
    }
    discount_components = {
        **common,
        "action_variation": _status(discounts >= 20, discounts >= 5),
        "treatment_support": _status(
            discounts >= 20 and cast(float, history["discount"].max()) >= 0.20,
            discounts >= 5,
        ),
        "causal_identifiability": (
            ReadinessStatus.READY
            if "randomized_assignment" in history.columns
            and bool(history["randomized_assignment"].all())
            else _status(False, "lagged_demand" in history.columns)
        ),
    }
    hard = {"data_volume", "history_length", "action_variation", "treatment_support"}
    if any(discount_components[name] == ReadinessStatus.NOT_READY for name in hard):
        discount_status = ReadinessStatus.NOT_READY
    elif any(value != ReadinessStatus.READY for value in discount_components.values()):
        discount_status = ReadinessStatus.LIMITED
    else:
        discount_status = ReadinessStatus.READY
    unsupported = CapabilityReadiness(
        capability="price_change",
        status=ReadinessStatus.NOT_READY,
        components={"implemented_behavior_model": ReadinessStatus.NOT_READY},
        reasons=("typed action exists, but no causal behavior model is implemented",),
    )
    launch = unsupported.model_copy(update={"capability": "product_launch"})
    return TwinReadinessReport(
        twin_id=twin_id,
        capabilities=(
            CapabilityReadiness(
                capability="discount",
                status=discount_status,
                components=discount_components,
                reasons=(
                    "readiness is decomposed; LIMITED calibration does not invalidate support",
                    "hidden-confounding absence is not established",
                ),
            ),
            unsupported,
            launch,
        ),
        generated_at=datetime.now(UTC),
    )
