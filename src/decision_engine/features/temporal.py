from __future__ import annotations

import polars as pl


def add_leak_safe_temporal_features(
    frame: pl.DataFrame,
    *,
    entity_col: str = "entity_id",
    timestamp_col: str = "timestamp",
    target_col: str = "outcome",
    lags: tuple[int, ...] = (1, 7, 14, 28),
    windows: tuple[int, ...] = (7, 14, 28),
) -> pl.DataFrame:
    """Create features using strictly prior target values within each entity."""
    result = frame.sort([entity_col, timestamp_col])
    expressions: list[pl.Expr] = [
        pl.col(timestamp_col).dt.weekday().alias("day_of_week"),
        pl.col(timestamp_col).dt.week().alias("week_of_year"),
        pl.col(timestamp_col).dt.month().alias("month"),
        pl.col(timestamp_col).dt.quarter().alias("quarter"),
    ]
    expressions.extend(
        pl.col(target_col).shift(lag).over(entity_col).alias(f"{target_col}_lag_{lag}")
        for lag in lags
    )
    shifted = pl.col(target_col).shift(1).over(entity_col)
    for window in windows:
        expressions.append(
            shifted.rolling_mean(window_size=window)
            .over(entity_col)
            .alias(f"rolling_mean_{window}")
        )
        expressions.append(
            shifted.rolling_std(window_size=window).over(entity_col).alias(f"rolling_std_{window}")
        )
    return result.with_columns(expressions)
