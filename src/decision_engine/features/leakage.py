from datetime import datetime

import polars as pl


def assert_training_precedes_decision(
    frame: pl.DataFrame, decision_time: datetime, timestamp_col: str = "timestamp"
) -> None:
    latest = frame[timestamp_col].max()
    if frame.height and isinstance(latest, datetime) and latest >= decision_time:
        raise AssertionError("future leakage: training timestamp reaches decision time")


def assert_available_by_cutoff(
    frame: pl.DataFrame, cutoff: datetime, observed_at_col: str = "observed_at"
) -> None:
    latest = frame[observed_at_col].max()
    if frame.height and isinstance(latest, datetime) and latest > cutoff:
        raise AssertionError("future leakage: value was not observed by cutoff")
